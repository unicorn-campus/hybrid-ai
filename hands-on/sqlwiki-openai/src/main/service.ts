import { existsSync } from 'node:fs'
import { mkdir, readFile, rename, unlink, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'
import { fork, type ChildProcess } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import type {
  Bootstrap, Cell, Connection, HistoryEntry, QueryRequest, QueryResult, SchemaInfo,
  TableDetails, TableInfo, Workspace
} from '../shared/types'
import { dangerousSql, isReadOnlySql, quoteIdentifier, splitSql } from '../shared/sql'

export interface SecretCodec {
  encrypt(value: string): string
  decrypt(value: string): string
}

interface StoredConnection extends Omit<Connection, 'password' | 'hasPassword'> { secret?: string }
interface State { connections: StoredConnection[]; history: HistoryEntry[]; workspace?: Workspace }
type RemoteHandle = { engine: 'postgres' | 'mysql'; client: any; profile: Connection }
type Handle = RemoteHandle | { engine: 'sqlite'; profile: Connection; session: SqliteSession }

const DEFAULT_LIMIT = 200
const MAX_LIMIT = 1_000
const DEMO_ID = 'sqlkiwi-demo'

export class SqlkiwiService {
  private readonly statePath: string
  private readonly demoPath: string
  private state: State = { connections: [], history: [] }
  private loaded = false
  private writeQueue: Promise<void> = Promise.resolve()
  private handles = new Map<string, Handle>()
  private active = new Map<string, { cancel(): Promise<void> }>()

  constructor(private readonly dataDir: string, private readonly codec?: SecretCodec) {
    this.statePath = join(dataDir, 'sqlkiwi-state.json')
    this.demoPath = join(dataDir, 'sqlkiwi-demo.db')
  }

  async bootstrap(): Promise<Bootstrap> {
    await this.load()
    await this.ensureDemo()
    return {
      connections: this.state.connections.map((item) => this.publicConnection(item)),
      history: [...this.state.history], workspace: this.state.workspace, demoId: DEMO_ID
    }
  }

  async saveConnection(input: Connection): Promise<Connection> {
    await this.load()
    const id = input.id || randomUUID()
    const index = this.state.connections.findIndex((item) => item.id === id)
    const previous = index >= 0 ? this.state.connections[index] : undefined
    let secret = previous?.secret
    if (input.password) {
      if (!this.codec) {
        throw new Error('PASSWORD_STORAGE_UNAVAILABLE: OS 암호화 기능을 사용할 수 없습니다.')
      }
      secret = this.codec.encrypt(input.password)
    }
    const stored: StoredConnection = {
      id, name: input.name.trim() || '새 연결', engine: input.engine,
      host: input.host?.trim(), port: input.port, database: input.database?.trim(),
      username: input.username?.trim(), filename: input.filename,
      readOnly: Boolean(input.readOnly), color: input.color, ssl: Boolean(input.ssl), secret
    }
    if (this.handles.has(id)) await this.disconnect(id)
    const previousConnections = [...this.state.connections]
    if (index >= 0) this.state.connections[index] = stored
    else this.state.connections.push(stored)
    try { await this.persist() }
    catch (error) { this.state.connections = previousConnections; throw error }
    return this.publicConnection(stored)
  }

  async deleteConnection(id: string): Promise<void> {
    await this.load()
    if (id === DEMO_ID) throw new Error('DEMO_CONNECTION_REQUIRED: 예제 연결은 삭제할 수 없습니다.')
    await this.disconnect(id)
    this.state.connections = this.state.connections.filter((item) => item.id !== id)
    await this.persist()
  }

  async testConnection(input: Connection): Promise<{ version: string }> {
    const profile = { ...input }
    if (!profile.password && profile.id) {
      await this.load()
      const stored = this.state.connections.find((item) => item.id === profile.id)
      if (stored) profile.password = this.readSecret(stored)
    }
    if (profile.engine === 'sqlite') {
      const filename = profile.id === DEMO_ID ? this.demoPath : profile.filename
      if (!filename) throw new Error('SQLITE_PATH_REQUIRED: 데이터베이스 파일을 선택해 주세요.')
      const session = await SqliteSession.open(filename, Boolean(profile.readOnly))
      try { return await session.request({ op: 'version' }) }
      finally { await session.dispose() }
    }
    const handle = await this.openRemote(profile)
    try { return { version: await this.remoteVersion(handle) } }
    finally { await this.closeRemote(handle) }
  }

  async connect(id: string): Promise<{ version: string; schema: SchemaInfo }> {
    const profile = await this.profile(id)
    await this.disconnect(id)
    if (profile.engine === 'sqlite') {
      const session = await SqliteSession.open(profile.filename!, Boolean(profile.readOnly))
      this.handles.set(id, { engine: 'sqlite', profile, session })
      const version = (await session.request<{ version: string }>({ op: 'version' })).version
      return { version, schema: await this.schema(id) }
    }
    const handle = await this.openRemote(profile)
    this.handles.set(id, handle)
    return { version: await this.remoteVersion(handle), schema: await this.remoteSchema(handle) }
  }

  async disconnect(id: string): Promise<void> {
    await this.cancel(id)
    const handle = this.handles.get(id)
    this.handles.delete(id)
    if (handle?.engine === 'postgres' || handle?.engine === 'mysql') await this.closeRemote(handle)
    else if (handle?.engine === 'sqlite') await handle.session.dispose()
  }

  async schema(id: string): Promise<SchemaInfo> {
    const handle = await this.connected(id)
    if (handle.engine === 'sqlite') {
      return handle.session.request({ op: 'schema' })
    }
    return this.remoteSchema(handle)
  }

  async tableDetails(id: string, table: TableInfo): Promise<TableDetails> {
    const handle = await this.connected(id)
    if (handle.engine === 'sqlite') {
      return handle.session.request({ op: 'tableDetails', table })
    }
    if (handle.engine === 'mysql') {
      const full = `${quoteIdentifier(table.schema, 'mysql')}.${quoteIdentifier(table.name, 'mysql')}`
      const [columns] = await handle.client.query(
        `SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY, COLUMN_DEFAULT
         FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=? AND TABLE_NAME=? ORDER BY ORDINAL_POSITION`,
        [table.schema, table.name]
      )
      const [ddlRows] = await handle.client.query(`SHOW CREATE TABLE ${full}`)
      return {
        columns: columns.map((row: any) => ({ name: row.COLUMN_NAME, type: row.COLUMN_TYPE,
          nullable: row.IS_NULLABLE === 'YES', primaryKey: row.COLUMN_KEY === 'PRI', defaultValue: row.COLUMN_DEFAULT })),
        ddl: ddlRows[0]?.['Create Table'] ?? ddlRows[0]?.['Create View'] ?? ''
      }
    }
    const result = await handle.client.query(
      `SELECT c.column_name, c.data_type, c.is_nullable, c.column_default,
              EXISTS (SELECT 1 FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name=kcu.constraint_name AND tc.constraint_schema=kcu.constraint_schema
                WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_schema=c.table_schema
                  AND tc.table_name=c.table_name AND kcu.column_name=c.column_name) AS primary_key
       FROM information_schema.columns c WHERE c.table_schema=$1 AND c.table_name=$2 ORDER BY c.ordinal_position`,
      [table.schema, table.name]
    )
    const columns = result.rows.map((row: any) => ({ name: row.column_name, type: row.data_type,
      nullable: row.is_nullable === 'YES', primaryKey: row.primary_key, defaultValue: row.column_default }))
    if (table.type === 'view') {
      const view = await handle.client.query(
        `SELECT pg_get_viewdef(to_regclass(format('%I.%I', $1::text, $2::text)), true) AS definition`,
        [table.schema, table.name]
      )
      return { columns, ddl: `CREATE VIEW ${quoteIdentifier(table.schema, 'postgres')}.` +
        `${quoteIdentifier(table.name, 'postgres')} AS\n${view.rows[0]?.definition ?? ''}` }
    }
    const constraints = await handle.client.query(
      `SELECT conname, pg_get_constraintdef(oid, true) AS definition
       FROM pg_constraint
       WHERE conrelid=to_regclass(format('%I.%I', $1::text, $2::text)) ORDER BY conname`,
      [table.schema, table.name]
    )
    const fields = columns.map((column: any) => {
      const nullable = column.nullable ? '' : ' NOT NULL'
      const defaultValue = column.defaultValue == null ? '' : ` DEFAULT ${column.defaultValue}`
      return `  ${quoteIdentifier(column.name, 'postgres')} ${column.type}${defaultValue}${nullable}`
    })
    fields.push(...constraints.rows.map((constraint: any) =>
      `  CONSTRAINT ${quoteIdentifier(constraint.conname, 'postgres')} ${constraint.definition}`))
    return {
      columns,
      ddl: `CREATE TABLE ${quoteIdentifier(table.schema, 'postgres')}.` +
        `${quoteIdentifier(table.name, 'postgres')} (\n${fields.join(',\n')}\n);`
    }
  }

  async query(request: QueryRequest): Promise<QueryResult[]> {
    await this.load()
    if (this.active.has(request.connectionId)) {
      throw new Error('QUERY_IN_PROGRESS: 이 연결에서 이미 쿼리를 실행 중입니다.')
    }
    const handle = await this.connected(request.connectionId)
    const statements = splitSql(request.sql, handle.profile.engine).map((item) => item.text)
    if (!statements.length) return []
    if (handle.profile.readOnly && statements.some((sql) => !isReadOnlySql(sql))) {
      throw new Error('READ_ONLY_CONNECTION: 읽기 전용 연결에서는 변경 SQL을 실행할 수 없습니다.')
    }
    if (!request.allowDangerous) {
      const danger = statements.map(dangerousSql).find(Boolean)
      if (danger) throw new Error(`DANGEROUS_SQL: ${danger} 문장은 사용자 확인이 필요합니다.`)
    }
    const limit = Math.max(1, Math.min(request.limit ?? DEFAULT_LIMIT, MAX_LIMIT))
    let results: QueryResult[] = []
    const started = Date.now()
    let failure: unknown
    try {
      if (handle.engine === 'sqlite') {
        this.active.set(request.connectionId, { cancel: async () => {
          this.handles.delete(request.connectionId)
          await handle.session.dispose()
        } })
        try { results = await handle.session.request({ op: 'query', statements, limit }) }
        finally { this.active.delete(request.connectionId) }
      } else {
        results = await this.remoteQuery(request.connectionId, handle, statements, limit)
      }
      failure = results.find((item) => item.error)?.error
      return results
    } catch (error) {
      failure = error
      throw sanitizeError(error)
    } finally {
      const profile = await this.profile(request.connectionId)
      const entry: HistoryEntry = {
        id: randomUUID(), connectionId: profile.id, connectionName: profile.name, sql: request.sql,
        executedAt: new Date().toISOString(), durationMs: Date.now() - started,
        rowCount: results.reduce((sum, item) => sum + item.rows.length, 0), success: !failure,
        error: failure ? sanitizeError(failure).message : undefined
      }
      this.state.history.unshift(entry)
      this.state.history = this.state.history.slice(0, 200)
      await this.persist()
    }
  }

  async cancel(id: string): Promise<void> {
    const running = this.active.get(id)
    if (running) await running.cancel().catch(() => undefined)
  }

  async history(): Promise<HistoryEntry[]> { await this.load(); return [...this.state.history] }
  async clearHistory(): Promise<void> { await this.load(); this.state.history = []; await this.persist() }
  async saveWorkspace(workspace: Workspace): Promise<void> {
    await this.load(); this.state.workspace = workspace; await this.persist()
  }
  async dispose(): Promise<void> {
    await Promise.all([...this.handles.keys()].map((id) => this.disconnect(id)))
  }

  private async ensureDemo(): Promise<void> {
    const existing = this.state.connections.find((item) => item.id === DEMO_ID)
    const demo: StoredConnection = {
      id: DEMO_ID, name: 'Kiwi Shop 예제', engine: 'sqlite', filename: this.demoPath,
      readOnly: false, color: '#86d73f'
    }
    if (existing) Object.assign(existing, demo)
    else this.state.connections.unshift(demo)
    const isNew = !existsSync(this.demoPath)
    const session = await SqliteSession.open(this.demoPath, false)
    try {
      const schema = await session.request<SchemaInfo>({ op: 'schema' })
      if (isNew || !schema.tables.some((table) => table.name === 'customers')) {
        await session.request({ op: 'seed' })
      }
    } finally { await session.dispose() }
    await this.persist()
  }

  private async load(): Promise<void> {
    if (this.loaded) return
    await mkdir(this.dataDir, { recursive: true })
    try {
      const parsed = JSON.parse(await readFile(this.statePath, 'utf8'))
      this.state = { connections: parsed.connections ?? [], history: parsed.history ?? [], workspace: parsed.workspace }
    } catch (error: any) {
      if (error?.code !== 'ENOENT') {
        throw new Error('STATE_READ_FAILED: 연결 설정을 읽을 수 없습니다.', { cause: error })
      }
    }
    this.loaded = true
  }

  private async persist(): Promise<void> {
    this.writeQueue = this.writeQueue.catch(() => undefined).then(async () => {
      await mkdir(this.dataDir, { recursive: true })
      const temporary = `${this.statePath}.${process.pid}.${randomUUID()}.tmp`
      await writeFile(temporary, JSON.stringify(this.state, null, 2), { encoding: 'utf8', mode: 0o600 })
      const waits = [25, 50, 100, 200, 400]
      try {
        for (let attempt = 0; ; attempt += 1) {
          try { await rename(temporary, this.statePath); break }
          catch (error: any) {
            const transient = ['EPERM', 'EACCES', 'EBUSY'].includes(error?.code)
            if (!transient || attempt >= waits.length) throw error
            await delay(waits[attempt])
          }
        }
      } catch (error) {
        await unlink(temporary).catch(() => undefined)
        throw error
      }
    })
    await this.writeQueue
  }

  private publicConnection(item: StoredConnection): Connection {
    const { secret: _secret, ...profile } = item
    return { ...profile, hasPassword: Boolean(item.secret) }
  }

  private readSecret(item: StoredConnection): string | undefined {
    if (!item.secret) return undefined
    if (!this.codec) throw new Error('PASSWORD_DECRYPTION_UNAVAILABLE: OS 암호화 기능을 사용할 수 없습니다.')
    try { return this.codec.decrypt(item.secret) }
    catch { throw new Error('PASSWORD_DECRYPTION_FAILED: 저장한 비밀번호를 읽을 수 없습니다.') }
  }

  private async profile(id: string): Promise<Connection> {
    await this.load()
    const item = this.state.connections.find((connection) => connection.id === id)
    if (!item) throw new Error('CONNECTION_NOT_FOUND: 연결 설정을 찾을 수 없습니다.')
    return { ...this.publicConnection(item), password: this.readSecret(item) }
  }

  private async connected(id: string): Promise<Handle> {
    const handle = this.handles.get(id)
    if (!handle) throw new Error('NOT_CONNECTED: 먼저 데이터베이스에 연결해 주세요.')
    return handle
  }

  private async openRemote(profile: Connection): Promise<RemoteHandle> {
    const common = {
      host: profile.host, port: profile.port, database: profile.database,
      user: profile.username, password: profile.password
    }
    if (profile.engine === 'postgres') {
      const { Client } = await import('pg')
      const client = new Client({
        ...common, connectionTimeoutMillis: 10_000, statement_timeout: 30_000,
        query_timeout: 30_000, ssl: profile.ssl ? { rejectUnauthorized: true } : false
      })
      client.on('error', () => {
        // idle 연결 오류는 다음 작업에서 호출자에게 반환함. EventEmitter의 unhandled error로 앱이 종료되지 않게 소비함.
      })
      await client.connect()
      if (profile.readOnly) await client.query('SET default_transaction_read_only = on')
      return { engine: 'postgres', client, profile }
    }
    if (profile.engine === 'mysql') {
      const mysql = await import('mysql2/promise')
      const client = await mysql.createConnection({
        ...common, connectTimeout: 10_000, rowsAsArray: false,
        supportBigNumbers: true, bigNumberStrings: true, decimalNumbers: false,
        ssl: profile.ssl ? { rejectUnauthorized: true } : undefined
      })
      if (profile.readOnly) await client.query('SET SESSION TRANSACTION READ ONLY')
      return { engine: 'mysql', client, profile }
    }
    throw new Error('UNSUPPORTED_ENGINE: 지원하지 않는 데이터베이스입니다.')
  }

  private async closeRemote(handle: RemoteHandle): Promise<void> {
    await handle.client.end().catch(() => undefined)
  }

  private async remoteVersion(handle: RemoteHandle): Promise<string> {
    if (handle.engine === 'postgres') {
      return (await handle.client.query('SELECT version() AS version')).rows[0].version
    }
    const [rows] = await handle.client.query('SELECT VERSION() AS version')
    return rows[0].version
  }

  private async remoteSchema(handle: RemoteHandle): Promise<SchemaInfo> {
    if (handle.engine === 'postgres') {
      const result = await handle.client.query(
        `SELECT table_schema AS schema, table_name AS name,
                CASE WHEN table_type='VIEW' THEN 'view' ELSE 'table' END AS type
         FROM information_schema.tables
         WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY table_schema, table_name`)
      return { tables: result.rows }
    }
    const [rows] = await handle.client.query(
      `SELECT TABLE_SCHEMA AS \`schema\`, TABLE_NAME AS name,
              CASE WHEN TABLE_TYPE='VIEW' THEN 'view' ELSE 'table' END AS type
       FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() ORDER BY TABLE_NAME`)
    return { tables: rows }
  }

  private async remoteQuery(id: string, handle: RemoteHandle, statements: string[], limit: number): Promise<QueryResult[]> {
    let cancelled = false
    let rejectMysql: ((error: Error) => void) | undefined
    this.active.set(id, { cancel: async () => {
      cancelled = true
      if (handle.engine === 'mysql') {
        try { await this.cancelMysql(handle) }
        catch {
          this.handles.delete(id)
          handle.client.destroy()
        } finally { rejectMysql?.(new Error('QUERY_CANCELLED: 작업이 취소되었습니다.')) }
      } else {
        try { await this.cancelPostgres(handle) }
        catch {
          this.handles.delete(id)
          await handle.client.end().catch(() => undefined)
        }
      }
    } })
    const output: QueryResult[] = []
    try {
      for (const sql of statements) {
        if (cancelled) throw new Error('QUERY_CANCELLED: 작업이 취소되었습니다.')
        const started = performance.now()
        try {
          if (handle.engine === 'postgres') {
            const result = await postgresQueryBounded(handle.client, sql, limit)
            if (cancelled) throw new Error('QUERY_CANCELLED: 작업이 취소되었습니다.')
            output.push({ ...result, sql, durationMs: performance.now() - started })
          } else {
            try {
              const result = await mysqlQueryBounded(handle.client, sql, limit, reject => { rejectMysql = reject })
              if (cancelled) throw new Error('QUERY_CANCELLED: 작업이 취소되었습니다.')
              output.push({ ...result, sql, durationMs: performance.now() - started })
            } finally { rejectMysql = undefined }
          }
        } catch (error) {
          output.push({
            sql, columns: [], rows: [], affectedRows: 0, durationMs: performance.now() - started,
            truncated: false, error: sanitizeError(error).message
          })
          break
        }
      }
      return output
    } finally {
      this.active.delete(id)
    }
  }

  private async cancelPostgres(handle: RemoteHandle): Promise<void> {
    const { Client } = await import('pg')
    const control = new Client({
      host: handle.profile.host, port: handle.profile.port, database: handle.profile.database,
      user: handle.profile.username, password: handle.profile.password,
      connectionTimeoutMillis: 5_000, ssl: handle.profile.ssl ? { rejectUnauthorized: true } : false
    })
    try {
      await control.connect()
      await control.query('SELECT pg_cancel_backend($1)', [handle.client.processID])
    } finally {
      await control.end().catch(() => undefined)
    }
  }

  private async cancelMysql(handle: RemoteHandle): Promise<void> {
    const threadId = Number(handle.client.threadId ?? handle.client.connection?.threadId)
    if (!Number.isSafeInteger(threadId) || threadId <= 0) throw new Error('INVALID_MYSQL_THREAD')
    const mysql = await import('mysql2/promise')
    const control = await mysql.createConnection({
      host: handle.profile.host, port: handle.profile.port, database: handle.profile.database,
      user: handle.profile.username, password: handle.profile.password, connectTimeout: 5_000,
      ssl: handle.profile.ssl ? { rejectUnauthorized: true } : undefined
    })
    try { await control.query({ sql: `KILL QUERY ${threadId}`, timeout: 5_000 }) }
    finally { await control.end().catch(() => undefined) }
  }
}

export function createService(dataDir: string, codec?: SecretCodec): SqlkiwiService {
  return new SqlkiwiService(dataDir, codec)
}

function toCell(value: any): Cell {
  if (value === null || typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return value
  if (typeof value === 'bigint') {
    return value >= BigInt(Number.MIN_SAFE_INTEGER) && value <= BigInt(Number.MAX_SAFE_INTEGER)
      ? Number(value) : value.toString()
  }
  if (value instanceof Date) return value.toISOString()
  if (Buffer.isBuffer(value)) {
    return `0x${value.subarray(0, 32).toString('hex')}${value.length > 32 ? '…' : ''}`
  }
  return JSON.stringify(value)
}

function sanitizeError(value: unknown): Error {
  const raw = value instanceof Error ? value.message : String(value)
  return new Error(raw.replace(/(?:password|pwd)=[^\s;]+/gi, 'password=***').slice(0, 1_000))
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds))
}

function mysqlQueryBounded(client: any, sql: string, limit: number,
  registerAbort: (reject: (error: Error) => void) => void): Promise<Omit<QueryResult, 'sql' | 'durationMs'>> {
  return new Promise((resolve, reject) => {
    registerAbort(reject)
    const rows: Cell[][] = []
    let fields: any[] = []
    let affectedRows = 0
    let truncated = false
    const query = client.connection.query({ sql, rowsAsArray: true, timeout: 30_000 })
    query.on('fields', (value: any[] | undefined) => { fields = Array.isArray(value) ? value : [] })
    query.on('result', (value: any) => {
      if (Array.isArray(value)) {
        if (rows.length < limit) rows.push(value.map(toCell))
        else truncated = true
      } else if (value && typeof value.affectedRows === 'number') affectedRows = value.affectedRows
    })
    query.once('error', reject)
    query.once('end', () => {
      try { resolve({ columns: fields.map((field) => field.name), rows, affectedRows, truncated }) }
      catch (error) { reject(error) }
    })
  })
}

async function postgresQueryBounded(
  client: any,
  sql: string,
  limit: number
): Promise<Omit<QueryResult, 'sql' | 'durationMs'>> {
  const { default: Cursor } = await import('pg-cursor')
  const cursor: any = client.query(new Cursor(sql, [], { rowMode: 'array' }))
  try {
    const { rows, result } = await new Promise<{ rows: any[][]; result: any }>((resolve, reject) => {
      cursor.read(limit + 1, (error: Error | null, rows: any[][], result: any) => {
        if (error) reject(error)
        else resolve({ rows, result })
      })
    })
    return {
      columns: result?.fields?.map((field: any) => field.name) ?? [],
      rows: rows.slice(0, limit).map((row) => row.map(toCell)),
      affectedRows: result?.rowCount ?? 0,
      truncated: rows.length > limit
    }
  } finally {
    await cursor.close().catch(() => undefined)
  }
}

interface WorkerRequest {
  op: 'open' | 'seed' | 'version' | 'schema' | 'tableDetails' | 'query' | 'close'
  filename?: string
  readOnly?: boolean
  table?: TableInfo
  statements?: string[]
  limit?: number
}

class SqliteSession {
  private readonly child: ChildProcess
  private readonly pending = new Map<string, { resolve(value: any): void; reject(error: Error): void; timer: NodeJS.Timeout }>()
  private closed = false

  private constructor() {
    const typescript = import.meta.url.endsWith('.ts')
    const workerUrl = new URL(typescript ? './db-worker.ts' : './db-worker.js', import.meta.url)
    this.child = fork(fileURLToPath(workerUrl), [], {
      execArgv: typescript ? ['--experimental-strip-types'] : [],
      env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' },
      windowsHide: true,
      stdio: ['ignore', 'ignore', 'ignore', 'ipc'],
      serialization: 'advanced'
    })
    this.child.on('message', (message: any) => {
      const pending = this.pending.get(message.id)
      if (!pending) return
      clearTimeout(pending.timer)
      this.pending.delete(message.id)
      if (message.ok) pending.resolve(message.value)
      else pending.reject(new Error(message.error))
    })
    this.child.on('error', (error) => this.rejectAll(error))
    this.child.on('exit', () => this.rejectAll(new Error('QUERY_CANCELLED: SQLite 작업이 종료되었습니다.')))
  }

  static async open(filename: string, readOnly: boolean): Promise<SqliteSession> {
    const session = new SqliteSession()
    try { await session.request({ op: 'open', filename, readOnly }); return session }
    catch (error) { await session.dispose(); throw error }
  }

  request<T>(work: WorkerRequest): Promise<T> {
    if (this.closed) return Promise.reject(new Error('SQLITE_SESSION_CLOSED: 연결이 닫혔습니다.'))
    const id = randomUUID()
    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id)
        reject(new Error('QUERY_TIMEOUT: SQLite 작업 시간이 30초를 넘었습니다.'))
        void this.dispose()
      }, 30_000)
      this.pending.set(id, { resolve, reject, timer })
      this.child.send({ id, work }, (error) => {
        if (!error) return
        clearTimeout(timer)
        this.pending.delete(id)
        reject(error)
      })
    })
  }

  async dispose(): Promise<void> {
    if (this.closed) return
    this.closed = true
    await new Promise<void>((resolve) => {
      if (this.child.exitCode !== null || this.child.signalCode !== null) { resolve(); return }
      const timer = setTimeout(resolve, 1_000)
      this.child.once('exit', () => { clearTimeout(timer); resolve() })
      this.child.kill()
    })
  }

  private rejectAll(error: Error): void {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer)
      pending.reject(error)
    }
    this.pending.clear()
  }
}

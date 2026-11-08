// MySQL 드라이버
// - SQL 실행용 연결과 탐색용 연결을 따로 엶
// - 결과는 mysql2 스트리밍 질의로 받고, 묶음이 차면 소켓 읽기를 멈춤(pause). 더 가져올 때 다시 읽음(resume)
// - 결과를 끝까지 안 읽고 닫으면 KILL QUERY로 서버 실행을 멈춘 뒤 남은 응답을 버림
// - 메타데이터는 DBeaver MySQLCatalog처럼 SHOW와 information_schema를 씀
import mysql from 'mysql2/promise'
import type { FieldPacket, QueryError } from 'mysql2'
import type { ConnectionConfig } from '@shared/types'
import { toRow } from './cell'
import type { Driver, ExecOutcome, RowCursor } from './driver'
import { navChildren, type MetaSource, type NamedItem } from './meta-tree'

// 자료형 번호를 이름으로(mysql2가 Types 상수를 내보내지만 타입 정의에는 빠져 있음)
const TYPE_NAMES: Record<number, string> = Object.fromEntries(
  Object.entries((mysql as unknown as { Types: Record<string, number> }).Types ?? {}).map(([k, v]) => [v, k.toLowerCase()])
)

// DBeaver MySQLDataSource.isSystemCatalog와 같은 목록
const SYSTEM_DB = new Set(['information_schema', 'performance_schema', 'mysql'])

// promise 연결 안의 콜백식 연결(스트리밍과 pause, resume에 씀). 실행 시에는 있지만 타입 정의에 빠져 있어 직접 적음
type CoreConnection = import('mysql2').Connection
const coreOf = (c: mysql.Connection): CoreConnection => (c as unknown as { connection: CoreConnection }).connection

export class MysqlDriver implements Driver, MetaSource {
  readonly kind = 'mysql' as const
  readonly schemaNodeType = 'database' as const
  private main: mysql.Connection | null = null
  private meta: mysql.Connection | null = null
  private mainDead = false

  constructor(
    private readonly config: ConnectionConfig,
    private readonly password: string | undefined
  ) {}

  private open(): Promise<mysql.Connection> {
    const c = this.config
    return mysql.createConnection({
      host: c.host || 'localhost',
      port: c.port || 3306,
      user: c.user || 'root',
      password: this.password,
      database: c.database || undefined,
      connectTimeout: 20_000, // DBeaver MySQL 드라이버 기본 connectTimeout=20000
      charset: 'utf8mb4',
      dateStrings: true, // 날짜를 DB 문자열 그대로
      supportBigNumbers: true,
      bigNumberStrings: true, // BIGINT, DECIMAL을 정밀도 손실 없이 문자열로
      multipleStatements: false // 문장 분리는 앱이 함
    })
  }

  private async openMain(): Promise<mysql.Connection> {
    const main = await this.open()
    main.on('error', () => {
      this.mainDead = true
    })
    if (this.config.readOnly) await main.query('SET SESSION TRANSACTION READ ONLY')
    return main
  }

  async connect(): Promise<void> {
    this.main = await this.openMain()
    this.meta = await this.open()
    this.meta.on('error', () => undefined)
    this.mainDead = false
  }

  async close(): Promise<void> {
    await Promise.allSettled([this.main?.end(), this.meta?.end()])
    this.main = null
    this.meta = null
  }

  async serverVersion(): Promise<string> {
    const rows = await this.metaRows('select version()')
    return `MySQL ${rows[0]?.[0] ?? ''}`.trim()
  }

  private async mainConn(): Promise<mysql.Connection> {
    if (!this.main || this.mainDead) {
      await this.main?.end().catch(() => undefined)
      this.main = await this.openMain()
      this.mainDead = false
    }
    return this.main
  }

  async execute(sql: string, fetchSize: number): Promise<ExecOutcome> {
    const conn = await this.mainConn()
    const stream = new StreamingResult(coreOf(conn), sql, fetchSize, () => this.killMainQuery())
    const head = await stream.waitHead()
    if (head.kind === 'update') return head
    const first = await stream.fetch(fetchSize)
    return { kind: 'rows', columns: head.columns, rows: first.rows, done: first.done, cursor: stream }
  }

  private async killMainQuery(): Promise<void> {
    const id = this.main?.threadId
    if (id && this.meta) await this.meta.query(`KILL QUERY ${Number(id)}`).catch(() => undefined)
  }

  async cancel(): Promise<void> {
    await this.killMainQuery()
  }

  // ---- 메타데이터 ----

  private async metaRows(sql: string, params: unknown[] = []): Promise<unknown[][]> {
    if (!this.meta) throw new Error('연결되어 있지 않음')
    const [rows] = await this.meta.query({ sql, rowsAsArray: true }, params)
    return rows as unknown[][]
  }

  async listSchemas(): Promise<string[]> {
    const rows = await this.metaRows('SHOW DATABASES')
    return rows.map((r) => String(r[0])).filter((d) => !SYSTEM_DB.has(d.toLowerCase()))
  }

  async listRelations(schema: string, kind: 'table' | 'view'): Promise<NamedItem[]> {
    // SHOW FULL TABLES의 두 번째 열(Table_type)에 VIEW가 들어 있으면 뷰
    const rows = await this.metaRows(`SHOW FULL TABLES FROM ${this.quoteIdent(schema)}`)
    return rows
      .filter((r) => (String(r[1]).includes('VIEW') ? kind === 'view' : kind === 'table'))
      .map((r) => ({ name: String(r[0]) }))
      .sort((a, b) => a.name.localeCompare(b.name))
  }

  async listColumns(schema: string, table: string): Promise<NamedItem[]> {
    const rows = await this.metaRows(
      `SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY
         FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION`,
      [schema, table]
    )
    return rows.map((r) => ({
      name: String(r[0]),
      detail: [String(r[1]), r[2] === 'NO' ? 'NOT NULL' : '', r[3] === 'PRI' ? 'PK' : ''].filter(Boolean).join(' ')
    }))
  }

  async listIndexes(schema: string, table: string): Promise<NamedItem[]> {
    const rows = await this.metaRows(
      `SELECT INDEX_NAME, NON_UNIQUE, COLUMN_NAME
         FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
        ORDER BY INDEX_NAME, SEQ_IN_INDEX`,
      [schema, table]
    )
    const map = new Map<string, { unique: boolean; cols: string[] }>()
    for (const r of rows) {
      const name = String(r[0])
      const entry = map.get(name) ?? { unique: Number(r[1]) === 0, cols: [] }
      entry.cols.push(String(r[2]))
      map.set(name, entry)
    }
    return [...map].map(([name, e]) => ({
      name,
      detail: `(${e.cols.join(', ')})${name === 'PRIMARY' ? ' PK' : e.unique ? ' UNIQUE' : ''}`
    }))
  }

  async listForeignKeys(schema: string, table: string): Promise<NamedItem[]> {
    const rows = await this.metaRows(
      `SELECT CONSTRAINT_NAME, COLUMN_NAME, REFERENCED_TABLE_SCHEMA, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
         FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? AND REFERENCED_TABLE_NAME IS NOT NULL
        ORDER BY CONSTRAINT_NAME, ORDINAL_POSITION`,
      [schema, table]
    )
    const map = new Map<string, { cols: string[]; ref: string; refCols: string[] }>()
    for (const r of rows) {
      const name = String(r[0])
      const ref = r[2] === schema ? String(r[3]) : `${r[2]}.${r[3]}`
      const entry = map.get(name) ?? { cols: [], ref, refCols: [] }
      entry.cols.push(String(r[1]))
      entry.refCols.push(String(r[4]))
      map.set(name, entry)
    }
    return [...map].map(([name, e]) => ({
      name,
      detail: `(${e.cols.join(', ')}) REFERENCES ${e.ref}(${e.refCols.join(', ')})`
    }))
  }

  children = (parent: Parameters<Driver['children']>[0]) => navChildren(this, parent)

  async completionSchema(): Promise<{ schema: Record<string, Record<string, string[]>>; defaultSchema?: string }> {
    const rows = await this.metaRows(
      `SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME
         FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA NOT IN ('information_schema', 'performance_schema', 'mysql', 'sys')
        ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
        LIMIT 50000`
    )
    const schema: Record<string, Record<string, string[]>> = {}
    for (const r of rows) ((schema[String(r[0])] ??= {})[String(r[1])] ??= []).push(String(r[2]))
    const cur = await this.metaRows('SELECT DATABASE()')
    return { schema, defaultSchema: (cur[0]?.[0] as string | null) ?? undefined }
  }

  quoteIdent(name: string): string {
    return `\`${name.replace(/`/g, '``')}\``
  }
}

/** mysql2 스트리밍 질의를 RowCursor로 감쌈 */
class StreamingResult implements RowCursor {
  private buffer: unknown[][] = []
  private fields: FieldPacket[] | null = null
  private header: { affectedRows?: number } | null = null
  private ended = false
  private error: Error | null = null
  private paused = false
  private draining = false
  private wake: (() => void) | null = null
  // mysql2의 resume()은 쌓인 패킷을 그 자리에서 처리하므로, 기다리기 전에 온 신호를 기억해 둠
  private signaled = false

  constructor(
    private readonly core: CoreConnection,
    sql: string,
    private readonly highWater: number,
    private readonly kill: () => Promise<void>
  ) {
    const q = core.query({ sql, rowsAsArray: true })
    q.on('fields', (f: FieldPacket[] | undefined) => {
      // 행이 없는 문장(UPDATE 등)에서도 fields 이벤트가 undefined로 옴
      if (Array.isArray(f)) this.fields = f
      this.notify()
    })
    q.on('result', (row: unknown) => {
      if (this.fields === null) {
        this.header = row as { affectedRows?: number } // 행이 없는 문장의 결과(OK 패킷)
      } else if (!this.draining) {
        this.buffer.push(row as unknown[])
        if (this.buffer.length >= this.highWater && !this.paused) {
          this.paused = true
          core.pause()
        }
      }
      this.notify()
    })
    q.on('error', (err: QueryError) => {
      this.error = err
      this.notify()
    })
    q.on('end', () => {
      this.ended = true
      this.notify()
    })
  }

  private notify(): void {
    const w = this.wake
    this.wake = null
    if (w) w()
    else this.signaled = true
  }

  private wait(): Promise<void> {
    if (this.signaled) {
      this.signaled = false
      return Promise.resolve()
    }
    return new Promise((resolve) => {
      this.wake = resolve
    })
  }

  async waitHead(): Promise<{ kind: 'rows'; columns: { name: string; type: string | null }[] } | { kind: 'update'; affectedRows: number | null }> {
    while (!this.fields && !this.header && !this.ended && !this.error) await this.wait()
    if (this.error) throw this.error
    if (this.fields) return { kind: 'rows', columns: this.fields.map((f) => ({ name: f.name, type: TYPE_NAMES[f.columnType ?? f.type ?? -1] ?? null })) }
    return { kind: 'update', affectedRows: this.header?.affectedRows ?? null }
  }

  async fetch(n: number) {
    while (this.buffer.length < n && !this.ended && !this.error) {
      if (this.paused) {
        this.paused = false
        this.core.resume()
      }
      await this.wait()
    }
    if (this.error) throw this.error
    const rows = this.buffer.splice(0, n).map(toRow)
    return { rows, done: this.ended && this.buffer.length === 0 }
  }

  async close(): Promise<void> {
    if (this.ended || this.error) return
    // 남은 행을 다 받지 않고 끝내려면 서버 실행을 멈추고 남은 응답을 버려야 연결을 다시 쓸 수 있음
    this.draining = true
    this.buffer = []
    await this.kill()
    if (this.paused) {
      this.paused = false
      this.core.resume()
    }
    while (!this.ended && !this.error) await this.wait()
  }
}

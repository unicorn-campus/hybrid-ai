// SQLite 드라이버
// - SQL 실행은 별도 프로세스(sqlite-worker, Electron utilityProcess)에서, 탐색은 메인 프로세스의 읽기 전용 연결에서 함
// - 취소하면 실행 프로세스를 끝내고, 다음 실행 때 새로 엶(임시 테이블 같은 세션 상태는 사라짐)
import { utilityProcess, type UtilityProcess } from 'electron'
import workerPath from './sqlite-worker?modulePath'
import type { CellValue, ConnectionConfig, NavNode } from '@shared/types'
import type { Driver, ExecOutcome, RowCursor } from './driver'
import { navChildren, type MetaSource, type NamedItem } from './meta-tree'
import { SqliteEngine, type EngineExec } from './sqlite-engine'

interface Pending {
  resolve: (v: unknown) => void
  reject: (e: Error) => void
}

class WorkerClient {
  private readonly worker: UtilityProcess
  private readonly pending = new Map<number, Pending>()
  private nextId = 1
  /** 끝난 스레드에 보낸 요청은 응답이 오지 않으므로 바로 실패시킴 */
  private dead = false
  readonly ready: Promise<void>

  constructor(file: string, readonly: boolean) {
    this.worker = utilityProcess.fork(workerPath, [file, readonly ? '1' : '0'], { serviceName: 'sqlkiwi-sqlite' })
    this.ready = new Promise((resolve, reject) => {
      this.pending.set(0, { resolve: () => resolve(), reject })
    })
    this.worker.on('message', (m: { id: number; ok: boolean; value?: unknown; error?: string }) => {
      const p = this.pending.get(m.id)
      if (!p) return
      this.pending.delete(m.id)
      if (m.ok) p.resolve(m.value)
      else p.reject(new Error(m.error))
    })
    this.worker.on('error', (type) => this.failAll(new Error(`실행 프로세스 오류: ${type}`)))
    this.worker.on('exit', () => {
      this.dead = true
      this.failAll(new Error('실행을 취소함'))
    })
  }

  private failAll(e: Error): void {
    for (const p of this.pending.values()) p.reject(e)
    this.pending.clear()
  }

  call<T>(op: string, args: Record<string, unknown> = {}): Promise<T> {
    if (this.dead) return Promise.reject(new Error('실행 스레드가 끝남'))
    const id = this.nextId++
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (v: unknown) => void, reject })
      this.worker.postMessage({ id, op, ...args })
    })
  }

  /** 실행 프로세스를 끝냄. 질의가 C 코드 안에서 돌고 있어도 OS가 끝냄 */
  async terminate(): Promise<void> {
    if (this.dead) return
    this.dead = true
    const exited = new Promise<void>((resolve) => this.worker.once('exit', () => resolve()))
    this.worker.kill()
    await Promise.race([exited, new Promise((r) => setTimeout(r, 3000))])
  }
}

export class SqliteDriver implements Driver, MetaSource {
  readonly kind = 'sqlite' as const
  readonly schemaNodeType = null
  readonly fixedSchema = 'main'
  private exec: WorkerClient | null = null
  private meta: SqliteEngine | null = null

  constructor(private readonly config: ConnectionConfig) {}

  private get file(): string {
    if (!this.config.filePath) throw new Error('SQLite 파일 경로가 없음')
    return this.config.filePath
  }

  private async execClient(): Promise<WorkerClient> {
    if (!this.exec) {
      const client = new WorkerClient(this.file, this.config.readOnly)
      try {
        await client.ready
      } catch (e) {
        await client.terminate()
        throw e
      }
      this.exec = client
    }
    return this.exec
  }

  async connect(): Promise<void> {
    // 실행용 연결이 먼저 파일을 만들 수 있게 한 뒤(읽기 전용이 아니면), 탐색용 읽기 전용 연결을 엶
    await this.execClient()
    this.meta = new SqliteEngine(this.file, { readonly: true, fileMustExist: true })
  }

  async close(): Promise<void> {
    if (this.exec) {
      await this.exec.call('close').catch(() => undefined)
      await this.exec.terminate()
      this.exec = null
    }
    this.meta?.close()
    this.meta = null
  }

  async serverVersion(): Promise<string> {
    const row = this.metaEngine().db.prepare('select sqlite_version() as v').get() as { v: string }
    return `SQLite ${row.v}`
  }

  async execute(sql: string, fetchSize: number): Promise<ExecOutcome> {
    const client = await this.execClient()
    const r = await client.call<EngineExec>('exec', { sql, n: fetchSize })
    if (r.kind === 'update') return r
    let done = r.done
    const cursor: RowCursor = {
      async fetch(n) {
        if (done) return { rows: [], done: true }
        const next = await client.call<{ rows: CellValue[][]; done: boolean }>('fetch', { n })
        done = next.done
        return next
      },
      async close() {
        if (done) return
        done = true
        await client.call('closeCursor').catch(() => undefined)
      }
    }
    return { kind: 'rows', columns: r.columns, rows: r.rows, done, cursor }
  }

  async cancel(): Promise<void> {
    // better-sqlite3에는 실행 중단 API가 없어서 작업 스레드를 끝냄
    const client = this.exec
    this.exec = null
    await client?.terminate()
  }

  private metaEngine(): SqliteEngine {
    if (!this.meta) throw new Error('연결되어 있지 않음')
    return this.meta
  }

  async listSchemas(): Promise<string[]> {
    return ['main']
  }
  async listRelations(_schema: string, kind: 'table' | 'view'): Promise<NamedItem[]> {
    return this.metaEngine().listRelations(kind)
  }
  async listColumns(_schema: string, table: string): Promise<NamedItem[]> {
    return this.metaEngine().listColumns(table)
  }
  async listIndexes(_schema: string, table: string): Promise<NamedItem[]> {
    return this.metaEngine().listIndexes(table)
  }
  async listForeignKeys(_schema: string, table: string): Promise<NamedItem[]> {
    return this.metaEngine().listForeignKeys(table)
  }

  children = (parent: NavNode | null) => navChildren(this, parent)

  async completionSchema(): Promise<{ schema: Record<string, Record<string, string[]>>; defaultSchema?: string }> {
    return { schema: { main: this.metaEngine().completionSchema() }, defaultSchema: 'main' }
  }

  quoteIdent(name: string): string {
    return /^[A-Za-z_][A-Za-z0-9_]*$/.test(name) ? name : `"${name.replace(/"/g, '""')}"`
  }
}

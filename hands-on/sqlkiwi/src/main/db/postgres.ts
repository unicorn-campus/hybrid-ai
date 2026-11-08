// PostgreSQL 드라이버
// - SQL 실행용 연결과 탐색용 연결을 따로 엶(DBeaver의 메타 전용 컨텍스트와 같은 취지)
// - 모든 문장을 pg-cursor로 실행해 200행씩 나눠 가져옴. 컬럼 정보와 영향 행 수도 커서 결과에서 얻음
// - 메타데이터 질의는 DBeaver PostgreSchema의 pg_catalog 질의 구조를 참고해 단순화함
import pg from 'pg'
import Cursor from 'pg-cursor'
import type { ConnectionConfig } from '@shared/types'
import { toRow } from './cell'
import type { Driver, ExecOutcome, RowCursor } from './driver'
import { navChildren, type MetaSource, type NamedItem } from './meta-tree'

// 정수와 실수, 불리언만 JS 값으로 바꾸고 나머지(날짜, 10진수, 큰 정수, JSON, 배열)는 DB 문자열 그대로 받음
const NUMBER_OIDS = new Set([21, 23, 26, 700, 701]) // int2, int4, oid, float4, float8
const BOOL_OID = 16
const BYTEA_OID = 17
const typeParsers = {
  getTypeParser(oid: number, format?: string): (v: string) => unknown {
    if (format === 'binary') return pg.types.getTypeParser(oid, 'binary') as (v: string) => unknown
    if (NUMBER_OIDS.has(oid)) return Number
    if (oid === BOOL_OID) return (v: string) => v === 't'
    if (oid === BYTEA_OID) return pg.types.getTypeParser(BYTEA_OID, 'text') as (v: string) => unknown
    return (v: string) => v
  }
}

const SYSTEM_SCHEMA = (s: string): boolean =>
  s === 'pg_catalog' || s.toLowerCase() === 'information_schema' || s.startsWith('pg_')

export class PostgresDriver implements Driver, MetaSource {
  readonly kind = 'postgres' as const
  readonly schemaNodeType = 'schema' as const
  private main: pg.Client | null = null
  private meta: pg.Client | null = null
  private mainDead = false

  constructor(
    private readonly config: ConnectionConfig,
    private readonly password: string | undefined
  ) {}

  private newClient(): pg.Client {
    const c = this.config
    const client = new pg.Client({
      host: c.host || 'localhost',
      port: c.port || 5432,
      database: c.database || 'postgres',
      user: c.user || 'postgres',
      password: this.password,
      connectionTimeoutMillis: 20_000, // DBeaver 기본 연결 제한 20초와 같게
      application_name: 'sqlkiwi',
      types: typeParsers,
      // 읽기 전용 연결: 서버가 쓰기 트랜잭션을 거부함
      options: c.readOnly ? '-c default_transaction_read_only=on' : undefined
    })
    return client
  }

  async connect(): Promise<void> {
    const main = this.newClient()
    main.on('error', () => {
      this.mainDead = true // 서버가 연결을 끊으면 다음 실행 때 다시 연결함
    })
    await main.connect()
    const meta = this.newClient()
    meta.on('error', () => undefined)
    await meta.connect()
    this.main = main
    this.meta = meta
    this.mainDead = false
  }

  async close(): Promise<void> {
    await Promise.allSettled([this.main?.end(), this.meta?.end()])
    this.main = null
    this.meta = null
  }

  async serverVersion(): Promise<string> {
    const r = await this.metaQuery<{ v: string }>('select version() as v')
    return r[0]?.v ?? 'PostgreSQL'
  }

  private async mainClient(): Promise<pg.Client> {
    if (!this.main || this.mainDead) {
      // 끊긴 연결은 같은 설정으로 한 번 다시 연결함(DBeaver의 recover 1회와 같은 취지)
      await this.main?.end().catch(() => undefined)
      const main = this.newClient()
      main.on('error', () => {
        this.mainDead = true
      })
      await main.connect()
      this.main = main
      this.mainDead = false
    }
    return this.main
  }

  async execute(sql: string, fetchSize: number): Promise<ExecOutcome> {
    const client = await this.mainClient()
    const cursor = client.query(new Cursor(sql, undefined, { rowMode: 'array' }))

    const read = (n: number): Promise<{ rows: unknown[][]; result: pg.QueryResult }> =>
      new Promise((resolve, reject) => {
        cursor.read(n, (err, rows, result) => (err ? reject(err) : resolve({ rows: rows as unknown[][], result })))
      })

    const first = await read(fetchSize)
    const fields = first.result.fields ?? []
    if (fields.length === 0) {
      await cursor.close().catch(() => undefined)
      return { kind: 'update', affectedRows: first.result.rowCount ?? null }
    }
    const columns = fields.map((f) => ({ name: f.name, type: typeName(f.dataTypeID) }))
    let done = first.rows.length < fetchSize
    const rowCursor: RowCursor = {
      async fetch(n) {
        if (done) return { rows: [], done: true }
        const next = await read(n)
        done = next.rows.length < n
        return { rows: next.rows.map(toRow), done }
      },
      async close() {
        done = true
        await cursor.close().catch(() => undefined)
      }
    }
    if (done) await cursor.close().catch(() => undefined)
    return { kind: 'rows', columns, rows: first.rows.map(toRow), done, cursor: rowCursor }
  }

  async cancel(): Promise<void> {
    const pid = (this.main as unknown as { processID?: number } | null)?.processID
    if (pid) await this.metaQuery('select pg_cancel_backend($1)', [pid])
  }

  // ---- 메타데이터 ----

  private async metaQuery<T extends object = Record<string, unknown>>(sql: string, params: unknown[] = []): Promise<T[]> {
    if (!this.meta) throw new Error('연결되어 있지 않음')
    const r = await this.meta.query(sql, params)
    return r.rows as T[]
  }

  async listSchemas(): Promise<string[]> {
    // 시스템 스키마(pg_catalog, information_schema, pg_ 접두)는 숨김. DBeaver 기본값과 같음
    const rows = await this.metaQuery<{ nspname: string }>('select nspname from pg_catalog.pg_namespace order by nspname')
    return rows.map((r) => r.nspname).filter((s) => !SYSTEM_SCHEMA(s))
  }

  async listRelations(schema: string, kind: 'table' | 'view'): Promise<NamedItem[]> {
    // relkind: r 일반 테이블, p 파티션 부모, f 외부 테이블, v 뷰, m 구체화 뷰. 파티션 자식은 숨김
    const kinds = kind === 'table' ? ['r', 'p', 'f'] : ['v', 'm']
    const rows = await this.metaQuery<{ relname: string; relkind: string }>(
      `select c.relname, c.relkind
         from pg_catalog.pg_class c
         join pg_catalog.pg_namespace n on n.oid = c.relnamespace
        where n.nspname = $1 and c.relkind = any($2) and not c.relispartition
        order by c.relname`,
      [schema, kinds]
    )
    const label: Record<string, string | undefined> = { p: '파티션', f: '외부', m: '구체화 뷰' }
    return rows.map((r) => ({ name: r.relname, detail: label[r.relkind] }))
  }

  async listColumns(schema: string, table: string): Promise<NamedItem[]> {
    const rows = await this.metaQuery<{ attname: string; type: string; notnull: boolean; pk: boolean }>(
      `select a.attname,
              pg_catalog.format_type(a.atttypid, a.atttypmod) as type,
              a.attnotnull as notnull,
              exists (select 1 from pg_catalog.pg_index i
                       where i.indrelid = c.oid and i.indisprimary and a.attnum = any(i.indkey)) as pk
         from pg_catalog.pg_attribute a
         join pg_catalog.pg_class c on c.oid = a.attrelid
         join pg_catalog.pg_namespace n on n.oid = c.relnamespace
        where n.nspname = $1 and c.relname = $2 and a.attnum > 0 and not a.attisdropped
        order by a.attnum`,
      [schema, table]
    )
    return rows.map((r) => ({ name: r.attname, detail: columnDetail(r.type, r.notnull, r.pk) }))
  }

  async listIndexes(schema: string, table: string): Promise<NamedItem[]> {
    const rows = await this.metaQuery<{ relname: string; uniq: boolean; prim: boolean; cols: string }>(
      `select ic.relname, i.indisunique as uniq, i.indisprimary as prim,
              array_to_string(array(select pg_catalog.pg_get_indexdef(i.indexrelid, k, true)
                                      from generate_series(1, i.indnatts) k order by k), ', ') as cols
         from pg_catalog.pg_index i
         join pg_catalog.pg_class ic on ic.oid = i.indexrelid
         join pg_catalog.pg_class c on c.oid = i.indrelid
         join pg_catalog.pg_namespace n on n.oid = c.relnamespace
        where n.nspname = $1 and c.relname = $2
        order by ic.relname`,
      [schema, table]
    )
    return rows.map((r) => ({ name: r.relname, detail: indexDetail(r.cols, r.uniq, r.prim) }))
  }

  async listForeignKeys(schema: string, table: string): Promise<NamedItem[]> {
    const rows = await this.metaQuery<{ conname: string; def: string }>(
      `select con.conname, pg_catalog.pg_get_constraintdef(con.oid, true) as def
         from pg_catalog.pg_constraint con
         join pg_catalog.pg_class c on c.oid = con.conrelid
         join pg_catalog.pg_namespace n on n.oid = c.relnamespace
        where con.contype = 'f' and n.nspname = $1 and c.relname = $2
        order by con.conname`,
      [schema, table]
    )
    return rows.map((r) => ({ name: r.conname, detail: r.def.replace(/^FOREIGN KEY /, '') }))
  }

  children = (parent: Parameters<Driver['children']>[0]) => navChildren(this, parent)

  async completionSchema(): Promise<{ schema: Record<string, Record<string, string[]>>; defaultSchema?: string }> {
    const rows = await this.metaQuery<{ nspname: string; relname: string; attname: string }>(
      `select n.nspname, c.relname, a.attname
         from pg_catalog.pg_attribute a
         join pg_catalog.pg_class c on c.oid = a.attrelid
         join pg_catalog.pg_namespace n on n.oid = c.relnamespace
        where c.relkind in ('r', 'p', 'f', 'v', 'm') and a.attnum > 0 and not a.attisdropped
          and n.nspname <> 'information_schema' and n.nspname not like 'pg\\_%'
        order by n.nspname, c.relname, a.attnum
        limit 50000`
    )
    const schema: Record<string, Record<string, string[]>> = {}
    for (const r of rows) ((schema[r.nspname] ??= {})[r.relname] ??= []).push(r.attname)
    const cur = await this.metaQuery<{ s: string | null }>('select current_schema() as s')
    return { schema, defaultSchema: cur[0]?.s ?? 'public' }
  }

  quoteIdent(name: string): string {
    return /^[a-z_][a-z0-9_$]*$/.test(name) ? name : `"${name.replace(/"/g, '""')}"`
  }
}

// 자주 보는 자료형 oid만 이름으로 바꿈(나머지는 숫자 대신 null)
const TYPE_NAMES: Record<number, string> = {
  16: 'bool', 17: 'bytea', 20: 'int8', 21: 'int2', 23: 'int4', 25: 'text', 26: 'oid', 114: 'json',
  700: 'float4', 701: 'float8', 1042: 'bpchar', 1043: 'varchar', 1082: 'date', 1083: 'time',
  1114: 'timestamp', 1184: 'timestamptz', 1186: 'interval', 1700: 'numeric', 2950: 'uuid', 3802: 'jsonb'
}
const typeName = (oid: number): string | null => TYPE_NAMES[oid] ?? null

export function columnDetail(type: string, notNull: boolean, pk: boolean): string {
  return [type, notNull ? 'NOT NULL' : '', pk ? 'PK' : ''].filter(Boolean).join(' ')
}

export function indexDetail(cols: string, unique: boolean, primary: boolean): string {
  return `(${cols})${primary ? ' PK' : unique ? ' UNIQUE' : ''}`
}

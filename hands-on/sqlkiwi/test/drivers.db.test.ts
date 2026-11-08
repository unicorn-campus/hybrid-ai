// DB 드라이버 시험. 시험 DB(test-db/compose.yml)가 떠 있어야 함
// 실행: npm run test:db  (better-sqlite3가 Electron용으로 빌드되어 있어 Electron의 Node 모드로 돌림)
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import type { ConnectionConfig } from '../src/shared/types'
import { MysqlDriver } from '../src/main/db/mysql'
import { PostgresDriver } from '../src/main/db/postgres'
import { SqliteEngine } from '../src/main/db/sqlite-engine'
import type { Driver } from '../src/main/db/driver'

const base = { savePassword: false, readOnly: false }
const pgConfig: ConnectionConfig = { ...base, id: 'pg', name: 'pg', kind: 'postgres', host: '127.0.0.1', port: 55432, database: 'kiwi', user: 'kiwi' }
const myConfig: ConnectionConfig = { ...base, id: 'my', name: 'my', kind: 'mysql', host: '127.0.0.1', port: 53306, database: 'kiwi', user: 'kiwi' }

async function drain(d: Driver, sql: string) {
  const out = await d.execute(sql, 200)
  if (out.kind !== 'rows') throw new Error('rows 결과가 아님')
  const rows = [...out.rows]
  let done = out.done
  while (!done) {
    const part = await out.cursor.fetch(200)
    rows.push(...part.rows)
    done = part.done
  }
  return { first: out.rows.length, firstDone: out.done, total: rows.length, columns: out.columns, rows }
}

for (const [label, make, schema] of [
  ['PostgreSQL', () => new PostgresDriver(pgConfig, 'kiwi'), 'shop'],
  ['MySQL', () => new MysqlDriver(myConfig, 'kiwi'), 'kiwi']
] as const) {
  describe(`${label} 드라이버`, () => {
    let d: Driver
    beforeAll(async () => {
      d = make()
      await d.connect()
    })
    afterAll(async () => {
      await d.close()
    })

    it('서버 버전', async () => {
      expect(await d.serverVersion()).toMatch(label === 'MySQL' ? /MySQL 8/ : /PostgreSQL 18/)
    })

    it('200행씩 나눠 가져오고 끝까지 읽으면 500행', async () => {
      const r = await drain(d, `select * from ${label === 'MySQL' ? 'orders' : 'shop.orders'} order by id`)
      expect(r.first).toBe(200)
      expect(r.firstDone).toBe(false)
      expect(r.total).toBe(500)
      expect(r.columns.map((c) => c.name)).toEqual(['id', 'customer_id', 'amount', 'memo', 'ordered_at'])
    })

    it('10진수와 날짜는 문자열, NULL은 null', async () => {
      const r = await drain(d, `select amount, memo, ordered_at from ${label === 'MySQL' ? 'orders' : 'shop.orders'} where id = 7`)
      const [amount, memo, at] = r.rows[0]
      expect(typeof amount).toBe('string')
      expect(memo).toBeNull() // 7의 배수는 memo가 NULL
      expect(String(at)).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/)
    })

    it('중간에 닫은 뒤에도 같은 연결로 다음 문장 실행', async () => {
      const out = await d.execute(`select * from ${label === 'MySQL' ? 'orders' : 'shop.orders'}`, 200)
      if (out.kind !== 'rows') throw new Error()
      await out.cursor.close()
      const r = await drain(d, 'select 1 as one')
      expect(r.rows.map(String)).toEqual(['1']) // MySQL은 정수 리터럴이 BIGINT라 문자열로 옴(정밀도 보존 설계)
    })

    it('행이 없는 문장은 영향 행 수', async () => {
      const tbl = label === 'MySQL' ? 'kiwi_tmp' : 'shop.kiwi_tmp'
      await d.execute(`drop table if exists ${tbl}`, 200)
      await d.execute(`create table ${tbl} (id int)`, 200)
      const ins = await d.execute(`insert into ${tbl} values (1), (2), (3)`, 200)
      expect(ins).toEqual({ kind: 'update', affectedRows: 3 })
      await d.execute(`drop table ${tbl}`, 200)
    })

    it('오류 문장은 예외', async () => {
      await expect(d.execute('select * from no_such_table', 200)).rejects.toThrow()
      const r = await drain(d, 'select 2 as two') // 오류 뒤에도 연결을 계속 씀
      expect(r.rows.map(String)).toEqual(['2'])
    })

    it('탐색 트리: 스키마 > 테이블 > 컬럼, 인덱스, 외래 키', async () => {
      const roots = await d.children(null)
      const s = roots.find((n) => n.label === schema)
      expect(s).toBeDefined()
      expect(roots.some((n) => n.label === 'information_schema')).toBe(false)
      const [tablesFolder, viewsFolder] = await d.children(s!)
      const tables = await d.children(tablesFolder)
      expect(tables.map((t) => t.label)).toEqual(['customers', 'orders'])
      const views = await d.children(viewsFolder)
      expect(views.map((t) => t.label)).toEqual(['customer_totals'])
      const orders = tables.find((t) => t.label === 'orders')!
      const [colF, idxF, fkF] = await d.children(orders)
      const cols = await d.children(colF)
      expect(cols[0].label).toBe('id')
      expect(cols[0].detail).toMatch(/PK/)
      const idx = await d.children(idxF)
      expect(idx.some((i) => i.label === 'orders_customer_idx' && i.detail === '(customer_id)')).toBe(true)
      const fks = await d.children(fkF)
      expect(fks).toHaveLength(1)
      expect(fks[0].detail).toMatch(/\(customer_id\) REFERENCES .*customers\(id\)/)
    })

    it('자동완성 스키마', async () => {
      const c = await d.completionSchema()
      expect(c.schema[schema].orders).toContain('customer_id')
      expect(c.defaultSchema).toBe(label === 'MySQL' ? 'kiwi' : 'public')
    })

    it('실행 중 취소', async () => {
      const sleep = label === 'MySQL' ? 'select sleep(10)' : 'select pg_sleep(10)'
      const started = Date.now()
      const running = d.execute(sleep, 200).then(
        (r) => r,
        (e: Error) => e
      )
      await new Promise((r) => setTimeout(r, 500))
      await d.cancel()
      const result = await running
      expect(Date.now() - started).toBeLessThan(5000)
      // PostgreSQL은 오류(canceling statement), MySQL SLEEP은 1을 돌려주며 끝남
      if (label === 'PostgreSQL') expect(result).toBeInstanceOf(Error)
      const r = await drain(d, 'select 3 as three')
      expect(r.rows.map(String)).toEqual(['3'])
    })
  })
}

describe('읽기 전용 연결', () => {
  it('PostgreSQL 서버가 쓰기를 거부', async () => {
    const d = new PostgresDriver({ ...pgConfig, readOnly: true }, 'kiwi')
    await d.connect()
    await expect(d.execute('create table shop.ro_test (id int)', 200)).rejects.toThrow(/read-only/)
    await d.close()
  })
  it('MySQL 서버가 쓰기를 거부', async () => {
    const d = new MysqlDriver({ ...myConfig, readOnly: true }, 'kiwi')
    await d.connect()
    await expect(d.execute('insert into customers(name) values (\'x\')', 200)).rejects.toThrow(/READ ONLY/i)
    await d.close()
  })
})

describe('SQLite 엔진', () => {
  let dir: string
  let e: SqliteEngine
  beforeAll(() => {
    dir = mkdtempSync(join(tmpdir(), 'sqlkiwi-'))
    e = new SqliteEngine(join(dir, 'test.db'), { readonly: false, fileMustExist: false })
    e.db.exec(`
      create table customers (id integer primary key, name text not null, photo blob);
      create table orders (id integer primary key, customer_id integer references customers(id), amount real);
      create index orders_customer_idx on orders(customer_id);
      create view big_orders as select * from orders where amount > 100;
    `)
    e.db.prepare('insert into customers values (1, ?, ?)').run('고객1', Buffer.from([0xca, 0xfe]))
    const ins = e.db.prepare('insert into orders(customer_id, amount) values (?, ?)')
    for (let i = 1; i <= 450; i++) ins.run(1, i)
  })
  afterAll(() => {
    e.close()
    rmSync(dir, { recursive: true, force: true })
  })

  it('200행씩 가져오기', () => {
    const r = e.execute('select * from orders', 200)
    if (r.kind !== 'rows') throw new Error()
    expect(r.rows).toHaveLength(200)
    expect(r.done).toBe(false)
    expect(e.fetch(200).rows).toHaveLength(200)
    const last = e.fetch(200)
    expect(last.rows).toHaveLength(50)
    expect(last.done).toBe(true)
  })

  it('정수는 문자열로(큰 정수 정밀도 보존), 바이너리는 16진 미리보기', () => {
    const r = e.execute('select id, name, photo, 9007199254740993 as big from customers', 200)
    if (r.kind !== 'rows') throw new Error()
    expect(r.rows[0]).toEqual(['1', '고객1', { kind: 'binary', bytes: 2, preview: 'cafe' }, '9007199254740993'])
  })

  it('영향 행 수', () => {
    expect(e.execute('update orders set amount = amount where id <= 10', 200)).toEqual({ kind: 'update', affectedRows: 10 })
  })

  it('메타데이터', () => {
    expect(e.listRelations('table').map((t) => t.name)).toEqual(['customers', 'orders'])
    expect(e.listRelations('view').map((t) => t.name)).toEqual(['big_orders'])
    expect(e.listColumns('customers')[0]).toEqual({ name: 'id', detail: 'INTEGER PK' })
    expect(e.listIndexes('orders')).toEqual([{ name: 'orders_customer_idx', detail: '(customer_id)' }])
    expect(e.listForeignKeys('orders')).toEqual([{ name: 'fk_0', detail: '(customer_id) REFERENCES customers(id)' }])
    expect(e.completionSchema().orders).toEqual(['id', 'customer_id', 'amount'])
  })
})

import { DatabaseSync } from 'node:sqlite'

interface Work {
  op: 'open' | 'seed' | 'version' | 'schema' | 'tableDetails' | 'query' | 'close'
  filename?: string
  readOnly?: boolean
  table?: { name: string }
  statements?: string[]
  limit?: number
}

let db: DatabaseSync | undefined

function cell(value: unknown): string | number | boolean | null {
  if (value === null || typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return value
  if (typeof value === 'bigint') {
    return value >= BigInt(Number.MIN_SAFE_INTEGER) && value <= BigInt(Number.MAX_SAFE_INTEGER)
      ? Number(value) : value.toString()
  }
  if (value instanceof Uint8Array) {
    const bytes = Buffer.from(value)
    return `0x${bytes.subarray(0, 32).toString('hex')}${bytes.length > 32 ? '…' : ''}`
  }
  return JSON.stringify(value)
}

function execute(work: Work): unknown {
  if (work.op === 'open') {
    db?.close()
    db = new DatabaseSync(work.filename!, {
      readOnly: Boolean(work.readOnly), enableForeignKeyConstraints: true, allowExtension: false,
      timeout: 5_000, readBigInts: true, returnArrays: true
    })
    return { opened: true }
  }
  if (work.op === 'close') { db?.close(); db = undefined; return { closed: true } }
  if (!db) throw new Error('SQLITE_NOT_OPEN')
  if (work.op === 'seed') {
    db.exec(`
      CREATE TABLE IF NOT EXISTS customers(
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, city TEXT
      );
      CREATE TABLE IF NOT EXISTS products(
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, price NUMERIC NOT NULL
      );
      CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id),
        ordered_at TEXT NOT NULL, status TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS order_items(
        order_id INTEGER NOT NULL REFERENCES orders(id), product_id INTEGER NOT NULL REFERENCES products(id),
        quantity INTEGER NOT NULL, unit_price NUMERIC NOT NULL, PRIMARY KEY(order_id, product_id)
      );
      INSERT OR IGNORE INTO customers VALUES
        (1,'김민준','minjun@example.com','서울'),(2,'이서연','seoyeon@example.com','부산'),
        (3,'박지우','jiwoo@example.com','대전'),(4,'최하린','harin@example.com','제주');
      INSERT OR IGNORE INTO products VALUES
        (1,'그린 키위 8입','과일',12900),(2,'골드 키위 6입','과일',14900),
        (3,'키위 잼','가공식품',7800),(4,'키위 주스','음료',4500);
      INSERT OR IGNORE INTO orders VALUES
        (101,1,'2026-10-30 10:15:00','배송완료'),(102,2,'2026-11-01 14:40:00','배송중'),
        (103,1,'2026-11-05 09:20:00','결제완료'),(104,3,'2026-11-06 18:05:00','주문접수');
      INSERT OR IGNORE INTO order_items VALUES
        (101,1,2,12900),(101,3,1,7800),(102,2,1,14900),(103,4,4,4500),(104,1,1,12900);
    `)
    return { created: true }
  }
  if (work.op === 'version') return { version: `SQLite ${db.prepare('SELECT sqlite_version()').get()![0]}` }
  if (work.op === 'schema') {
    const rows = db.prepare(`SELECT '' AS schema, name,
      CASE type WHEN 'view' THEN 'view' ELSE 'table' END AS type
      FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name`).all()
    return { tables: rows.map((row) => ({ schema: row[0], name: row[1], type: row[2] })) }
  }
  if (work.op === 'tableDetails') {
    const name = work.table!.name
    const quotedName = `"${name.replace(/"/g, '""')}"`
    const columns = db.prepare(`PRAGMA table_xinfo(${quotedName})`).all().map((row) => ({
      name: String(row[1]), type: String(row[2] ?? ''), nullable: !row[3],
      primaryKey: Boolean(row[5]), defaultValue: row[4] == null ? null : String(row[4])
    }))
    const record = db.prepare("SELECT sql FROM sqlite_master WHERE name=? AND type IN ('table','view')").get(name)
    return { columns, ddl: String(record?.[0] ?? '') }
  }
  if (work.op === 'query') {
    const results = []
    for (const sql of work.statements ?? []) {
      const started = performance.now()
      try {
        const statement = db.prepare(sql)
        const metadata = statement.columns()
        if (metadata.length) {
          const rows = []
          for (const row of statement.iterate()) {
            rows.push((row as unknown as unknown[]).map(cell))
            if (rows.length > work.limit!) break
          }
          results.push({ sql, columns: metadata.map((item) => item.name), rows: rows.slice(0, work.limit),
            affectedRows: 0, durationMs: performance.now() - started, truncated: rows.length > work.limit! })
        } else {
          const change = statement.run()
          results.push({ sql, columns: [], rows: [], affectedRows: Number(change.changes),
            durationMs: performance.now() - started, truncated: false })
        }
      } catch (error) {
        results.push({ sql, columns: [], rows: [], affectedRows: 0, durationMs: performance.now() - started,
          truncated: false, error: String(error instanceof Error ? error.message : error).slice(0, 1_000) })
        break
      }
    }
    return results
  }
  throw new Error('UNKNOWN_SQLITE_OPERATION')
}

process.on('message', ({ id, work }: { id: string; work: Work }) => {
  try { process.send!({ id, ok: true, value: execute(work) }) }
  catch (error) {
    process.send!({ id, ok: false, error: String(error instanceof Error ? error.message : error).slice(0, 1_000) })
  }
})

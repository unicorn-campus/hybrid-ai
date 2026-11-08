// SQLite 실행 엔진(동기식). 작업 스레드 안에서 SQL 실행용으로, 메인 스레드에서 탐색용(읽기 전용)으로 씀
import Database from 'better-sqlite3'
import type { CellValue, ColumnInfo } from '@shared/types'
import { toRow } from './cell'
import type { NamedItem } from './meta-tree'

export type EngineExec =
  | { kind: 'rows'; columns: ColumnInfo[]; rows: CellValue[][]; done: boolean }
  | { kind: 'update'; affectedRows: number | null }

export class SqliteEngine {
  readonly db: Database.Database
  private iter: Iterator<unknown[]> | null = null

  constructor(file: string, options: { readonly: boolean; fileMustExist: boolean }) {
    this.db = new Database(file, { readonly: options.readonly, fileMustExist: options.fileMustExist })
  }

  execute(sql: string, fetchSize: number): EngineExec {
    this.closeCursor()
    const stmt = this.db.prepare(sql)
    if (!stmt.reader) {
      const info = stmt.run()
      return { kind: 'update', affectedRows: info.changes }
    }
    // 행을 배열로 받고(raw), 큰 정수는 BigInt로 받아 정밀도를 지킴(safeIntegers)
    stmt.raw(true)
    stmt.safeIntegers(true)
    const iter = stmt.iterate() as IterableIterator<unknown[]>
    const columns = stmt.columns().map((c) => ({ name: c.name, type: c.type?.toLowerCase() ?? null }))
    this.iter = iter
    const { rows, done } = this.fetch(fetchSize)
    return { kind: 'rows', columns, rows, done }
  }

  fetch(n: number): { rows: CellValue[][]; done: boolean } {
    const rows: CellValue[][] = []
    if (!this.iter) return { rows, done: true }
    while (rows.length < n) {
      const r = this.iter.next()
      if (r.done) {
        this.iter = null
        return { rows, done: true }
      }
      rows.push(toRow(r.value))
    }
    return { rows, done: false }
  }

  closeCursor(): void {
    this.iter?.return?.()
    this.iter = null
  }

  close(): void {
    this.closeCursor()
    this.db.close()
  }

  // ---- 메타데이터(DBeaver는 JDBC 메타 호출에 맡기지만 sqlkiwi는 sqlite_master와 PRAGMA를 직접 씀) ----

  listRelations(kind: 'table' | 'view'): NamedItem[] {
    const rows = this.db
      .prepare(
        `select name from sqlite_master
          where type = ? and name not like 'sqlite\\_%' escape '\\'
          order by name`
      )
      .all(kind) as { name: string }[]
    return rows.map((r) => ({ name: r.name }))
  }

  listColumns(table: string): NamedItem[] {
    const rows = this.db.prepare('select name, type, "notnull", pk, hidden from pragma_table_xinfo(?)').all(table) as {
      name: string
      type: string
      notnull: number
      pk: number
      hidden: number
    }[]
    return rows
      .filter((r) => r.hidden !== 1)
      .map((r) => ({
        name: r.name,
        detail: [r.type || '(형 없음)', r.notnull ? 'NOT NULL' : '', r.pk ? 'PK' : ''].filter(Boolean).join(' ')
      }))
  }

  listIndexes(table: string): NamedItem[] {
    const list = this.db.prepare('select name, "unique", origin from pragma_index_list(?)').all(table) as {
      name: string
      unique: number
      origin: string
    }[]
    return list
      .filter((i) => !i.name.startsWith('sqlite_autoindex_')) // DBeaver도 자동 인덱스를 숨김
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((i) => {
        const cols = (this.db.prepare('select name from pragma_index_info(?) order by seqno').all(i.name) as { name: string | null }[])
          .map((c) => c.name ?? '(식)')
          .join(', ')
        return { name: i.name, detail: `(${cols})${i.origin === 'pk' ? ' PK' : i.unique ? ' UNIQUE' : ''}` }
      })
  }

  listForeignKeys(table: string): NamedItem[] {
    const rows = this.db.prepare('select id, "table", "from", "to" from pragma_foreign_key_list(?) order by id, seq').all(table) as {
      id: number
      table: string
      from: string
      to: string | null
    }[]
    const map = new Map<number, { ref: string; from: string[]; to: string[] }>()
    for (const r of rows) {
      const e = map.get(r.id) ?? { ref: r.table, from: [], to: [] }
      e.from.push(r.from)
      e.to.push(r.to ?? '(기본 키)')
      map.set(r.id, e)
    }
    // SQLite 외래 키는 이름이 없어서 순번으로 이름을 붙임
    return [...map].map(([id, e]) => ({ name: `fk_${id}`, detail: `(${e.from.join(', ')}) REFERENCES ${e.ref}(${e.to.join(', ')})` }))
  }

  completionSchema(): Record<string, string[]> {
    const tables = this.db
      .prepare(`select name from sqlite_master where type in ('table', 'view') and name not like 'sqlite\\_%' escape '\\'`)
      .all() as { name: string }[]
    const out: Record<string, string[]> = {}
    for (const t of tables) {
      out[t.name] = (this.db.prepare('select name from pragma_table_info(?)').all(t.name) as { name: string }[]).map((c) => c.name)
    }
    return out
  }
}

// 연결 세션 관리
// - 연결마다 드라이버 하나를 열어 두고, SQL 실행은 한 번에 하나씩(잠금) 처리함
// - 결과를 다 읽지 않은 커서는 resultId로 보관해 "더 가져오기"에 씀. 새 실행 전에 이전 커서를 닫음
import { randomUUID } from 'node:crypto'
import { performance } from 'node:perf_hooks'
import {
  FETCH_SIZE,
  type CellValue,
  type ConnectionConfig,
  type ConnectionInput,
  type NavNode,
  type StatementResult
} from '@shared/types'
import { firstKeyword } from '@shared/sql-split'
import type { Driver, RowCursor } from './db/driver'
import { MysqlDriver } from './db/mysql'
import { PostgresDriver } from './db/postgres'
import { SqliteDriver } from './db/sqlite'
import { getConnection, getPassword } from './store/connections'

export const NEED_PASSWORD = 'NEED_PASSWORD'

interface Session {
  config: ConnectionConfig
  driver: Driver
  results: Map<string, RowCursor>
  lock: Promise<unknown>
}

const sessions = new Map<string, Session>()
const resultOwner = new Map<string, string>()

function createDriver(config: ConnectionConfig, password: string | undefined): Driver {
  switch (config.kind) {
    case 'postgres':
      return new PostgresDriver(config, password)
    case 'mysql':
      return new MysqlDriver(config, password)
    case 'sqlite':
      return new SqliteDriver(config)
  }
}

/** 같은 세션의 실행 작업을 순서대로 처리함 */
function serialize<T>(s: Session, job: () => Promise<T>): Promise<T> {
  const run = s.lock.then(job, job)
  s.lock = run.catch(() => undefined)
  return run
}

function session(id: string): Session {
  const s = sessions.get(id)
  if (!s) throw new Error('연결되어 있지 않음. 먼저 연결하십시오')
  return s
}

export async function testConnection(input: ConnectionInput): Promise<{ version: string; elapsedMs: number }> {
  const start = performance.now()
  const password = input.password ?? (input.savePassword ? getPassword(input.id) : undefined)
  const driver = createDriver(input, password)
  try {
    await driver.connect()
    const version = await driver.serverVersion()
    return { version, elapsedMs: Math.round(performance.now() - start) }
  } finally {
    await driver.close().catch(() => undefined)
  }
}

export async function connect(id: string, password?: string): Promise<{ version: string }> {
  const existing = sessions.get(id)
  if (existing) return { version: await existing.driver.serverVersion() }
  const config = getConnection(id)
  if (!config) throw new Error('연결 설정을 찾지 못함')
  let pwd = password
  if (pwd === undefined && config.kind !== 'sqlite') {
    pwd = config.savePassword ? getPassword(id) : undefined
    // 비밀번호를 저장하지 않은 연결은 화면에서 물어봄(DBeaver도 연결할 때 물음)
    if (pwd === undefined && !config.savePassword) throw new Error(NEED_PASSWORD)
  }
  const driver = createDriver(config, pwd)
  await driver.connect()
  sessions.set(id, { config, driver, results: new Map(), lock: Promise.resolve() })
  return { version: await driver.serverVersion() }
}

export async function disconnect(id: string): Promise<void> {
  const s = sessions.get(id)
  if (!s) return
  sessions.delete(id)
  for (const rid of s.results.keys()) resultOwner.delete(rid)
  await s.driver.close().catch(() => undefined)
}

export async function disconnectAll(): Promise<void> {
  await Promise.allSettled([...sessions.keys()].map(disconnect))
}

export function isConnected(id: string): boolean {
  return sessions.has(id)
}

// 읽기 전용 연결에서 앱이 먼저 막는 문장(DB 쪽 읽기 전용 설정과 함께 이중으로 막음)
const WRITE_KEYWORDS = new Set([
  'INSERT', 'UPDATE', 'DELETE', 'MERGE', 'UPSERT', 'REPLACE', 'CREATE', 'DROP', 'ALTER', 'TRUNCATE',
  'RENAME', 'GRANT', 'REVOKE', 'COMMENT', 'VACUUM', 'REINDEX', 'ATTACH', 'DETACH'
])

async function closeResults(s: Session): Promise<void> {
  const open = [...s.results.entries()]
  s.results.clear()
  for (const [rid, cursor] of open) {
    resultOwner.delete(rid)
    await cursor.close().catch(() => undefined)
  }
}

/**
 * 문장 하나를 실행함
 * @param keepCursor 결과를 더 가져올 수 있게 커서를 남길지(스크립트 실행 중간 결과는 첫 묶음만 남기고 닫음)
 */
export function execute(connectionId: string, sql: string, keepCursor: boolean): Promise<StatementResult> {
  const s = session(connectionId)
  return serialize(s, async () => {
    if (keepCursor) await closeResults(s)
    if (s.config.readOnly && WRITE_KEYWORDS.has(firstKeyword(sql))) {
      throw new Error('읽기 전용 연결이라 데이터를 바꾸는 문장은 실행하지 않음')
    }
    const start = performance.now()
    const out = await s.driver.execute(sql, FETCH_SIZE)
    const elapsedMs = Math.round(performance.now() - start)
    if (out.kind === 'update') return { sql, elapsedMs, result: out }

    const resultId = randomUUID()
    if (!out.done && keepCursor) {
      s.results.set(resultId, out.cursor)
      resultOwner.set(resultId, connectionId)
    } else if (!out.done) {
      await out.cursor.close().catch(() => undefined)
    }
    return {
      sql,
      elapsedMs,
      result: { kind: 'rows', resultId, columns: out.columns, rows: out.rows, hasMore: !out.done, canFetchMore: !out.done && keepCursor }
    }
  })
}

export function fetchMore(resultId: string, all = false): Promise<{ rows: CellValue[][]; hasMore: boolean }> {
  const connId = resultOwner.get(resultId)
  if (!connId) return Promise.resolve({ rows: [], hasMore: false })
  const s = session(connId)
  return serialize(s, async () => {
    const cursor = s.results.get(resultId)
    if (!cursor) return { rows: [], hasMore: false }
    const rows: CellValue[][] = []
    let done = false
    // "모두 가져오기"는 묶음을 반복해서 끝까지 읽음
    do {
      const part = await cursor.fetch(FETCH_SIZE)
      rows.push(...part.rows)
      done = part.done
    } while (all && !done)
    if (done) {
      s.results.delete(resultId)
      resultOwner.delete(resultId)
    }
    return { rows, hasMore: !done }
  })
}

export async function closeResult(resultId: string): Promise<void> {
  const connId = resultOwner.get(resultId)
  if (!connId) return
  const s = session(connId)
  await serialize(s, async () => {
    const cursor = s.results.get(resultId)
    s.results.delete(resultId)
    resultOwner.delete(resultId)
    await cursor?.close().catch(() => undefined)
  })
}

/** 실행 중인 문장 취소. 잠금을 기다리지 않고 바로 보냄 */
export async function cancel(connectionId: string): Promise<void> {
  const s = sessions.get(connectionId)
  if (s) await s.driver.cancel()
}

export function children(connectionId: string, parent: NavNode | null): Promise<NavNode[]> {
  return session(connectionId).driver.children(parent)
}

export function completionSchema(connectionId: string) {
  return session(connectionId).driver.completionSchema()
}

export function quoteIdent(connectionId: string, name: string): string {
  return session(connectionId).driver.quoteIdent(name)
}

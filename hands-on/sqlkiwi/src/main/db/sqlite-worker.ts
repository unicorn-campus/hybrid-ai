// SQLite SQL 실행 프로세스 (Electron utilityProcess)
// better-sqlite3는 동기식이고 실행 중단 API(sqlite3_interrupt)가 없음.
// 작업 스레드(worker_threads)는 C 코드 안에서 도는 질의를 끊지 못해서, 실행을 별도 프로세스로 옮김.
// 취소는 메인 쪽에서 이 프로세스를 끝내는(kill) 방식으로 처리함
import { SqliteEngine } from './sqlite-engine'

interface Request {
  id: number
  op: 'exec' | 'fetch' | 'closeCursor' | 'close'
  sql?: string
  n?: number
}

const [file, readonlyFlag] = process.argv.slice(-2)
const port = process.parentPort

let engine: SqliteEngine | null = null
let openError: string | null = null
try {
  engine = new SqliteEngine(file, { readonly: readonlyFlag === '1', fileMustExist: readonlyFlag === '1' })
} catch (e) {
  openError = e instanceof Error ? e.message : String(e)
}

port.postMessage({ id: 0, ok: openError === null, error: openError ?? undefined })

port.on('message', (event) => {
  const req = event.data as Request
  try {
    if (!engine) throw new Error(openError ?? 'DB 파일을 열지 못함')
    let value: unknown
    switch (req.op) {
      case 'exec':
        value = engine.execute(req.sql!, req.n!)
        break
      case 'fetch':
        value = engine.fetch(req.n!)
        break
      case 'closeCursor':
        engine.closeCursor()
        break
      case 'close':
        engine.close()
        engine = null
        break
    }
    port.postMessage({ id: req.id, ok: true, value })
  } catch (e) {
    port.postMessage({ id: req.id, ok: false, error: e instanceof Error ? e.message : String(e) })
  }
})

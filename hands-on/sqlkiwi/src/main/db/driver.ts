// DB 종류마다 다른 부분을 감추는 공통 틀
import type { CellValue, ColumnInfo, CompletionSchema, DbKind, NavNode } from '@shared/types'

/** 결과 행을 조금씩 꺼내는 커서. DBeaver처럼 처음엔 한 묶음(200행)만 가져오고 필요할 때 더 가져옴 */
export interface RowCursor {
  /** 최대 n행을 가져옴. done이 true면 더 이상 행이 없음 */
  fetch(n: number): Promise<{ rows: CellValue[][]; done: boolean }>
  close(): Promise<void>
}

export type ExecOutcome =
  | { kind: 'rows'; columns: ColumnInfo[]; rows: CellValue[][]; done: boolean; cursor: RowCursor }
  | { kind: 'update'; affectedRows: number | null }

export interface Driver {
  readonly kind: DbKind
  /** SQL 실행용 연결과 탐색용 연결을 엶(DBeaver도 메타데이터 읽기용 연결을 따로 씀) */
  connect(): Promise<void>
  close(): Promise<void>
  /** 서버 이름과 버전(연결 시험 결과 표시용) */
  serverVersion(): Promise<string>
  /** 문장 하나를 실행하고 첫 묶음(fetchSize행)까지 가져옴 */
  execute(sql: string, fetchSize: number): Promise<ExecOutcome>
  /** 실행 중인 문장을 멈춤 */
  cancel(): Promise<void>
  /** 탐색 트리: parent가 null이면 최상위 노드 */
  children(parent: NavNode | null): Promise<NavNode[]>
  /** 자동완성용 스키마 요약 */
  completionSchema(): Promise<{ schema: CompletionSchema; defaultSchema?: string }>
  /** 식별자를 이 DB 규칙으로 감쌈 */
  quoteIdent(name: string): string
}

/** 메모리에 이미 다 있는 행을 커서처럼 돌려줌 */
export function arrayCursor(rows: CellValue[][]): RowCursor {
  let pos = 0
  return {
    async fetch(n) {
      const part = rows.slice(pos, pos + n)
      pos += part.length
      return { rows: part, done: pos >= rows.length }
    },
    async close() {
      pos = rows.length
    }
  }
}

// main, preload, renderer가 함께 쓰는 자료형

export type DbKind = 'sqlite' | 'postgres' | 'mysql'

/** 저장되는 연결 설정. 비밀번호는 여기에 넣지 않고 따로 암호화해 저장함 */
export interface ConnectionConfig {
  id: string
  name: string
  kind: DbKind
  /** SQLite 전용: DB 파일 경로 */
  filePath?: string
  host?: string
  port?: number
  database?: string
  user?: string
  /** 비밀번호를 저장할지 여부(저장하면 OS 보안 저장소로 암호화) */
  savePassword: boolean
  /** 읽기 전용 연결: 데이터를 바꾸는 문장을 DB 쪽에서 막음 */
  readOnly: boolean
}

/** 연결 저장 또는 시험 때 화면에서 넘기는 값. password는 이때만 오감 */
export interface ConnectionInput extends ConnectionConfig {
  password?: string
}

export interface ColumnInfo {
  name: string
  /** DB가 알려 준 자료형 이름(모르면 null) */
  type: string | null
}

/** 셀 값은 화면으로 넘기기 전에 표시 가능한 형태로 바꿈 */
export type CellValue =
  | null
  | string
  | number
  | boolean
  | { kind: 'binary'; bytes: number; preview: string }

export interface RowsResult {
  kind: 'rows'
  resultId: string
  columns: ColumnInfo[]
  rows: CellValue[][]
  /** 아직 가져오지 않은 행이 더 있는지 */
  hasMore: boolean
  /** 더 가져오기가 가능한지(스크립트 실행의 중간 결과는 첫 묶음만 보여 주고 커서를 닫음) */
  canFetchMore: boolean
}

export interface UpdateResult {
  kind: 'update'
  /** 영향받은 행 수(알 수 없으면 null) */
  affectedRows: number | null
}

export interface StatementResult {
  /** 실행한 문장(화면 표시용) */
  sql: string
  elapsedMs: number
  result: RowsResult | UpdateResult
}

export interface ExecuteError {
  sql: string
  message: string
  /** 오류가 난 문장의 편집기 시작 위치(알면) */
  offset?: number
}

/** 탐색 트리 노드 */
export type NavNodeType =
  | 'database'
  | 'schema'
  | 'folder-tables'
  | 'folder-views'
  | 'table'
  | 'view'
  | 'folder-columns'
  | 'folder-indexes'
  | 'folder-fks'
  | 'column'
  | 'index'
  | 'fk'

export interface NavNode {
  type: NavNodeType
  label: string
  /** 회색 보조 글(자료형, 인덱스 컬럼 등) */
  detail?: string
  /** 루트부터 이 노드까지의 이름 경로. 자식 요청 때 그대로 돌려줌 */
  path: string[]
  hasChildren: boolean
}

/** 자동완성용 스키마 요약: { 스키마: { 테이블: [컬럼] } } */
export type CompletionSchema = Record<string, Record<string, string[]>>

export interface QueryRequest {
  connectionId: string
  sql: string
  /** 편집기에서 이 문장이 시작하는 위치(오류 위치 표시용) */
  offset: number
}

/** 결과 한 번에 가져오는 행 수 (DBeaver 기본값 200과 같게 둠) */
export const FETCH_SIZE = 200

/** 결과를 받는 쪽에서 쓰는 응답 */
export type Ok<T> = { ok: true; value: T }
export type Fail = { ok: false; error: string }
export type Reply<T> = Ok<T> | Fail

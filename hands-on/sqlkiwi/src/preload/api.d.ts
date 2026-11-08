// preload가 화면에 열어 주는 API의 자료형(화면 코드와 preload가 함께 씀)
import type {
  CellValue,
  CompletionSchema,
  ConnectionConfig,
  ConnectionInput,
  NavNode,
  Reply,
  StatementResult
} from '../shared/types'

export interface KiwiApi {
  connections: {
    list(): Promise<Reply<ConnectionConfig[]>>
    save(input: ConnectionInput): Promise<Reply<ConnectionConfig>>
    remove(id: string): Promise<Reply<void>>
    test(input: ConnectionInput): Promise<Reply<{ version: string; elapsedMs: number }>>
    canStorePasswords(): Promise<Reply<boolean>>
  }
  session: {
    connect(id: string, password?: string): Promise<Reply<{ version: string }>>
    disconnect(id: string): Promise<Reply<void>>
    isConnected(id: string): Promise<Reply<boolean>>
  }
  meta: {
    children(id: string, parent: NavNode | null): Promise<Reply<NavNode[]>>
    completion(id: string): Promise<Reply<{ schema: CompletionSchema; defaultSchema?: string }>>
    quote(id: string, name: string): Promise<Reply<string>>
  }
  query: {
    execute(id: string, sql: string, keepCursor: boolean): Promise<Reply<StatementResult>>
    fetchMore(resultId: string, all: boolean): Promise<Reply<{ rows: CellValue[][]; hasMore: boolean }>>
    close(resultId: string): Promise<Reply<void>>
    cancel(id: string): Promise<Reply<void>>
  }
  dialog: {
    openSqlite(): Promise<Reply<string | null>>
    newSqlite(): Promise<Reply<string | null>>
  }
}

declare global {
  interface Window {
    kiwi: KiwiApi
  }
}

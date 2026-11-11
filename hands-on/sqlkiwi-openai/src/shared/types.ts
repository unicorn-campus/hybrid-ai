export type Engine = 'sqlite' | 'postgres' | 'mysql'
export interface Connection {
  id: string
  name: string
  engine: Engine
  host?: string
  port?: number
  database?: string
  username?: string
  password?: string
  hasPassword?: boolean
  filename?: string
  readOnly?: boolean
  color?: string
  ssl?: boolean
}
export interface TableInfo { schema: string; name: string; type: 'table' | 'view' }
export interface ColumnInfo { name: string; type: string; nullable: boolean; primaryKey: boolean; defaultValue?: string | null }
export interface SchemaInfo { tables: TableInfo[] }
export interface TableDetails { columns: ColumnInfo[]; ddl: string }
export type Cell = string | number | boolean | null
export interface QueryResult {
  sql: string
  columns: string[]
  rows: Cell[][]
  affectedRows: number
  durationMs: number
  truncated: boolean
  error?: string
}
export interface HistoryEntry {
  id: string; connectionId: string; connectionName: string; sql: string
  executedAt: string; durationMs: number; rowCount: number; success: boolean; error?: string
}
export interface WorkspaceTab { id: string; title: string; sql: string; connectionId: string | null }
export interface Workspace { tabs: WorkspaceTab[]; activeTabId: string; theme: 'dark' | 'light' }
export interface Bootstrap { connections: Connection[]; history: HistoryEntry[]; workspace?: Workspace; demoId: string }
export interface QueryRequest { connectionId: string; sql: string; limit?: number; allowDangerous?: boolean }
export interface SqlkiwiAPI {
  bootstrap(): Promise<Bootstrap>
  saveConnection(connection: Connection): Promise<Connection>
  deleteConnection(id: string): Promise<void>
  testConnection(connection: Connection): Promise<{ version: string }>
  connect(id: string): Promise<{ version: string; schema: SchemaInfo }>
  disconnect(id: string): Promise<void>
  schema(id: string): Promise<SchemaInfo>
  tableDetails(id: string, table: TableInfo): Promise<TableDetails>
  query(request: QueryRequest): Promise<QueryResult[]>
  cancel(id: string): Promise<void>
  history(): Promise<HistoryEntry[]>
  clearHistory(): Promise<void>
  saveWorkspace(workspace: Workspace): Promise<void>
  openDatabase(): Promise<string | null>
  openSql(): Promise<{ name: string; sql: string } | null>
  saveSql(sql: string, name?: string): Promise<boolean>
  exportCsv(columns: string[], rows: Cell[][]): Promise<boolean>
}
declare global { interface Window { sqlkiwi: SqlkiwiAPI } }

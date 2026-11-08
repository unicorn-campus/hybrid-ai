// 탐색 트리 모양은 DB와 상관없이 같게 둠(DBeaver의 plugin.xml <tree> 선언을 단순화한 것)
//
//   (스키마 또는 DB)            PostgreSQL 스키마, MySQL DB. SQLite는 이 층 없이 'main' 하나
//     테이블 폴더 > 테이블 > 컬럼 폴더, 인덱스 폴더, 외래 키 폴더
//     뷰 폴더     > 뷰     > 컬럼 폴더
//
// 노드를 펼칠 때 그 아래 한 층만 읽음(지연 로딩). 캐시는 화면 쪽에서 둠
import type { NavNode } from '@shared/types'

export interface NamedItem {
  name: string
  detail?: string
}

/** DB별로 채워 넣는 메타데이터 질의 */
export interface MetaSource {
  /** 스키마 층 이름표. null이면 스키마 층이 없음(SQLite) */
  readonly schemaNodeType: 'schema' | 'database' | null
  /** 스키마 층이 없을 때 쓰는 고정 스키마 이름 */
  readonly fixedSchema?: string
  listSchemas(): Promise<string[]>
  listRelations(schema: string, kind: 'table' | 'view'): Promise<NamedItem[]>
  listColumns(schema: string, table: string): Promise<NamedItem[]>
  listIndexes(schema: string, table: string): Promise<NamedItem[]>
  listForeignKeys(schema: string, table: string): Promise<NamedItem[]>
}

const folder = (type: NavNode['type'], label: string, path: string[]): NavNode => ({
  type,
  label,
  path,
  hasChildren: true
})

function schemaFolders(schema: string): NavNode[] {
  return [folder('folder-tables', '테이블', [schema]), folder('folder-views', '뷰', [schema])]
}

export async function navChildren(meta: MetaSource, parent: NavNode | null): Promise<NavNode[]> {
  if (parent === null) {
    if (meta.schemaNodeType === null) return schemaFolders(meta.fixedSchema ?? 'main')
    const schemas = await meta.listSchemas()
    return schemas.map((s) => ({ type: meta.schemaNodeType!, label: s, path: [s], hasChildren: true }))
  }

  const [schema, table] = parent.path
  switch (parent.type) {
    case 'schema':
    case 'database':
      return schemaFolders(schema)
    case 'folder-tables':
    case 'folder-views': {
      const kind = parent.type === 'folder-tables' ? 'table' : 'view'
      const items = await meta.listRelations(schema, kind)
      return items.map((t) => ({ type: kind, label: t.name, detail: t.detail, path: [schema, t.name], hasChildren: true }))
    }
    case 'table':
      return [
        folder('folder-columns', '컬럼', [schema, table]),
        folder('folder-indexes', '인덱스', [schema, table]),
        folder('folder-fks', '외래 키', [schema, table])
      ]
    case 'view':
      return [folder('folder-columns', '컬럼', [schema, table])]
    case 'folder-columns':
      return leaves('column', await meta.listColumns(schema, table), schema, table)
    case 'folder-indexes':
      return leaves('index', await meta.listIndexes(schema, table), schema, table)
    case 'folder-fks':
      return leaves('fk', await meta.listForeignKeys(schema, table), schema, table)
    default:
      return []
  }
}

function leaves(type: NavNode['type'], items: NamedItem[], schema: string, table: string): NavNode[] {
  return items.map((i) => ({ type, label: i.name, detail: i.detail, path: [schema, table, i.name], hasChildren: false }))
}

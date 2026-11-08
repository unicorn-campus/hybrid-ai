// 왼쪽 탐색 트리: 연결 > (스키마 또는 DB) > 테이블과 뷰 폴더 > 테이블 > 컬럼, 인덱스, 외래 키
// 노드는 펼칠 때 한 층만 읽고(지연 로딩) 결과를 보관함. 새로고침은 그 노드 아래만 다시 읽음
import { useCallback, useState } from 'react'
import type { ConnectionConfig, NavNode } from '@shared/types'
import { errorText, kiwi, unwrap } from '../api'

interface NodeState {
  expanded: boolean
  loading: boolean
  children?: NavNode[]
  error?: string
}

interface Props {
  connections: ConnectionConfig[]
  connected: Set<string>
  activeConnectionId: string | null
  onSelectConnection(id: string): void
  /** 연결이 안 되어 있으면 연결함. 성공하면 true */
  ensureConnected(id: string): Promise<boolean>
  onDisconnect(id: string): void
  onNew(): void
  onEdit(c: ConnectionConfig): void
  onDelete(c: ConnectionConfig): void
  onOpenEditor(id: string): void
  onOpenRelation(id: string, node: NavNode): void
}

const ICON: Record<NavNode['type'], string> = {
  database: '🛢',
  schema: '◫',
  'folder-tables': '▤',
  'folder-views': '◩',
  table: '▦',
  view: '◪',
  'folder-columns': '☰',
  'folder-indexes': '⚡',
  'folder-fks': '⇢',
  column: '·',
  index: '⚡',
  fk: '⇢'
}

const KIND_SHORT = { sqlite: 'SL', postgres: 'PG', mysql: 'MY' } as const

const keyOf = (connId: string, node: NavNode | null) =>
  node ? `${connId}|${node.type}|${node.path.join('\u0001')}` : `${connId}|root`

export function Navigator(props: Props) {
  const [nodes, setNodes] = useState<Record<string, NodeState>>({})

  const patch = (key: string, p: Partial<NodeState>) =>
    setNodes((all) => ({ ...all, [key]: { ...(all[key] ?? { expanded: false, loading: false }), ...p } }))

  const load = useCallback(async (connId: string, node: NavNode | null) => {
    const key = keyOf(connId, node)
    patch(key, { expanded: true, loading: true, error: undefined })
    try {
      const children = await unwrap(kiwi.meta.children(connId, node))
      patch(key, { loading: false, children })
    } catch (e) {
      patch(key, { loading: false, error: errorText(e) })
    }
  }, [])

  const toggle = async (connId: string, node: NavNode | null) => {
    const key = keyOf(connId, node)
    const st = nodes[key]
    if (st?.expanded) {
      patch(key, { expanded: false })
      return
    }
    if (node === null && !(await props.ensureConnected(connId))) return
    if (st?.children) patch(key, { expanded: true })
    else await load(connId, node)
  }

  /** 노드와 그 아래 캐시를 지우고 다시 읽음 */
  const refresh = async (connId: string, node: NavNode | null) => {
    const prefix = keyOf(connId, node)
    setNodes((all) => Object.fromEntries(Object.entries(all).filter(([k]) => k === prefix || !k.startsWith(`${connId}|`) || !isUnder(k, prefix))))
    await load(connId, node)
  }

  const renderNode = (connId: string, node: NavNode, depth: number) => {
    const key = keyOf(connId, node)
    const st = nodes[key]
    const openable = node.type === 'table' || node.type === 'view'
    return (
      <li key={key}>
        <div
          className="tree-row"
          style={{ paddingLeft: 8 + depth * 14 }}
          onClick={() => node.hasChildren && toggle(connId, node)}
          onDoubleClick={() => openable && props.onOpenRelation(connId, node)}
          title={openable ? '두 번 누르면 데이터 보기' : node.detail}
        >
          <span className="twisty">{node.hasChildren ? (st?.expanded ? '▾' : '▸') : ''}</span>
          <span className={`node-icon ${node.type}`}>{ICON[node.type]}</span>
          <span className="node-label">{node.label}</span>
          {node.detail && <span className="node-detail">{node.detail}</span>}
          {st?.loading && <span className="spinner" aria-label="읽는 중" />}
          {node.hasChildren && st?.expanded && !st.loading && (
            <button
              className="row-action"
              title="새로고침"
              onClick={(e) => {
                e.stopPropagation()
                void refresh(connId, node)
              }}
            >
              ↻
            </button>
          )}
        </div>
        {st?.expanded && renderChildren(connId, st, depth + 1)}
      </li>
    )
  }

  const renderChildren = (connId: string, st: NodeState, depth: number) => {
    if (st.error) return <div className="tree-error" style={{ paddingLeft: 8 + depth * 14 }}>{st.error}</div>
    if (!st.children) return null
    if (st.children.length === 0) return <div className="tree-empty" style={{ paddingLeft: 22 + depth * 14 }}>(없음)</div>
    return <ul>{st.children.map((c) => renderNode(connId, c, depth))}</ul>
  }

  return (
    <aside className="navigator">
      <div className="pane-header">
        <span>데이터베이스</span>
        <button className="ghost" onClick={props.onNew} title="새 연결">
          + 새 연결
        </button>
      </div>
      {props.connections.length === 0 && (
        <div className="empty-hint">
          <p>아직 연결이 없음</p>
          <button className="primary" onClick={props.onNew}>
            첫 연결 만들기
          </button>
        </div>
      )}
      <ul className="tree">
        {props.connections.map((c) => {
          const key = keyOf(c.id, null)
          const st = nodes[key]
          const isConn = props.connected.has(c.id)
          return (
            <li key={c.id}>
              <div
                className={`tree-row conn ${props.activeConnectionId === c.id ? 'active' : ''}`}
                onClick={() => {
                  props.onSelectConnection(c.id)
                  void toggle(c.id, null)
                }}
                onDoubleClick={() => props.onOpenEditor(c.id)}
                title={c.kind === 'sqlite' ? c.filePath : `${c.user ?? ''}@${c.host ?? ''}:${c.port ?? ''}/${c.database ?? ''}`}
              >
                <span className="twisty">{st?.expanded ? '▾' : '▸'}</span>
                <span className={`db-badge ${c.kind}`}>{KIND_SHORT[c.kind]}</span>
                <span className="node-label">{c.name}</span>
                {c.readOnly && <span className="tag">읽기 전용</span>}
                <span className={`dot ${isConn ? 'on' : ''}`} title={isConn ? '연결됨' : '연결 안 됨'} />
                {st?.loading && <span className="spinner" />}
                <span className="row-actions">
                  <button className="row-action" title="SQL 편집기 열기" onClick={(e) => (e.stopPropagation(), props.onOpenEditor(c.id))}>
                    ✎
                  </button>
                  {isConn && (
                    <button className="row-action" title="새로고침" onClick={(e) => (e.stopPropagation(), void refresh(c.id, null))}>
                      ↻
                    </button>
                  )}
                  {isConn && (
                    <button
                      className="row-action"
                      title="연결 끊기"
                      onClick={(e) => {
                        e.stopPropagation()
                        setNodes((all) => Object.fromEntries(Object.entries(all).filter(([k]) => !k.startsWith(`${c.id}|`))))
                        props.onDisconnect(c.id)
                      }}
                    >
                      ⏏
                    </button>
                  )}
                  <button className="row-action" title="연결 고치기" onClick={(e) => (e.stopPropagation(), props.onEdit(c))}>
                    ⚙
                  </button>
                  <button className="row-action" title="연결 삭제" onClick={(e) => (e.stopPropagation(), props.onDelete(c))}>
                    ✕
                  </button>
                </span>
              </div>
              {st?.expanded && renderChildren(c.id, st, 1)}
            </li>
          )
        })}
      </ul>
    </aside>
  )
}

// 같은 경로를 쓰는 노드(스키마와 그 아래 폴더 등)의 위아래 순서
const RANK: Record<NavNode['type'], number> = {
  database: 0, schema: 0, 'folder-tables': 1, 'folder-views': 1, table: 2, view: 2,
  'folder-columns': 3, 'folder-indexes': 3, 'folder-fks': 3, column: 4, index: 4, fk: 4
}

/** 캐시 키 k가 prefix 노드보다 아래쪽 노드인지 */
function isUnder(k: string, prefix: string): boolean {
  if (prefix.endsWith('|root')) return true
  const [conn, type, path] = prefix.split('|')
  const [kConn, kType, kPath] = k.split('|')
  if (conn !== kConn || kPath === undefined) return false
  if (kPath === path) return RANK[kType as NavNode['type']] > RANK[type as NavNode['type']]
  return kPath.startsWith(path + '\u0001')
}

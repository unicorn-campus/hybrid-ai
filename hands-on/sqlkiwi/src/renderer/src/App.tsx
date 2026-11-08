// sqlkiwi 화면 전체: 왼쪽 탐색 트리, 오른쪽 위 SQL 편집기 탭, 오른쪽 아래 결과
import { useCallback, useEffect, useRef, useState } from 'react'
import type { CellValue, ColumnInfo, CompletionSchema, ConnectionConfig, NavNode, StatementResult } from '@shared/types'
import { firstKeyword, isDangerous, splitStatements } from '@shared/sql-split'
import { errorText, kiwi, unwrap } from './api'
import { ConnectionDialog, PasswordDialog } from './components/ConnectionDialog'
import { Navigator } from './components/Navigator'
import { ResultGrid, sortRows, type SortDir } from './components/ResultGrid'
import { SqlEditor, type EditorHandle, type RunRequest } from './components/SqlEditor'

// ---- 결과 화면 자료형 ----
interface RowsView {
  kind: 'rows'
  title: string
  /** 사용자가 실행한 원래 문장(서버 정렬 때 감쌀 대상) */
  baseSql: string
  columns: ColumnInfo[]
  rows: CellValue[][]
  /** 정렬 전 원래 순서(메모리 정렬 해제용) */
  original?: CellValue[][]
  resultId: string
  hasMore: boolean
  canFetchMore: boolean
  loading: boolean
  elapsedMs: number
  sort?: { col: number; dir: SortDir; server: boolean }
}
interface MessageView {
  kind: 'message'
  title: string
  text: string
  error?: boolean
  sql?: string
}
interface StatsView {
  kind: 'stats'
  title: string
  items: { sql: string; elapsedMs: number; text: string; error?: boolean }[]
}
type ResultView = RowsView | MessageView | StatsView

interface EditorTab {
  id: string
  connectionId: string
  title: string
  initialText: string
  text: string
  running: boolean
  results: ResultView[]
  activeResult: number
}

let tabSeq = 0
const SORTABLE = new Set(['SELECT', 'WITH', 'VALUES', 'TABLE'])
const DATA_CHANGE = new Set(['INSERT', 'UPDATE', 'DELETE', 'MERGE', 'REPLACE', 'UPSERT'])

/** 행이 없는 문장의 결과 글: 데이터 변경 문장은 바뀐 행 수, 그 밖(CREATE 등)은 완료 */
function updateText(sql: string, affected: number | null): string {
  return DATA_CHANGE.has(firstKeyword(sql)) && affected !== null ? `${affected}행 바뀜` : '완료'
}

export function App() {
  const [connections, setConnections] = useState<ConnectionConfig[]>([])
  const [connected, setConnected] = useState<Set<string>>(new Set())
  const [completion, setCompletion] = useState<Record<string, { schema: CompletionSchema; defaultSchema?: string }>>({})
  const [tabs, setTabs] = useState<EditorTab[]>([])
  const [activeTab, setActiveTab] = useState<string | null>(null)
  const [activeConn, setActiveConn] = useState<string | null>(null)
  const [dialog, setDialog] = useState<{ edit: ConnectionConfig | null } | null>(null)
  const [pwPrompt, setPwPrompt] = useState<{ conn: ConnectionConfig; resolve(p: string | null): void } | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [split, setSplit] = useState(0.5)
  const editors = useRef(new Map<string, EditorHandle>())
  const tabsRef = useRef(tabs)
  tabsRef.current = tabs

  const showToast = (t: string) => {
    setToast(t)
    setTimeout(() => setToast((cur) => (cur === t ? null : cur)), 4000)
  }

  const reloadConnections = useCallback(async () => {
    setConnections(await unwrap(kiwi.connections.list()))
  }, [])
  useEffect(() => {
    void reloadConnections()
  }, [reloadConnections])

  const connById = (id: string) => connections.find((c) => c.id === id)

  // ---- 연결 ----
  const ensureConnected = useCallback(
    async (id: string): Promise<boolean> => {
      if (connected.has(id)) return true
      const conn = connections.find((c) => c.id === id)
      if (!conn) return false
      try {
        let r = await kiwi.session.connect(id)
        if (!r.ok && r.error === 'NEED_PASSWORD') {
          const pw = await new Promise<string | null>((resolve) => setPwPrompt({ conn, resolve }))
          setPwPrompt(null)
          if (pw === null) return false
          r = await kiwi.session.connect(id, pw)
        }
        if (!r.ok) throw new Error(r.error)
        setConnected((s) => new Set(s).add(id))
        showToast(`연결됨: ${r.value.version}`)
        // 자동완성용 테이블과 컬럼 목록은 뒤에서 읽음
        unwrap(kiwi.meta.completion(id)).then(
          (c) => setCompletion((all) => ({ ...all, [id]: c })),
          () => undefined
        )
        return true
      } catch (e) {
        showToast(`연결 실패: ${errorText(e)}`)
        return false
      }
    },
    [connected, connections]
  )

  const disconnect = async (id: string) => {
    await kiwi.session.disconnect(id)
    setConnected((s) => {
      const n = new Set(s)
      n.delete(id)
      return n
    })
  }

  // ---- 편집기 탭 ----
  const openEditor = (connectionId: string, text = '', title?: string): string => {
    const conn = connById(connectionId)
    const id = `tab-${++tabSeq}`
    const t: EditorTab = {
      id,
      connectionId,
      title: title ?? `${conn?.name ?? 'SQL'} ${tabSeq}`,
      initialText: text,
      text,
      running: false,
      results: [],
      activeResult: 0
    }
    setTabs((all) => [...all, t])
    setActiveTab(id)
    setActiveConn(connectionId)
    return id
  }

  const closeTab = (id: string) => {
    const t = tabsRef.current.find((x) => x.id === id)
    t?.results.forEach((r) => r.kind === 'rows' && r.canFetchMore && kiwi.query.close(r.resultId))
    setTabs((all) => {
      const rest = all.filter((x) => x.id !== id)
      if (activeTab === id) setActiveTab(rest.at(-1)?.id ?? null)
      return rest
    })
  }

  const updateTab = (id: string, fn: (t: EditorTab) => EditorTab) => setTabs((all) => all.map((t) => (t.id === id ? fn(t) : t)))
  const updateResult = (tabId: string, idx: number, fn: (r: ResultView) => ResultView) =>
    updateTab(tabId, (t) => ({ ...t, results: t.results.map((r, i) => (i === idx ? fn(r) : r)) }))

  // ---- 실행 ----
  const toView = (r: StatementResult, title: string, keep: boolean): ResultView => {
    if (r.result.kind === 'update') {
      return { kind: 'message', title, sql: r.sql, text: `${updateText(r.sql, r.result.affectedRows)} (${r.elapsedMs}ms)` }
    }
    return {
      kind: 'rows',
      title,
      baseSql: r.sql,
      columns: r.result.columns,
      rows: r.result.rows,
      resultId: r.result.resultId,
      hasMore: r.result.hasMore,
      canFetchMore: keep && r.result.canFetchMore,
      loading: false,
      elapsedMs: r.elapsedMs
    }
  }

  const confirmDanger = (sqls: string[]) => {
    const bad = sqls.filter(isDangerous)
    if (bad.length === 0) return true
    // DBeaver처럼 WHERE 없는 DELETE, UPDATE와 DROP TABLE은 한 번 더 확인함
    return window.confirm(`조건 없이 데이터를 바꾸거나 지우는 문장이 있음:\n\n${bad.map((s) => s.slice(0, 120)).join('\n')}\n\n그래도 실행할까요?`)
  }

  const runStatement = async (tabId: string, req: RunRequest) => {
    const tab = tabsRef.current.find((t) => t.id === tabId)
    if (!tab || tab.running) return
    if (!req.sql.trim()) {
      showToast('실행할 문장이 없음. 커서를 문장 위에 두십시오')
      return
    }
    if (!confirmDanger([req.sql])) return
    if (!(await ensureConnected(tab.connectionId))) return
    updateTab(tabId, (t) => ({ ...t, running: true }))
    const r = await kiwi.query.execute(tab.connectionId, req.sql, true)
    updateTab(tabId, (t) => ({
      ...t,
      running: false,
      activeResult: 0,
      results: [r.ok ? toView(r.value, '결과', true) : { kind: 'message', title: '오류', text: r.error, error: true, sql: req.sql }]
    }))
  }

  const runScript = async (tabId: string, text: string) => {
    const tab = tabsRef.current.find((t) => t.id === tabId)
    if (!tab || tab.running) return
    const kind = connById(tab.connectionId)?.kind ?? 'postgres'
    const stmts = splitStatements(text, kind).map((s) => s.text)
    if (stmts.length === 0) return showToast('실행할 문장이 없음')
    if (!confirmDanger(stmts)) return
    if (!(await ensureConnected(tab.connectionId))) return
    updateTab(tabId, (t) => ({ ...t, running: true, results: [], activeResult: 0 }))
    const views: ResultView[] = []
    const stats: StatsView = { kind: 'stats', title: '통계', items: [] }
    let n = 0
    for (const s of stmts) {
      // 스크립트의 결과는 문장마다 첫 200행만 보여 주고 커서를 닫음
      const r = await kiwi.query.execute(tab.connectionId, s, false)
      if (!r.ok) {
        stats.items.push({ sql: s, elapsedMs: 0, text: r.error, error: true })
        break // 오류가 나면 멈춤
      }
      const v = toView(r.value, `결과 ${++n}`, false)
      if (v.kind === 'rows') views.push(v)
      stats.items.push({
        sql: s,
        elapsedMs: r.value.elapsedMs,
        text: v.kind === 'rows' ? `${v.rows.length}${v.hasMore ? '+' : ''}행` : r.value.result.kind === 'update' ? updateText(s, r.value.result.affectedRows) : ''
      })
    }
    const failed = stats.items.some((i) => i.error)
    updateTab(tabId, (t) => ({ ...t, running: false, results: [...views, stats], activeResult: failed ? views.length : 0 }))
    showToast(failed ? `${stats.items.length - 1}/${stmts.length}개 실행 후 오류로 멈춤` : `${stmts.length}개 문장 실행 완료`)
  }

  const cancel = async (tabId: string) => {
    const tab = tabsRef.current.find((t) => t.id === tabId)
    if (tab) await kiwi.query.cancel(tab.connectionId)
  }

  const fetchMore = async (tabId: string, idx: number, all = false) => {
    const tab = tabsRef.current.find((t) => t.id === tabId)
    const v = tab?.results[idx]
    if (!v || v.kind !== 'rows' || !v.canFetchMore || v.loading) return
    updateResult(tabId, idx, (r) => ({ ...r, loading: true }) as RowsView)
    const r = await kiwi.query.fetchMore(v.resultId, all)
    updateResult(tabId, idx, (cur) => {
      const rv = cur as RowsView
      if (!r.ok) return { ...rv, loading: false, canFetchMore: false }
      return { ...rv, loading: false, rows: [...rv.rows, ...r.value.rows], hasMore: r.value.hasMore, canFetchMore: r.value.hasMore }
    })
    if (!r.ok) showToast(`더 가져오기 실패: ${r.error}`)
  }

  // 정렬: 다 받은 결과면 메모리에서, 남은 행이 있으면 서버에 ORDER BY를 붙여 다시 질의(DBeaver SMART 규칙)
  const sortBy = async (tabId: string, idx: number, col: number) => {
    const tab = tabsRef.current.find((t) => t.id === tabId)
    const v = tab?.results[idx]
    if (!tab || !v || v.kind !== 'rows' || v.loading) return
    const next: SortDir | null = v.sort?.col !== col ? 'asc' : v.sort.dir === 'asc' ? 'desc' : null
    const needServer = v.hasMore || v.sort?.server
    if (needServer && SORTABLE.has(firstKeyword(v.baseSql))) {
      const sqlText = next ? `SELECT * FROM (\n${v.baseSql}\n) z_q ORDER BY ${col + 1} ${next.toUpperCase()}` : v.baseSql
      updateResult(tabId, idx, (r) => ({ ...r, loading: true }) as RowsView)
      const r = await kiwi.query.execute(tab.connectionId, sqlText, true)
      if (!r.ok || r.value.result.kind !== 'rows') {
        updateResult(tabId, idx, (cur) => ({ ...(cur as RowsView), loading: false }))
        return showToast(`정렬 실패: ${r.ok ? '결과가 없음' : r.error}`)
      }
      const res = r.value.result
      updateResult(tabId, idx, (cur) => ({
        ...(cur as RowsView),
        rows: res.rows,
        original: undefined,
        resultId: res.resultId,
        hasMore: res.hasMore,
        canFetchMore: res.canFetchMore,
        loading: false,
        elapsedMs: r.value.elapsedMs,
        sort: next ? { col, dir: next, server: true } : undefined
      }))
      return
    }
    if (v.hasMore) showToast('받은 행만 정렬함. 모두 가져오기 뒤 정렬하면 전체가 정렬됨')
    updateResult(tabId, idx, (cur) => {
      const rv = cur as RowsView
      const original = rv.original ?? rv.rows
      return { ...rv, original: next ? original : undefined, rows: next ? sortRows(original, col, next) : original, sort: next ? { col, dir: next, server: false } : undefined }
    })
  }

  const openRelation = async (connId: string, node: NavNode) => {
    const conn = connById(connId)
    if (!conn) return
    const [schema, table] = node.path
    const q = async (n: string) => unwrap(kiwi.meta.quote(connId, n))
    const name = conn.kind === 'sqlite' ? await q(table) : `${await q(schema)}.${await q(table)}`
    const sqlText = `SELECT * FROM ${name}`
    const tabId = openEditor(connId, sqlText, table)
    pendingRun.current = { tabId, sql: sqlText } // 탭이 화면에 생긴 뒤 실행함
  }

  const pendingRun = useRef<{ tabId: string; sql: string } | null>(null)
  useEffect(() => {
    const p = pendingRun.current
    if (p && tabs.some((t) => t.id === p.tabId)) {
      pendingRun.current = null
      void runStatement(p.tabId, { sql: p.sql, from: 0 })
    }
  })

  const deleteConnection = async (c: ConnectionConfig) => {
    if (!window.confirm(`'${c.name}' 연결 설정을 지울까요? (DB 자체는 지우지 않음)`)) return
    await unwrap(kiwi.connections.remove(c.id))
    setConnected((s) => {
      const n = new Set(s)
      n.delete(c.id)
      return n
    })
    setTabs((all) => all.filter((t) => t.connectionId !== c.id))
    await reloadConnections()
  }

  // ---- 위아래 나누기 끌기 ----
  const rightPane = useRef<HTMLDivElement>(null)
  const startDrag = (e: React.PointerEvent) => {
    const box = rightPane.current!.getBoundingClientRect()
    const move = (ev: PointerEvent) => setSplit(Math.min(0.85, Math.max(0.15, (ev.clientY - box.top) / box.height)))
    const up = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    e.preventDefault()
  }

  const tab = tabs.find((t) => t.id === activeTab) ?? null
  const tabConn = tab ? connById(tab.connectionId) : undefined

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">
          <span className="kiwi" aria-hidden>
            ●
          </span>
          sqlkiwi
        </span>
        <span className="muted small">SQLite, PostgreSQL, MySQL 클라이언트</span>
      </header>

      <div className="body">
        <Navigator
          connections={connections}
          connected={connected}
          activeConnectionId={activeConn}
          onSelectConnection={setActiveConn}
          ensureConnected={ensureConnected}
          onDisconnect={(id) => void disconnect(id)}
          onNew={() => setDialog({ edit: null })}
          onEdit={(c) => setDialog({ edit: c })}
          onDelete={(c) => void deleteConnection(c)}
          onOpenEditor={(id) => openEditor(id)}
          onOpenRelation={(id, n) => void openRelation(id, n)}
        />

        <main className="workspace" ref={rightPane}>
          {tabs.length === 0 ? (
            <div className="welcome">
              <h1>sqlkiwi</h1>
              <ol>
                <li>왼쪽 위 「+ 새 연결」로 DB를 등록함</li>
                <li>연결을 누르면 스키마와 테이블이 펼쳐짐. 테이블을 두 번 누르면 데이터를 봄</li>
                <li>연결 옆 ✎ 단추로 SQL 편집기를 엶</li>
              </ol>
              <table className="keys">
                <tbody>
                  <tr>
                    <td>Ctrl+Enter</td>
                    <td>커서가 있는 문장 실행(빈 줄과 ; 로 문장을 나눔)</td>
                  </tr>
                  <tr>
                    <td>Alt+X</td>
                    <td>스크립트 전체 실행</td>
                  </tr>
                  <tr>
                    <td>Ctrl+Space</td>
                    <td>자동완성(키워드, 테이블, 컬럼)</td>
                  </tr>
                  <tr>
                    <td>Ctrl+C / Ctrl+Shift+C</td>
                    <td>결과 셀 복사 / 머리글 포함 복사</td>
                  </tr>
                </tbody>
              </table>
            </div>
          ) : (
            <>
              <div className="tabs">
                {tabs.map((t) => (
                  <div key={t.id} className={`tab ${t.id === activeTab ? 'active' : ''}`} onClick={() => (setActiveTab(t.id), setActiveConn(t.connectionId))}>
                    <span className={`db-badge ${connById(t.connectionId)?.kind ?? ''}`} />
                    <span>{t.title}</span>
                    {t.running && <span className="spinner" />}
                    <button
                      className="tab-close"
                      title="닫기"
                      onClick={(e) => {
                        e.stopPropagation()
                        closeTab(t.id)
                      }}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>

              {tab && (
                <div className="toolbar">
                  <button className="primary" disabled={tab.running} onClick={() => editors.current.get(tab.id)?.runCurrent()} title="Ctrl+Enter">
                    ▶ 문장 실행
                  </button>
                  <button disabled={tab.running} onClick={() => editors.current.get(tab.id)?.runScript()} title="Alt+X">
                    ▶▶ 스크립트 실행
                  </button>
                  <button disabled={!tab.running} onClick={() => void cancel(tab.id)}>
                    ■ 취소
                  </button>
                  <span className="spacer" />
                  <span className="conn-label">
                    <span className={`dot ${connected.has(tab.connectionId) ? 'on' : ''}`} />
                    {tabConn?.name}
                    {tabConn?.readOnly && <span className="tag">읽기 전용</span>}
                  </span>
                </div>
              )}

              <div className="editor-area" style={{ flexBasis: `${split * 100}%` }}>
                {tabs.map((t) => (
                  <div key={t.id} className="editor-wrap" style={{ display: t.id === activeTab ? 'block' : 'none' }}>
                    <SqlEditor
                      kind={connById(t.connectionId)?.kind ?? 'postgres'}
                      initialText={t.initialText}
                      completion={completion[t.connectionId]}
                      visible={t.id === activeTab}
                      onRun={(req) => void runStatement(t.id, req)}
                      onRunScript={(text) => void runScript(t.id, text)}
                      onChange={(text) => updateTab(t.id, (x) => ({ ...x, text }))}
                      handleRef={(h) => (h ? editors.current.set(t.id, h) : editors.current.delete(t.id))}
                    />
                  </div>
                ))}
              </div>

              <div className="splitter" onPointerDown={startDrag} role="separator" aria-orientation="horizontal" />

              <section className="results">
                {tab && <ResultPanel tab={tab} onSelect={(i) => updateTab(tab.id, (t) => ({ ...t, activeResult: i }))} onFetchMore={(i, all) => void fetchMore(tab.id, i, all)} onSort={(i, c) => void sortBy(tab.id, i, c)} />}
              </section>
            </>
          )}
        </main>
      </div>

      {dialog && (
        <ConnectionDialog
          initial={dialog.edit}
          onClose={() => setDialog(null)}
          onSaved={async (c) => {
            setDialog(null)
            setConnected((s) => {
              const n = new Set(s)
              n.delete(c.id)
              return n
            })
            await reloadConnections()
            setActiveConn(c.id)
          }}
        />
      )}
      {pwPrompt && <PasswordDialog name={pwPrompt.conn.name} onSubmit={(p) => pwPrompt.resolve(p)} onCancel={() => pwPrompt.resolve(null)} />}
      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </div>
  )
}

function ResultPanel({
  tab,
  onSelect,
  onFetchMore,
  onSort
}: {
  tab: EditorTab
  onSelect(i: number): void
  onFetchMore(i: number, all: boolean): void
  onSort(i: number, col: number): void
}) {
  if (tab.running && tab.results.length === 0) return <div className="result-empty">실행 중...</div>
  if (tab.results.length === 0) return <div className="result-empty">결과가 여기에 나옴. Ctrl+Enter로 문장을 실행하십시오</div>
  const idx = Math.min(tab.activeResult, tab.results.length - 1)
  const v = tab.results[idx]
  return (
    <>
      <div className="result-tabs">
        {tab.results.map((r, i) => (
          <button key={i} className={`result-tab ${i === idx ? 'active' : ''} ${r.kind === 'message' && r.error ? 'err' : ''}`} onClick={() => onSelect(i)}>
            {r.title}
          </button>
        ))}
      </div>
      <div className="result-body">
        {v.kind === 'rows' && (
          <ResultGrid
            columns={v.columns}
            rows={v.rows}
            canFetchMore={v.canFetchMore}
            loading={v.loading}
            sort={v.sort}
            onNeedMore={() => onFetchMore(idx, false)}
            onSort={(c) => onSort(idx, c)}
          />
        )}
        {v.kind === 'message' && (
          <div className={`message ${v.error ? 'err' : 'ok'}`}>
            <p>{v.text}</p>
            {v.sql && <pre>{v.sql}</pre>}
          </div>
        )}
        {v.kind === 'stats' && (
          <table className="stats">
            <thead>
              <tr>
                <th>#</th>
                <th>문장</th>
                <th>결과</th>
                <th>시간</th>
              </tr>
            </thead>
            <tbody>
              {v.items.map((it, i) => (
                <tr key={i} className={it.error ? 'err' : ''}>
                  <td>{i + 1}</td>
                  <td className="mono">{it.sql.length > 160 ? `${it.sql.slice(0, 160)}...` : it.sql}</td>
                  <td>{it.text}</td>
                  <td>{it.error ? '' : `${it.elapsedMs}ms`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {v.kind === 'rows' && (
        <div className="statusbar">
          <span>
            {v.rows.length.toLocaleString()}
            {v.hasMore ? '+' : ''}행
          </span>
          <span>{v.elapsedMs}ms</span>
          {v.sort && <span>정렬: {v.columns[v.sort.col]?.name} {v.sort.dir === 'asc' ? '오름차순' : '내림차순'}{v.sort.server ? ' (서버)' : ''}</span>}
          {v.hasMore && !v.canFetchMore && <span className="muted">스크립트 결과는 처음 200행만 보여 줌</span>}
          <span className="spacer" />
          {v.canFetchMore && (
            <>
              <button onClick={() => onFetchMore(idx, false)} disabled={v.loading}>
                다음 200행
              </button>
              <button onClick={() => onFetchMore(idx, true)} disabled={v.loading}>
                모두 가져오기
              </button>
            </>
          )}
        </div>
      )}
    </>
  )
}

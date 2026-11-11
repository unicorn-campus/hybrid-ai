import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, ChevronDown, ChevronRight, CircleStop, Columns3, Database, FileCode2, FolderOpen,
  History, KeyRound, LoaderCircle, Moon, MoreHorizontal, PanelLeftClose, PanelLeftOpen, Pencil,
  Play, Plus, RefreshCw, Save, Search, Settings2, Sparkles, SquareTerminal, Sun, Table2, Trash2,
  Unplug, View, X, Zap
} from 'lucide-react'
import type {
  Cell, ColumnInfo, Connection, HistoryEntry, QueryRequest, QueryResult, SchemaInfo, TableDetails,
  TableInfo, Workspace, WorkspaceTab
} from '../../shared/types'
import { currentStatement, quoteIdentifier } from '../../shared/sql'
import { ConnectionDialog } from './components/ConnectionDialog'
import { ResultGrid } from './components/ResultGrid'
import { SqlEditor, type SqlEditorHandle } from './components/SqlEditor'

const sampleSql = `-- 도시별 주문 현황: sqlkiwi 샘플 데이터
SELECT
  c.name AS customer,
  c.city,
  COUNT(DISTINCT o.id) AS order_count,
  ROUND(SUM(i.quantity * i.unit_price), 2) AS total_spent
FROM customers c
JOIN orders o ON o.customer_id = c.id
JOIN order_items i ON i.order_id = o.id
GROUP BY c.id, c.name, c.city
ORDER BY total_spent DESC;`

const makeTab = (connectionId: string | null, sql = '-- SQL을 입력하세요\nSELECT 1;', title = '새 쿼리'): WorkspaceTab => ({
  id: crypto.randomUUID(), title, sql, connectionId
})

function errorText(error: unknown) { return error instanceof Error ? error.message : String(error) }

function KiwiMark() {
  return <span className="kiwi-mark" aria-hidden="true"><span /><i /><i /><i /><i /><i /></span>
}

export function App() {
  const [connections, setConnections] = useState<Connection[]>([])
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [tabs, setTabs] = useState<WorkspaceTab[]>([])
  const [activeTabId, setActiveTabId] = useState('')
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')
  const [schemas, setSchemas] = useState<Record<string, SchemaInfo>>({})
  const [versions, setVersions] = useState<Record<string, string>>({})
  const [connecting, setConnecting] = useState<Record<string, boolean>>({})
  const [details, setDetails] = useState<Record<string, TableDetails>>({})
  const [expandedConnections, setExpandedConnections] = useState<Set<string>>(new Set())
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set())
  const [results, setResults] = useState<Record<string, QueryResult[]>>({})
  const [resultTabs, setResultTabs] = useState<Record<string, number>>({})
  const [running, setRunning] = useState<{ tabId: string; connectionId: string } | null>(null)
  const [rowLimit, setRowLimit] = useState(200)
  const [navigatorMode, setNavigatorMode] = useState<'connections' | 'history'>('connections')
  const [navigatorOpen, setNavigatorOpen] = useState(true)
  const [filter, setFilter] = useState('')
  const [dialog, setDialog] = useState<{ open: boolean; connection?: Connection }>({ open: false })
  const [danger, setDanger] = useState<{ request: QueryRequest; tabId: string } | null>(null)
  const [toast, setToast] = useState('')
  const [fatal, setFatal] = useState('')
  const editorRef = useRef<SqlEditorHandle>(null)
  const connectionEpoch = useRef<Record<string, number>>({})

  const activeTab = tabs.find((tab) => tab.id === activeTabId) ?? tabs[0]
  const activeConnection = connections.find((connection) => connection.id === activeTab?.connectionId)
  const activeResults = results[activeTab?.id] ?? []
  const activeResultIndex = Math.min(resultTabs[activeTab?.id] ?? 0, Math.max(activeResults.length - 1, 0))
  const activeResult = activeResults[activeResultIndex]
  const editorDetails = useMemo(() => {
    if (!activeConnection) return undefined
    const output: Record<string, TableDetails> = {}
    for (const [key, value] of Object.entries(details)) {
      const prefix = `${activeConnection.id}:`
      if (key.startsWith(prefix)) output[key.slice(prefix.length)] = value
    }
    return output
  }, [activeConnection, details])

  const notify = useCallback((message: string) => setToast(message), [])
  useEffect(() => { if (!toast) return; const timer = window.setTimeout(() => setToast(''), 2800); return () => window.clearTimeout(timer) }, [toast])

  const connect = useCallback(async (id: string, quiet = false) => {
    const epoch = (connectionEpoch.current[id] ?? 0) + 1
    connectionEpoch.current[id] = epoch
    setConnecting((current) => ({ ...current, [id]: true }))
    try {
      const response = await window.sqlkiwi.connect(id)
      if (connectionEpoch.current[id] !== epoch) return response
      setSchemas((current) => ({ ...current, [id]: response.schema }))
      setVersions((current) => ({ ...current, [id]: response.version }))
      setExpandedConnections((current) => new Set(current).add(id))
      if (!quiet) notify('데이터베이스에 연결했습니다.')
      return response
    } catch (error) {
      if (!quiet) notify(`연결 실패: ${errorText(error)}`)
      throw error
    } finally {
      if (connectionEpoch.current[id] === epoch) setConnecting((current) => ({ ...current, [id]: false }))
    }
  }, [notify])

  useEffect(() => {
    let disposed = false
    const load = async () => {
      try {
        const bootstrap = await window.sqlkiwi.bootstrap()
        if (disposed) return
        setConnections(bootstrap.connections)
        setHistory(bootstrap.history)
        const restored = bootstrap.workspace
        const first = makeTab(bootstrap.demoId, sampleSql, '주문 요약')
        const initialTabs = restored?.tabs.length ? restored.tabs : [first]
        const initialActive = initialTabs.some((tab) => tab.id === restored?.activeTabId) ? restored!.activeTabId : initialTabs[0].id
        setTabs(initialTabs); setActiveTabId(initialActive); setTheme(restored?.theme ?? 'dark')
        const response = await connect(bootstrap.demoId, true)
        if (!restored?.tabs.length && !disposed) {
          const queryResults = await window.sqlkiwi.query({ connectionId: bootstrap.demoId, sql: sampleSql, limit: 200 })
          if (!disposed) { setResults({ [first.id]: queryResults }); setHistory(await window.sqlkiwi.history()) }
        }
        if (!response && !disposed) throw new Error('샘플 데이터베이스를 열지 못했습니다.')
      } catch (error) { if (!disposed) setFatal(errorText(error)) }
    }
    void load()
    return () => { disposed = true }
  }, [connect])

  useEffect(() => {
    if (!tabs.length || !activeTabId) return
    const timer = window.setTimeout(() => {
      const workspace: Workspace = { tabs, activeTabId, theme }
      void window.sqlkiwi.saveWorkspace(workspace).catch(() => undefined)
    }, 500)
    return () => window.clearTimeout(timer)
  }, [activeTabId, tabs, theme])

  const updateActive = useCallback((patch: Partial<WorkspaceTab>) => {
    setTabs((current) => current.map((tab) => tab.id === activeTabId ? { ...tab, ...patch } : tab))
  }, [activeTabId])

  const addTab = useCallback((connectionId: string | null | undefined = activeTab?.connectionId ?? connections[0]?.id ?? null, sql?: string, title?: string) => {
    const tab = makeTab(connectionId ?? null, sql, title)
    setTabs((current) => [...current, tab]); setActiveTabId(tab.id)
    window.setTimeout(() => editorRef.current?.focus(), 0)
  }, [activeTab?.connectionId, connections])

  const closeTab = (id: string) => {
    if (running?.tabId === id) { notify('실행을 중지한 뒤 탭을 닫아 주세요.'); return }
    if (tabs.length === 1) {
      const replacement = makeTab(activeTab?.connectionId ?? null)
      setTabs([replacement]); setActiveTabId(replacement.id); return
    }
    const index = tabs.findIndex((tab) => tab.id === id)
    const next = tabs.filter((tab) => tab.id !== id)
    setTabs(next)
    if (activeTabId === id) setActiveTabId(next[Math.min(index, next.length - 1)].id)
    setResults((current) => { const copy = { ...current }; delete copy[id]; return copy })
  }

  const executeRequest = useCallback(async (request: QueryRequest, targetTabId: string) => {
    setRunning({ tabId: targetTabId, connectionId: request.connectionId })
    try {
      const queryResults = await window.sqlkiwi.query(request)
      setResults((current) => ({ ...current, [targetTabId]: queryResults }))
      setResultTabs((current) => ({ ...current, [targetTabId]: 0 }))
      setHistory(await window.sqlkiwi.history())
    } catch (error) {
      const message = errorText(error)
      if (message.includes('DANGEROUS_SQL:')) setDanger({ request, tabId: targetTabId })
      else setResults((current) => ({ ...current, [targetTabId]: [{ sql: request.sql, columns: [], rows: [], affectedRows: 0, durationMs: 0, truncated: false, error: message }] }))
    } finally { setRunning((current) => current?.tabId === targetTabId ? null : current) }
  }, [])

  const run = useCallback((script: boolean, allowDangerous = false) => {
    if (running) return
    if (!activeTab || !activeConnection) { notify('먼저 데이터베이스 연결을 선택해 주세요.'); return }
    const selected = editorRef.current?.selectedText().trim()
    const current = currentStatement(activeTab.sql, editorRef.current?.cursor() ?? 0, activeConnection.engine)
    const sqlText = script ? (selected || activeTab.sql) : (selected || current?.text || '')
    if (!sqlText) { notify('실행할 SQL이 없습니다.'); return }
    const request = { connectionId: activeConnection.id, sql: sqlText, limit: rowLimit, allowDangerous }
    const targetTabId = activeTab.id
    void (async () => {
      if (!schemas[activeConnection.id]) await connect(activeConnection.id, true)
      await executeRequest(request, targetTabId)
    })().catch(error => notify(`실행 실패: ${errorText(error)}`))
  }, [activeConnection, activeTab, executeRequest, notify, rowLimit, running, schemas, connect])

  const forgetConnection = (id: string) => {
    setSchemas(current => { const copy = { ...current }; delete copy[id]; return copy })
    setVersions(current => { const copy = { ...current }; delete copy[id]; return copy })
    setDetails(current => Object.fromEntries(Object.entries(current).filter(([key]) => !key.startsWith(`${id}:`))))
  }

  const cancelQuery = async () => {
    if (!running) return
    try {
      const id = running.connectionId
      await window.sqlkiwi.cancel(id)
      forgetConnection(id)
      notify('실행을 중지했습니다. 다음 실행 시 다시 연결합니다.')
    } catch (error) { notify(`중지 실패: ${errorText(error)}`) }
  }

  const disconnect = async (id: string) => {
    connectionEpoch.current[id] = (connectionEpoch.current[id] ?? 0) + 1
    await window.sqlkiwi.disconnect(id)
    setSchemas((current) => { const copy = { ...current }; delete copy[id]; return copy })
    setVersions((current) => { const copy = { ...current }; delete copy[id]; return copy })
    notify('연결을 끊었습니다.')
  }

  const refreshSchema = async (id: string) => {
    try { const schema = await window.sqlkiwi.schema(id); setSchemas((current) => ({ ...current, [id]: schema })); notify('스키마를 새로 읽었습니다.') }
    catch (error) { notify(`새로고침 실패: ${errorText(error)}`) }
  }

  const toggleTable = async (connectionId: string, table: TableInfo) => {
    const key = `${connectionId}:${table.schema}:${table.name}`
    const opening = !expandedTables.has(key)
    setExpandedTables((current) => { const next = new Set(current); opening ? next.add(key) : next.delete(key); return next })
    if (opening && !details[key]) {
      try { const value = await window.sqlkiwi.tableDetails(connectionId, table); setDetails((current) => ({ ...current, [key]: value })) }
      catch (error) { notify(`테이블 정보를 읽지 못했습니다: ${errorText(error)}`) }
    }
  }

  const openTable = (connection: Connection, table: TableInfo) => {
    const schema = table.schema && table.schema !== 'main' ? `${quoteIdentifier(table.schema, connection.engine)}.` : ''
    addTab(connection.id, `SELECT *\nFROM ${schema}${quoteIdentifier(table.name, connection.engine)}\nLIMIT ${rowLimit};`, table.name)
  }

  const saveConnection = async (connection: Connection) => {
    const saved = await window.sqlkiwi.saveConnection(connection)
    forgetConnection(saved.id)
    setConnections((current) => [...current.filter((item) => item.id !== saved.id), saved])
    setDialog({ open: false }); notify('연결 설정을 저장했습니다.')
  }

  const deleteConnection = async (connection: Connection) => {
    if (!window.confirm(`“${connection.name}” 연결 설정을 삭제할까요? 데이터베이스 파일은 삭제하지 않습니다.`)) return
    await window.sqlkiwi.deleteConnection(connection.id)
    setConnections((current) => current.filter((item) => item.id !== connection.id))
    notify('연결 설정을 삭제했습니다.')
  }

  const openSql = async () => {
    try {
      const file = await window.sqlkiwi.openSql()
      if (file) addTab(activeTab?.connectionId, file.sql, file.name.replace(/\.sql$/i, ''))
    } catch (error) { notify(`파일을 열지 못했습니다: ${errorText(error)}`) }
  }
  const saveSql = async () => {
    if (!activeTab) return
    try {
      if (await window.sqlkiwi.saveSql(activeTab.sql, `${activeTab.title}.sql`)) notify('SQL 파일을 저장했습니다.')
    } catch (error) { notify(`파일을 저장하지 못했습니다: ${errorText(error)}`) }
  }

  const filteredConnections = useMemo(() => connections.filter((connection) => connection.name.toLocaleLowerCase().includes(filter.toLocaleLowerCase())), [connections, filter])

  if (fatal) return <main className="fatal"><KiwiMark /><h1>sqlkiwi를 시작하지 못했습니다.</h1><p>{fatal}</p><button onClick={() => location.reload()}>다시 시도</button></main>
  if (!tabs.length) return <main className="splash"><KiwiMark /><h1>sqlkiwi</h1><p>샘플 데이터베이스를 준비하고 있습니다.</p><LoaderCircle className="spin" /></main>

  return <div className={`app theme-${theme}`}>
    <header className="app-header">
      <div className="brand"><KiwiMark /><div><strong>sqlkiwi</strong><span>query workspace</span></div></div>
      <div className="header-center"><span className={`connection-dot ${activeConnection && schemas[activeConnection.id] ? 'online' : ''}`} />
        <select aria-label="현재 연결" value={activeTab?.connectionId ?? ''} onChange={(event) => updateActive({ connectionId: event.target.value || null })}>
          <option value="">연결 선택</option>{connections.map((connection) => <option key={connection.id} value={connection.id}>{connection.name}</option>)}
        </select>
        {activeConnection?.readOnly && <span className="read-only"><KeyRound size={11} /> 읽기 전용</span>}
      </div>
      <div className="header-actions"><button className="icon-button" onClick={() => setTheme((value) => value === 'dark' ? 'light' : 'dark')} aria-label={theme === 'dark' ? '라이트 모드' : '다크 모드'}>{theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}</button><span className="avatar">SK</span></div>
    </header>

    <div className="workbench">
      {navigatorOpen && <aside className="navigator">
        <div className="navigator-tabs"><button className={navigatorMode === 'connections' ? 'active' : ''} onClick={() => setNavigatorMode('connections')}><Database size={14} /> 탐색기</button><button className={navigatorMode === 'history' ? 'active' : ''} onClick={() => setNavigatorMode('history')}><History size={14} /> 기록</button></div>
        {navigatorMode === 'connections' ? <>
          <div className="navigator-tools"><label><Search size={13} /><input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="연결 찾기" /></label><button className="icon-button" onClick={() => setDialog({ open: true })} aria-label="새 연결"><Plus size={16} /></button></div>
          <div className="tree" role="tree">{filteredConnections.map((connection) => {
            const open = expandedConnections.has(connection.id), schema = schemas[connection.id]
            return <div key={connection.id} className="connection-node">
              <div className={`tree-row connection-row ${activeTab?.connectionId === connection.id ? 'current' : ''}`}>
                <button className="tree-main" onClick={() => schema ? setExpandedConnections((current) => { const next = new Set(current); open ? next.delete(connection.id) : next.add(connection.id); return next }) : void connect(connection.id).catch(() => undefined)}>
                  {connecting[connection.id] ? <LoaderCircle size={14} className="spin" /> : open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  <span className="db-icon" style={{ '--db-color': connection.color ?? '#9ad84b' } as React.CSSProperties}><Database size={14} /></span>
                  <span><strong>{connection.name}</strong><small>{schema ? versions[connection.id] || '연결됨' : connection.engine}</small></span>
                </button>
                <div className="row-actions"><button onClick={() => void refreshSchema(connection.id)} disabled={!schema} aria-label={`${connection.name} 새로고침`}><RefreshCw size={12} /></button><button onClick={() => setDialog({ open: true, connection })} aria-label={`${connection.name} 수정`}><Pencil size={12} /></button><button onClick={() => void (schema ? disconnect(connection.id) : deleteConnection(connection))} aria-label={schema ? `${connection.name} 연결 끊기` : `${connection.name} 삭제`}>{schema ? <Unplug size={12} /> : <Trash2 size={12} />}</button></div>
              </div>
              {open && schema && <div className="tree-children">
                <div className="tree-section"><span><ChevronDown size={12} /><Table2 size={13} /> 테이블</span><small>{schema.tables.filter((table) => table.type === 'table').length}</small></div>
                {schema.tables.filter((table) => table.type === 'table').map((table) => <TableNode key={`${table.schema}.${table.name}`} connectionId={connection.id} table={table} detail={details[`${connection.id}:${table.schema}:${table.name}`]} open={expandedTables.has(`${connection.id}:${table.schema}:${table.name}`)} onToggle={toggleTable} onOpen={() => openTable(connection, table)} />)}
                {schema.tables.some((table) => table.type === 'view') && <div className="tree-section"><span><ChevronDown size={12} /><View size={13} /> 뷰</span><small>{schema.tables.filter((table) => table.type === 'view').length}</small></div>}
                {schema.tables.filter((table) => table.type === 'view').map((table) => <TableNode key={`${table.schema}.${table.name}`} connectionId={connection.id} table={table} detail={details[`${connection.id}:${table.schema}:${table.name}`]} open={expandedTables.has(`${connection.id}:${table.schema}:${table.name}`)} onToggle={toggleTable} onOpen={() => openTable(connection, table)} />)}
              </div>}
            </div>
          })}{!filteredConnections.length && <div className="tree-empty">저장된 연결이 없습니다.<button onClick={() => setDialog({ open: true })}>첫 연결 만들기</button></div>}</div>
        </> : <div className="history-list">{history.map((entry) => <button key={entry.id} onClick={() => addTab(entry.connectionId, entry.sql, '기록 쿼리')}><span className={entry.success ? 'history-state ok' : 'history-state fail'} /><strong>{entry.sql.replace(/\s+/g, ' ').slice(0, 64)}</strong><small>{new Date(entry.executedAt).toLocaleString('ko-KR')} · {entry.durationMs}ms · {entry.rowCount}행</small></button>)}{history.length > 0 && <button className="clear-history" onClick={() => void window.sqlkiwi.clearHistory().then(() => setHistory([]))}><Trash2 size={12} /> 기록 비우기</button>}{!history.length && <div className="tree-empty">실행 기록이 없습니다.</div>}</div>}
      </aside>}

      <main className="workspace">
        <div className="tab-strip"><button className="nav-toggle" onClick={() => setNavigatorOpen((value) => !value)} aria-label={navigatorOpen ? '탐색기 닫기' : '탐색기 열기'}>{navigatorOpen ? <PanelLeftClose size={15} /> : <PanelLeftOpen size={15} />}</button><div className="query-tabs">{tabs.map((tab) => <div className={`query-tab ${tab.id === activeTabId ? 'active' : ''}`} key={tab.id} onClick={() => setActiveTabId(tab.id)}><FileCode2 size={13} /><input aria-label="쿼리 탭 이름" value={tab.title} onChange={(event) => setTabs((current) => current.map((item) => item.id === tab.id ? { ...item, title: event.target.value } : item))} /><button onClick={(event) => { event.stopPropagation(); closeTab(tab.id) }} aria-label={`${tab.title} 탭 닫기`}><X size={12} /></button></div>)}</div><button className="new-tab" onClick={() => addTab()} aria-label="새 쿼리 탭"><Plus size={14} /></button></div>
        <div className="query-toolbar">
          <button className="run-button" onClick={() => run(false)} disabled={!!running || !activeConnection} title="현재 문장 또는 선택 영역 실행 (Ctrl+Enter)"><Play size={14} fill="currentColor" /> 실행 <kbd>Ctrl ↵</kbd></button>
          <button onClick={() => run(true)} disabled={!!running || !activeConnection} title="선택 영역 또는 전체 스크립트 실행 (Alt+X)"><Zap size={14} /> 스크립트 <kbd>Alt X</kbd></button>
          {running && <button className="stop-button" onClick={() => void cancelQuery()}><CircleStop size={14} /> 중지</button>}
          <span className="toolbar-separator" /><button onClick={() => void openSql()}><FolderOpen size={14} /> 열기</button><button onClick={() => void saveSql()}><Save size={14} /> 저장</button><span className="spacer" /><label className="limit-control">최대 행<select value={rowLimit} onChange={(event) => setRowLimit(Number(event.target.value))}><option>200</option><option>500</option><option>1000</option></select></label><button className="icon-button" onClick={() => activeConnection && setDialog({ open: true, connection: activeConnection })} aria-label="현재 연결 설정"><Settings2 size={15} /></button>
        </div>
        <section className="editor-pane">
          <div className="editor-meta"><span>{activeConnection?.engine.toUpperCase() ?? 'SQL'}</span><span>{activeConnection ? activeConnection.name : '연결 없음'}</span>{running?.tabId === activeTab.id && <span className="executing"><LoaderCircle size={11} className="spin" /> 실행 중</span>}</div>
          <SqlEditor ref={editorRef} value={activeTab.sql} engine={activeConnection?.engine ?? 'sqlite'} schema={activeConnection ? schemas[activeConnection.id] : undefined} details={editorDetails} theme={theme} onChange={(sql) => updateActive({ sql })} onRunCurrent={() => run(false)} onRunScript={() => run(true)} onSave={() => void saveSql()} />
        </section>
        <section className="results-pane">
          <div className="result-tabs"><div className="result-label"><SquareTerminal size={13} /> 결과</div>{activeResults.map((result, index) => <button key={`${result.sql}-${index}`} className={activeResultIndex === index ? 'active' : ''} onClick={() => setResultTabs((current) => ({ ...current, [activeTab.id]: index }))}>{result.error ? '오류' : result.columns.length ? `결과 ${index + 1}` : `실행 ${index + 1}`}<span>{result.error ? '!' : result.columns.length ? `${result.rows.length}${result.truncated ? '+' : ''}` : result.affectedRows}</span></button>)}{!activeResults.length && <span className="result-hint">Ctrl+Enter로 현재 SQL 실행</span>}<span className="spacer" />{activeResult && <div className="result-stats"><Activity size={12} /> {activeResult.durationMs < 10 ? activeResult.durationMs.toFixed(2) : Math.round(activeResult.durationMs)}ms {activeResult.truncated && <span>일부 결과</span>}</div>}</div>
          <div className="result-content">{activeResult ? <ResultGrid result={activeResult} onToast={notify} onExport={(columns, rows) => { void window.sqlkiwi.exportCsv(columns, rows).then(saved => { if (saved) notify('CSV 파일을 저장했습니다.') }).catch(error => notify(`내보내기 실패: ${errorText(error)}`)) }} /> : <div className="result-placeholder"><div className="placeholder-icon"><Sparkles size={24} /></div><strong>실행 결과가 여기에 표시됩니다.</strong><span>SQL을 선택한 뒤 실행하거나 Ctrl+Enter를 눌러 보세요.</span></div>}</div>
        </section>
      </main>
    </div>

    <footer className="status-bar"><span className={activeConnection && schemas[activeConnection.id] ? 'online' : ''}><i />{activeConnection && schemas[activeConnection.id] ? '연결됨' : '연결 대기'}</span><span>{activeConnection?.engine ?? '—'}</span><span>{activeConnection?.database || activeConnection?.filename?.split(/[\\/]/).pop() || '—'}</span><span className="spacer" /><span>행 제한 {rowLimit}</span><span>UTF-8</span><span>Ln {activeTab.sql.slice(0, editorRef.current?.cursor() ?? 0).split('\n').length}</span></footer>

    {dialog.open && <ConnectionDialog initial={dialog.connection} onClose={() => setDialog({ open: false })} onSave={saveConnection} onTest={async (connection) => (await window.sqlkiwi.testConnection(connection)).version} />}
    {danger && <div className="modal-backdrop"><section className="dialog danger-dialog" role="alertdialog" aria-modal="true" aria-labelledby="danger-title"><div className="danger-icon">!</div><h2 id="danger-title">데이터를 바꾸는 SQL입니다.</h2><p>WHERE 없는 UPDATE 또는 DELETE, DROP 문은 많은 데이터를 바꿀 수 있습니다. 내용을 다시 확인한 뒤 실행해 주세요.</p><pre>{danger.request.sql}</pre><footer><button className="ghost" onClick={() => setDanger(null)}>취소</button><button className="danger-button" onClick={() => { const request = { ...danger.request, allowDangerous: true }, targetTabId = danger.tabId; setDanger(null); void executeRequest(request, targetTabId) }}>확인하고 실행</button></footer></section></div>}
    {toast && <div className="toast" role="status">{toast}</div>}
  </div>
}

function TableNode({ connectionId, table, detail, open, onToggle, onOpen }: { connectionId: string; table: TableInfo; detail?: TableDetails; open: boolean; onToggle(id: string, table: TableInfo): void; onOpen(): void }) {
  return <div className="table-node">
    <button className="tree-row table-row" onClick={() => onToggle(connectionId, table)} onDoubleClick={onOpen} title="두 번 클릭하면 SELECT 쿼리를 엽니다.">{open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}{table.type === 'view' ? <View size={13} /> : <Table2 size={13} />}<span>{table.name}</span></button>
    {open && <div className="column-list">{detail ? detail.columns.map((column) => <ColumnNode key={column.name} column={column} />) : <span className="loading-row"><LoaderCircle size={11} className="spin" /> 열 정보 읽는 중</span>}</div>}
  </div>
}

function ColumnNode({ column }: { column: ColumnInfo }) {
  return <div className="column-row" title={`${column.name}: ${column.type}${column.nullable ? '' : ' NOT NULL'}`}><Columns3 size={11} /><span>{column.name}</span><small>{column.type}</small>{column.primaryKey && <KeyRound size={10} className="pk" />}</div>
}

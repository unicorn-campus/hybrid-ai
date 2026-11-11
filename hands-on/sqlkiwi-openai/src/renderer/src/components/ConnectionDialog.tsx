import { useEffect, useState } from 'react'
import { Database, File, LoaderCircle, Server, X } from 'lucide-react'
import type { Connection, Engine } from '../../../shared/types'

interface Props {
  initial?: Connection
  onClose(): void
  onSave(connection: Connection): Promise<void>
  onTest(connection: Connection): Promise<string>
}

const blank = (): Connection => ({ id: crypto.randomUUID(), name: '새 연결', engine: 'sqlite', filename: '', color: '#9ad84b' })

export function ConnectionDialog({ initial, onClose, onSave, onTest }: Props) {
  const [value, setValue] = useState<Connection>(() => initial ? { ...initial, password: '' } : blank())
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const set = <K extends keyof Connection>(key: K, next: Connection[K]) => setValue((current) => ({ ...current, [key]: next }))

  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [onClose])

  const chooseDatabase = async () => {
    const filename = await window.sqlkiwi.openDatabase()
    if (filename) { set('filename', filename); if (!initial) set('name', filename.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, '') || 'SQLite') }
  }
  const switchEngine = (engine: Engine) => setValue((current) => ({
    ...current, engine, port: engine === 'postgres' ? 5432 : engine === 'mysql' ? 3306 : undefined,
    username: engine === 'postgres' ? 'postgres' : engine === 'mysql' ? 'root' : undefined,
    name: current.name === '새 연결' ? (engine === 'sqlite' ? 'SQLite' : engine === 'postgres' ? 'PostgreSQL' : 'MySQL') : current.name
  }))
  const test = async () => {
    setTesting(true); setMessage('')
    try { setMessage(`연결 성공: ${await onTest(value)}`) } catch (error) { setMessage(`연결 실패: ${error instanceof Error ? error.message : String(error)}`) } finally { setTesting(false) }
  }
  const save = async (event: React.FormEvent) => {
    event.preventDefault(); setSaving(true); setMessage('')
    try { await onSave(value) } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); setSaving(false) }
  }

  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section className="dialog connection-dialog" role="dialog" aria-modal="true" aria-labelledby="connection-title">
      <header><div><span className="eyebrow">DATABASE CONNECTION</span><h2 id="connection-title">{initial ? '연결 설정 수정' : '새 데이터베이스 연결'}</h2></div><button className="icon-button" onClick={onClose} aria-label="닫기"><X size={18} /></button></header>
      <form onSubmit={save}>
        <div className="engine-tabs" role="tablist">
          {([['sqlite', File, 'SQLite'], ['postgres', Database, 'PostgreSQL'], ['mysql', Server, 'MySQL']] as const).map(([engine, Icon, label]) =>
            <button type="button" role="tab" aria-selected={value.engine === engine} className={value.engine === engine ? 'active' : ''} onClick={() => switchEngine(engine)} key={engine}><Icon size={18} />{label}</button>)}
        </div>
        <div className="form-grid">
          <label className="span-2">연결 이름<input autoFocus required value={value.name} onChange={(event) => set('name', event.target.value)} /></label>
          {value.engine === 'sqlite' ? <label className="span-2">데이터베이스 파일<div className="file-input"><input required value={value.filename ?? ''} onChange={(event) => set('filename', event.target.value)} placeholder="C:\\data\\sample.db" /><button type="button" onClick={chooseDatabase}>찾아보기</button></div></label> : <>
            <label>호스트<input required value={value.host ?? ''} onChange={(event) => set('host', event.target.value)} placeholder="localhost" /></label>
            <label>포트<input required type="number" value={value.port ?? ''} onChange={(event) => set('port', Number(event.target.value))} /></label>
            <label className="span-2">데이터베이스<input required value={value.database ?? ''} onChange={(event) => set('database', event.target.value)} /></label>
            <label>사용자<input required value={value.username ?? ''} onChange={(event) => set('username', event.target.value)} /></label>
            <label>비밀번호<input type="password" value={value.password ?? ''} onChange={(event) => set('password', event.target.value)} placeholder={value.hasPassword ? '비워 두면 기존 값 유지' : ''} /></label>
            <label className="check"><input type="checkbox" checked={value.ssl ?? false} onChange={(event) => set('ssl', event.target.checked)} /> SSL 인증서 검증</label>
          </>}
          <label className="check"><input type="checkbox" checked={value.readOnly ?? false} onChange={(event) => set('readOnly', event.target.checked)} /> 읽기 전용으로 연결</label>
        </div>
        {message && <p className={message.startsWith('연결 성공') ? 'form-message success' : 'form-message'} role="status">{message}</p>}
        <footer><button type="button" className="secondary" onClick={test} disabled={testing || saving}>{testing && <LoaderCircle size={14} className="spin" />}{testing ? '확인 중' : '연결 테스트'}</button><span className="spacer" /><button type="button" className="ghost" onClick={onClose}>취소</button><button className="primary" disabled={testing || saving}>{saving && <LoaderCircle size={14} className="spin" />}저장</button></footer>
      </form>
    </section>
  </div>
}

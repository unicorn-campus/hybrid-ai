// 연결 만들기와 고치기 대화상자
// 기본값은 DBeaver plugin.xml 드라이버 정의를 따름: PostgreSQL 5432/postgres/postgres, MySQL 3306/root
import { useEffect, useState } from 'react'
import type { ConnectionConfig, ConnectionInput, DbKind } from '@shared/types'
import { errorText, kiwi, newConnectionId, unwrap } from '../api'

const DEFAULTS: Record<DbKind, Partial<ConnectionConfig>> = {
  postgres: { host: 'localhost', port: 5432, database: 'postgres', user: 'postgres' },
  mysql: { host: 'localhost', port: 3306, database: '', user: 'root' },
  sqlite: {}
}

const KIND_LABEL: Record<DbKind, string> = { sqlite: 'SQLite', postgres: 'PostgreSQL', mysql: 'MySQL' }

interface Props {
  initial: ConnectionConfig | null
  onClose(): void
  onSaved(c: ConnectionConfig): void
}

export function ConnectionDialog({ initial, onClose, onSaved }: Props) {
  const [form, setForm] = useState<ConnectionInput>(
    () =>
      initial ?? {
        id: '',
        name: '',
        kind: 'postgres',
        savePassword: true,
        readOnly: false,
        ...DEFAULTS.postgres
      }
  )
  const [password, setPassword] = useState('')
  const [passwordTouched, setPasswordTouched] = useState(false)
  const [testMsg, setTestMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [canStore, setCanStore] = useState(true)

  useEffect(() => {
    unwrap(kiwi.connections.canStorePasswords()).then(setCanStore, () => setCanStore(false))
  }, [])

  const set = <K extends keyof ConnectionInput>(k: K, v: ConnectionInput[K]) => setForm((f) => ({ ...f, [k]: v }))

  const changeKind = (kind: DbKind) => {
    setForm((f) => ({ ...f, kind, host: undefined, port: undefined, database: undefined, user: undefined, filePath: undefined, ...DEFAULTS[kind] }))
    setTestMsg(null)
  }

  // 고치기에서 비밀번호 칸을 건드리지 않으면 저장된 비밀번호를 그대로 둠
  const buildInput = (): ConnectionInput => {
    const id = form.id || newConnectionId(form.kind)
    const name = form.name.trim() || defaultName(form)
    const input: ConnectionInput = { ...form, id, name }
    if (form.kind !== 'sqlite' && (passwordTouched || !initial)) input.password = password
    if (!canStore) input.savePassword = false
    return input
  }

  const test = async () => {
    setBusy(true)
    setTestMsg(null)
    try {
      const r = await unwrap(kiwi.connections.test(buildInput()))
      setTestMsg({ ok: true, text: `연결됨: ${r.version} (${r.elapsedMs}ms)` })
    } catch (e) {
      setTestMsg({ ok: false, text: errorText(e) })
    } finally {
      setBusy(false)
    }
  }

  const save = async () => {
    if (form.kind === 'sqlite' && !form.filePath) {
      setTestMsg({ ok: false, text: 'SQLite DB 파일을 고르십시오' })
      return
    }
    setBusy(true)
    try {
      const saved = await unwrap(kiwi.connections.save(buildInput()))
      onSaved(saved)
    } catch (e) {
      setTestMsg({ ok: false, text: errorText(e) })
      setBusy(false)
    }
  }

  const pickFile = async (create: boolean) => {
    const p = await unwrap(create ? kiwi.dialog.newSqlite() : kiwi.dialog.openSqlite())
    if (p) {
      set('filePath', p)
      if (!form.name) set('name', p.split(/[\\/]/).pop() ?? p)
    }
  }

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-label="연결 설정">
        <h2>{initial ? '연결 고치기' : '새 연결'}</h2>

        <div className="kind-picker" role="radiogroup" aria-label="DB 종류">
          {(['sqlite', 'postgres', 'mysql'] as DbKind[]).map((k) => (
            <button
              key={k}
              type="button"
              role="radio"
              aria-checked={form.kind === k}
              className={form.kind === k ? 'kind active' : 'kind'}
              disabled={!!initial}
              onClick={() => changeKind(k)}
            >
              <span className={`db-badge ${k}`}>{KIND_LABEL[k].slice(0, 2)}</span>
              {KIND_LABEL[k]}
            </button>
          ))}
        </div>

        <label className="field">
          <span>이름</span>
          <input value={form.name} placeholder={defaultName(form)} onChange={(e) => set('name', e.target.value)} />
        </label>

        {form.kind === 'sqlite' ? (
          <div className="field">
            <span>DB 파일</span>
            <div className="row">
              <input value={form.filePath ?? ''} placeholder="파일 경로" onChange={(e) => set('filePath', e.target.value)} />
              <button type="button" onClick={() => pickFile(false)}>
                열기
              </button>
              <button type="button" onClick={() => pickFile(true)}>
                새로 만들기
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="row">
              <label className="field grow">
                <span>호스트</span>
                <input value={form.host ?? ''} onChange={(e) => set('host', e.target.value)} />
              </label>
              <label className="field port">
                <span>포트</span>
                <input
                  value={form.port ?? ''}
                  inputMode="numeric"
                  onChange={(e) => set('port', e.target.value ? Number(e.target.value.replace(/\D/g, '')) : undefined)}
                />
              </label>
            </div>
            <label className="field">
              <span>데이터베이스</span>
              <input
                value={form.database ?? ''}
                placeholder={form.kind === 'mysql' ? '(비워 두면 지정 안 함)' : ''}
                onChange={(e) => set('database', e.target.value)}
              />
            </label>
            <div className="row">
              <label className="field grow">
                <span>사용자</span>
                <input value={form.user ?? ''} onChange={(e) => set('user', e.target.value)} />
              </label>
              <label className="field grow">
                <span>비밀번호</span>
                <input
                  type="password"
                  value={password}
                  placeholder={initial && !passwordTouched ? '(바꾸지 않음)' : ''}
                  onChange={(e) => {
                    setPassword(e.target.value)
                    setPasswordTouched(true)
                  }}
                />
              </label>
            </div>
            <label className="check">
              <input
                type="checkbox"
                checked={form.savePassword && canStore}
                disabled={!canStore}
                onChange={(e) => set('savePassword', e.target.checked)}
              />
              비밀번호 저장 {canStore ? '(OS 보안 저장소로 암호화)' : '(이 PC에서는 보안 저장소를 쓸 수 없음)'}
            </label>
          </>
        )}

        <label className="check">
          <input type="checkbox" checked={form.readOnly} onChange={(e) => set('readOnly', e.target.checked)} />
          읽기 전용 연결 (데이터를 바꾸는 문장을 막음)
        </label>

        {testMsg && <p className={testMsg.ok ? 'msg ok' : 'msg err'}>{testMsg.text}</p>}

        <div className="modal-actions">
          <button type="button" onClick={test} disabled={busy}>
            연결 시험
          </button>
          <span className="spacer" />
          <button type="button" onClick={onClose}>
            닫기
          </button>
          <button type="button" className="primary" onClick={save} disabled={busy}>
            저장
          </button>
        </div>
      </div>
    </div>
  )
}

function defaultName(f: ConnectionInput): string {
  if (f.kind === 'sqlite') return f.filePath?.split(/[\\/]/).pop() || 'SQLite'
  return `${f.database || f.user || KIND_LABEL[f.kind]}@${f.host || 'localhost'}`
}

export function PasswordDialog({ name, onSubmit, onCancel }: { name: string; onSubmit(p: string): void; onCancel(): void }) {
  const [value, setValue] = useState('')
  return (
    <div className="modal-backdrop">
      <form
        className="modal small"
        onSubmit={(e) => {
          e.preventDefault()
          onSubmit(value)
        }}
      >
        <h2>비밀번호 입력</h2>
        <p className="muted">{name} 연결에 쓸 비밀번호. 저장하지 않고 이번 연결에만 씀</p>
        <input type="password" autoFocus value={value} onChange={(e) => setValue(e.target.value)} />
        <div className="modal-actions">
          <span className="spacer" />
          <button type="button" onClick={onCancel}>
            취소
          </button>
          <button type="submit" className="primary">
            연결
          </button>
        </div>
      </form>
    </div>
  )
}

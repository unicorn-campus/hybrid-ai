// SQL 편집기 (CodeMirror 6)
// - Ctrl+Enter: 커서가 있는 문장 실행(선택 영역이 있으면 선택한 글 전체). DBeaver와 같은 단축키
// - Alt+X: 스크립트 실행(선택 영역 또는 전체를 문장으로 나눠 차례로 실행). DBeaver와 같은 단축키
// - 구문 강조와 자동완성은 @codemirror/lang-sql의 DB별 방언과, 연결에서 읽은 테이블과 컬럼 목록으로 함
import { useEffect, useRef } from 'react'
import { basicSetup } from 'codemirror'
import { Compartment, EditorState, Prec, StateEffect, StateField } from '@codemirror/state'
import { Decoration, EditorView, keymap, type DecorationSet } from '@codemirror/view'
import { MySQL, PostgreSQL, SQLite, sql, type SQLNamespace } from '@codemirror/lang-sql'
import type { CompletionSchema, DbKind } from '@shared/types'
import { statementAt } from '@shared/sql-split'

const DIALECT = { postgres: PostgreSQL, mysql: MySQL, sqlite: SQLite }

export interface RunRequest {
  sql: string
  /** 편집기 안 시작 위치 */
  from: number
}

interface Props {
  kind: DbKind
  initialText: string
  completion?: { schema: CompletionSchema; defaultSchema?: string }
  visible: boolean
  onRun(req: RunRequest): void
  onRunScript(text: string, from: number): void
  onChange(text: string): void
  /** 바깥에서 편집기를 다루는 손잡이(실행 버튼용) */
  handleRef?: (h: EditorHandle | null) => void
}

export interface EditorHandle {
  runCurrent(): void
  runScript(): void
  focus(): void
}

// 실행한 문장을 잠깐 칠해 보여 줌
const flashEffect = StateEffect.define<{ from: number; to: number } | null>()
const flashField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(deco, tr) {
    deco = deco.map(tr.changes)
    for (const e of tr.effects) {
      if (e.is(flashEffect)) {
        deco = e.value && e.value.to > e.value.from ? Decoration.set([Decoration.mark({ class: 'cm-ran' }).range(e.value.from, e.value.to)]) : Decoration.none
      }
    }
    return deco
  },
  provide: (f) => EditorView.decorations.from(f)
})

export function SqlEditor(props: Props) {
  const host = useRef<HTMLDivElement>(null)
  const view = useRef<EditorView | null>(null)
  const lang = useRef(new Compartment())
  const latest = useRef(props)
  latest.current = props

  useEffect(() => {
    const flash = (v: EditorView, from: number, to: number) => {
      v.dispatch({ effects: flashEffect.of({ from, to }) })
      setTimeout(() => v.dispatch({ effects: flashEffect.of(null) }), 700)
    }

    const runCurrent = (v: EditorView): boolean => {
      const { kind, onRun } = latest.current
      const sel = v.state.selection.main
      const doc = v.state.doc.toString()
      if (!sel.empty) {
        flash(v, sel.from, sel.to)
        onRun({ sql: doc.slice(sel.from, sel.to), from: sel.from })
        return true
      }
      const st = statementAt(doc, sel.head, kind)
      if (!st) {
        onRun({ sql: '', from: sel.head })
        return true
      }
      flash(v, st.start, st.end)
      onRun({ sql: st.text, from: st.start })
      return true
    }

    const runScript = (v: EditorView): boolean => {
      const sel = v.state.selection.main
      const doc = v.state.doc.toString()
      if (sel.empty) latest.current.onRunScript(doc, 0)
      else latest.current.onRunScript(doc.slice(sel.from, sel.to), sel.from)
      return true
    }

    const v = new EditorView({
      parent: host.current!,
      state: EditorState.create({
        doc: props.initialText,
        extensions: [
          Prec.highest(
            keymap.of([
              { key: 'Mod-Enter', run: runCurrent },
              { key: 'Alt-x', run: runScript }
            ])
          ),
          basicSetup,
          lang.current.of(sql({ dialect: DIALECT[props.kind], upperCaseKeywords: true })),
          flashField,
          EditorView.updateListener.of((u) => {
            if (u.docChanged) latest.current.onChange(u.state.doc.toString())
          }),
          EditorView.theme({ '&': { height: '100%' }, '.cm-scroller': { fontFamily: 'var(--mono)' } })
        ]
      })
    })
    view.current = v
    props.handleRef?.({ runCurrent: () => runCurrent(v), runScript: () => runScript(v), focus: () => v.focus() })
    v.focus()
    return () => {
      props.handleRef?.(null)
      v.destroy()
      view.current = null
    }
    // 편집기는 탭마다 한 번만 만듦
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 연결의 테이블, 컬럼 목록이 바뀌면 자동완성 설정을 다시 끼움
  useEffect(() => {
    const v = view.current
    if (!v) return
    v.dispatch({
      effects: lang.current.reconfigure(
        sql({
          dialect: DIALECT[props.kind],
          upperCaseKeywords: true,
          schema: (props.completion?.schema ?? {}) as SQLNamespace,
          defaultSchema: props.completion?.defaultSchema
        })
      )
    })
  }, [props.kind, props.completion])

  useEffect(() => {
    if (props.visible) view.current?.focus()
  }, [props.visible])

  return <div className="editor-host" ref={host} />
}

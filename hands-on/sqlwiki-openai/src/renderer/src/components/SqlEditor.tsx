import { useEffect, useImperativeHandle, useRef, forwardRef } from 'react'
import { EditorState } from '@codemirror/state'
import { EditorView, keymap, lineNumbers, highlightActiveLineGutter } from '@codemirror/view'
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands'
import { autocompletion } from '@codemirror/autocomplete'
import { bracketMatching, defaultHighlightStyle, HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { sql, SQLite, PostgreSQL, MySQL } from '@codemirror/lang-sql'
import { tags } from '@lezer/highlight'
import type { Engine, SchemaInfo, TableDetails } from '../../../shared/types'

export interface SqlEditorHandle {
  selectedText(): string
  cursor(): number
  focus(): void
}

interface Props {
  value: string
  engine: Engine
  schema?: SchemaInfo
  details?: Record<string, TableDetails>
  theme: 'dark' | 'light'
  onChange(value: string): void
  onRunCurrent(): void
  onRunScript(): void
  onSave(): void
}

const dialects = { sqlite: SQLite, postgres: PostgreSQL, mysql: MySQL }

const darkHighlightStyle = HighlightStyle.define([
  { tag: tags.keyword, color: '#c792ea', fontWeight: '600' },
  { tag: [tags.lineComment, tags.blockComment, tags.docComment], color: '#7f91a4', fontStyle: 'italic' },
  { tag: [tags.string, tags.special(tags.string)], color: '#b5d98b' },
  { tag: [tags.number, tags.bool, tags.null], color: '#f6bd74' },
  { tag: [tags.operator, tags.compareOperator, tags.logicOperator], color: '#89ddff' },
  { tag: [tags.typeName, tags.className], color: '#82d2ce' },
  { tag: [tags.variableName, tags.propertyName], color: '#e8edf2' },
  { tag: tags.definition(tags.variableName), color: '#ffcb6b' },
  { tag: [tags.punctuation, tags.separator], color: '#aab8c5' },
  { tag: tags.invalid, color: '#ff737d', textDecoration: 'underline' }
])

function completionSchema(schema?: SchemaInfo, details?: Record<string, TableDetails>) {
  const namespace: Record<string, Record<string, readonly string[]> | readonly string[]> = {}
  for (const table of schema?.tables ?? []) {
    const columns = details?.[`${table.schema}:${table.name}`]?.columns.map((column) => column.name) ?? []
    if (!table.schema || table.schema === 'main') namespace[table.name] = columns
    else {
      const group = namespace[table.schema]
      const tables: Record<string, readonly string[]> = group && !Array.isArray(group)
        ? group as Record<string, readonly string[]> : {}
      tables[table.name] = columns
      namespace[table.schema] = tables
    }
  }
  return namespace
}

export const SqlEditor = forwardRef<SqlEditorHandle, Props>(function SqlEditor(props, ref) {
  const host = useRef<HTMLDivElement>(null)
  const viewRef = useRef<EditorView | null>(null)
  const callbacks = useRef(props)
  callbacks.current = props

  useImperativeHandle(ref, () => ({
    selectedText: () => {
      const view = viewRef.current
      if (!view) return ''
      const { from, to } = view.state.selection.main
      return from === to ? '' : view.state.sliceDoc(from, to)
    },
    cursor: () => viewRef.current?.state.selection.main.head ?? 0,
    focus: () => viewRef.current?.focus()
  }), [])

  useEffect(() => {
    if (!host.current) return
    const state = EditorState.create({
      doc: props.value,
      extensions: [
        lineNumbers(), highlightActiveLineGutter(), history(), bracketMatching(),
        syntaxHighlighting(props.theme === 'dark' ? darkHighlightStyle : defaultHighlightStyle, { fallback: true }),
        sql({ dialect: dialects[props.engine], schema: completionSchema(props.schema, props.details), upperCaseKeywords: true }),
        autocompletion({ activateOnTyping: true }),
        EditorView.lineWrapping,
        EditorView.updateListener.of((update) => {
          if (update.docChanged) callbacks.current.onChange(update.state.doc.toString())
        }),
        keymap.of([
          { key: 'Mod-Enter', run: () => { callbacks.current.onRunCurrent(); return true } },
          { key: 'Alt-x', run: () => { callbacks.current.onRunScript(); return true } },
          { key: 'Mod-s', run: () => { callbacks.current.onSave(); return true }, preventDefault: true },
          indentWithTab, ...defaultKeymap, ...historyKeymap
        ]),
        EditorView.theme({
          '&': { height: '100%', fontSize: '13px', backgroundColor: 'transparent' },
          '.cm-scroller': { fontFamily: "'Cascadia Code', 'SFMono-Regular', Consolas, monospace", lineHeight: '1.65' },
          '.cm-content': { padding: '14px 0' },
          '.cm-gutters': { backgroundColor: 'transparent', border: 'none', color: 'var(--muted-2)' },
          '.cm-activeLine, .cm-activeLineGutter': { backgroundColor: 'var(--active-line)' },
          '.cm-cursor': { borderLeftColor: 'var(--kiwi)' },
          '.cm-selectionBackground, &.cm-focused .cm-selectionBackground': { backgroundColor: 'var(--selection) !important' },
          '.cm-tooltip': { backgroundColor: 'var(--panel-solid)', color: 'var(--text)', border: '1px solid var(--line)' },
          '.cm-tooltip-autocomplete > ul > li[aria-selected]': { backgroundColor: 'var(--kiwi-dim)', color: 'var(--text)' }
        }, { dark: props.theme === 'dark' })
      ]
    })
    const view = new EditorView({ state, parent: host.current })
    viewRef.current = view
    return () => { view.destroy(); viewRef.current = null }
  }, [props.details, props.engine, props.schema, props.theme])

  useEffect(() => {
    const view = viewRef.current
    if (!view) return
    const current = view.state.doc.toString()
    if (current !== props.value) {
      view.dispatch({ changes: { from: 0, to: current.length, insert: props.value } })
    }
  }, [props.value])

  return <div className="sql-editor" ref={host} aria-label="SQL 편집기" />
})

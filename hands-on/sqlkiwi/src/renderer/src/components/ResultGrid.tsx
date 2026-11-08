// 결과 그리드
// - 가상 스크롤로 보이는 행만 그림
// - 스크롤이 끝에 닿으면 다음 200행을 자동으로 가져옴(DBeaver resultset.autofetch.next.segment 기본값과 같음)
// - NULL은 [NULL], 바이너리는 16진 미리보기, 숫자와 날짜 열은 오른쪽 정렬
// - 셀을 누르고 Shift로 범위를 넓혀 Ctrl+C로 복사(탭 구분, 값에 탭이나 줄바꿈이 있을 때만 따옴표)
import { useEffect, useMemo, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import type { CellValue, ColumnInfo } from '@shared/types'

export type SortDir = 'asc' | 'desc'

interface Props {
  columns: ColumnInfo[]
  rows: CellValue[][]
  canFetchMore: boolean
  loading: boolean
  sort?: { col: number; dir: SortDir }
  onNeedMore(): void
  onSort(col: number): void
}

interface Sel {
  r1: number
  c1: number
  r2: number
  c2: number
}

const ROW_H = 26
const NUMERIC = /int|float|double|real|numeric|decimal|number|serial|money/
const TEMPORAL = /date|time/

export function displayValue(v: CellValue): string {
  if (v === null) return '[NULL]'
  if (typeof v === 'object') return `0x${v.preview}${v.bytes > 32 ? '...' : ''}`
  return String(v)
}

/** 복사용 값: NULL은 빈 문자열(DBeaver 복사 형식과 같음) */
function copyValue(v: CellValue): string {
  if (v === null) return ''
  const s = typeof v === 'object' ? `0x${v.preview}` : String(v)
  return /[\t\n\r"]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export function ResultGrid({ columns, rows, canFetchMore, loading, sort, onNeedMore, onSort }: Props) {
  const scroller = useRef<HTMLDivElement>(null)
  const [sel, setSel] = useState<Sel | null>(null)

  const rightAlign = useMemo(
    () =>
      columns.map((c, i) => {
        if (c.type && (NUMERIC.test(c.type) || TEMPORAL.test(c.type))) return true
        // 형 정보가 없으면 처음 몇 행의 값으로 판단
        const sample = rows.slice(0, 20).map((r) => r[i]).filter((v) => v !== null)
        return sample.length > 0 && sample.every((v) => typeof v === 'number')
      }),
    [columns, rows]
  )

  // 열 너비: 머리글(이름, 자료형, 정렬 표시)과 처음 50행 글자 수로 정함(최소 60px, 최대 360px)
  const widths = useMemo(
    () =>
      columns.map((c, i) => {
        const head = c.name.length * 8 + (c.type ? c.type.length * 6.5 + 6 : 0) + 34
        const body = Math.max(0, ...rows.slice(0, 50).map((r) => displayValue(r[i]).length)) * 7.6 + 18
        return Math.round(Math.min(360, Math.max(60, head, body)))
      }),
    [columns, rows]
  )
  const rowNumW = Math.max(48, String(rows.length).length * 9 + 20)
  const totalW = rowNumW + widths.reduce((a, b) => a + b, 0)

  const virt = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => ROW_H,
    overscan: 12
  })
  const items = virt.getVirtualItems()

  // 마지막 행이 보이면 더 가져옴
  const lastIndex = items.length ? items[items.length - 1].index : -1
  useEffect(() => {
    if (canFetchMore && !loading && rows.length > 0 && lastIndex >= rows.length - 1) onNeedMore()
  }, [lastIndex, rows.length, canFetchMore, loading, onNeedMore])

  useEffect(() => setSel(null), [columns])
  // 정렬이 바뀌면 맨 위로 올림
  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = 0
  }, [sort?.col, sort?.dir])

  const inSel = (r: number, c: number) =>
    sel && r >= Math.min(sel.r1, sel.r2) && r <= Math.max(sel.r1, sel.r2) && c >= Math.min(sel.c1, sel.c2) && c <= Math.max(sel.c1, sel.c2)

  const onKeyDown = (e: React.KeyboardEvent) => {
    const mod = e.ctrlKey || e.metaKey
    if (mod && e.key.toLowerCase() === 'a') {
      e.preventDefault()
      setSel({ r1: 0, c1: 0, r2: rows.length - 1, c2: columns.length - 1 })
    } else if (mod && e.key.toLowerCase() === 'c' && sel) {
      e.preventDefault()
      const [ra, rb] = [Math.min(sel.r1, sel.r2), Math.max(sel.r1, sel.r2)]
      const [ca, cb] = [Math.min(sel.c1, sel.c2), Math.max(sel.c1, sel.c2)]
      const lines: string[] = []
      if (e.shiftKey) lines.push(columns.slice(ca, cb + 1).map((c) => c.name).join('\t')) // Ctrl+Shift+C: 머리글 포함
      for (let r = ra; r <= rb; r++) lines.push(rows[r].slice(ca, cb + 1).map(copyValue).join('\t'))
      void navigator.clipboard.writeText(lines.join('\n'))
    } else if (sel && ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
      e.preventDefault()
      const dr = e.key === 'ArrowUp' ? -1 : e.key === 'ArrowDown' ? 1 : 0
      const dc = e.key === 'ArrowLeft' ? -1 : e.key === 'ArrowRight' ? 1 : 0
      const r = clamp(sel.r2 + dr, 0, rows.length - 1)
      const c = clamp(sel.c2 + dc, 0, columns.length - 1)
      setSel(e.shiftKey ? { ...sel, r2: r, c2: c } : { r1: r, c1: c, r2: r, c2: c })
      virt.scrollToIndex(r)
    }
  }

  return (
    <div className="grid" ref={scroller} tabIndex={0} onKeyDown={onKeyDown}>
      <div style={{ width: totalW, minWidth: '100%' }}>
        <div className="grid-head" style={{ width: totalW }}>
          <div className="cell rownum head" style={{ width: rowNumW }}>
            #
          </div>
          {columns.map((c, i) => (
            <div
              key={i}
              className="cell head"
              style={{ width: widths[i] }}
              title={`${c.name}${c.type ? ` : ${c.type}` : ''}\n누르면 정렬(오름차순, 내림차순, 해제)`}
              onClick={() => onSort(i)}
            >
              <span className="col-name">{c.name}</span>
              {c.type && <span className="col-type">{c.type}</span>}
              {sort?.col === i && <span className="sort">{sort.dir === 'asc' ? '▲' : '▼'}</span>}
            </div>
          ))}
        </div>
        <div style={{ height: virt.getTotalSize(), position: 'relative' }}>
          {items.map((it) => {
            const row = rows[it.index]
            return (
              <div key={it.key} className={`grid-row ${it.index % 2 ? 'odd' : ''}`} style={{ transform: `translateY(${it.start}px)`, height: ROW_H }}>
                <div className="cell rownum" style={{ width: rowNumW }}>
                  {it.index + 1}
                </div>
                {row.map((v, c) => (
                  <div
                    key={c}
                    className={`cell ${v === null ? 'null' : ''} ${typeof v === 'object' && v ? 'binary' : ''} ${rightAlign[c] ? 'right' : ''} ${inSel(it.index, c) ? 'sel' : ''}`}
                    style={{ width: widths[c] }}
                    title={displayValue(v).length > 40 ? displayValue(v).slice(0, 2000) : undefined}
                    onMouseDown={(e) => {
                      if (e.shiftKey && sel) setSel({ ...sel, r2: it.index, c2: c })
                      else setSel({ r1: it.index, c1: c, r2: it.index, c2: c })
                    }}
                  >
                    {displayValue(v)}
                  </div>
                ))}
              </div>
            )
          })}
        </div>
        {loading && <div className="grid-loading">더 가져오는 중...</div>}
      </div>
    </div>
  )
}

const clamp = (n: number, a: number, b: number) => Math.max(a, Math.min(b, n))

/** 메모리 정렬(모든 행을 이미 받았을 때). NULL은 맨 뒤, 숫자 문자열은 숫자로 비교 */
export function sortRows(rows: CellValue[][], col: number, dir: SortDir): CellValue[][] {
  const num = (v: CellValue) => (typeof v === 'number' ? v : typeof v === 'string' && v.trim() !== '' && !Number.isNaN(Number(v)) ? Number(v) : null)
  const sign = dir === 'asc' ? 1 : -1
  return rows
    .map((r, i) => ({ r, i }))
    .sort((a, b) => {
      const x = a.r[col]
      const y = b.r[col]
      if (x === null || y === null) return x === y ? a.i - b.i : x === null ? 1 : -1
      const nx = num(x)
      const ny = num(y)
      const cmp = nx !== null && ny !== null ? nx - ny : displayValue(x).localeCompare(displayValue(y), 'ko', { sensitivity: 'base' })
      return cmp !== 0 ? cmp * sign : a.i - b.i
    })
    .map((x) => x.r)
}

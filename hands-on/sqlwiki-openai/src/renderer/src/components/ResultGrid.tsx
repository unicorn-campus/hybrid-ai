import { useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, ChevronsUpDown, Copy, Download, Search } from 'lucide-react'
import type { Cell, QueryResult } from '../../../shared/types'

interface Props { result: QueryResult; onExport(columns: string[], rows: Cell[][]): void; onToast(message: string): void }
type Sort = { column: number; direction: 'asc' | 'desc' } | null

const display = (value: Cell) => value === null ? '[NULL]' : String(value)

export function ResultGrid({ result, onExport, onToast }: Props) {
  const [sort, setSort] = useState<Sort>(null)
  const [filter, setFilter] = useState('')
  const [selected, setSelected] = useState<number | null>(null)
  const rows = useMemo(() => {
    const needle = filter.toLocaleLowerCase()
    const filtered = needle ? result.rows.filter((row) => row.some((cell) => display(cell).toLocaleLowerCase().includes(needle))) : result.rows
    if (!sort) return filtered
    return [...filtered].sort((a, b) => {
      const av = a[sort.column], bv = b[sort.column]
      if (av === bv) return 0
      if (av === null) return 1
      if (bv === null) return -1
      const value = typeof av === 'number' && typeof bv === 'number' ? av - bv : String(av).localeCompare(String(bv))
      return sort.direction === 'asc' ? value : -value
    })
  }, [filter, result.rows, sort])

  const toggleSort = (column: number) => setSort((current) =>
    !current || current.column !== column ? { column, direction: 'asc' }
      : current.direction === 'asc' ? { column, direction: 'desc' } : null)

  const copyRow = async () => {
    if (selected === null) return
    const row = rows[selected]
    if (!row) { setSelected(null); return }
    try {
      await navigator.clipboard.writeText(row.map((cell) => cell === null ? '' : String(cell)).join('\t'))
      onToast('선택한 행을 탭 구분 형식으로 복사했습니다.')
    } catch (error) { onToast(`복사하지 못했습니다: ${error instanceof Error ? error.message : String(error)}`) }
  }

  const copyCell = async (cell: Cell) => {
    try { await navigator.clipboard.writeText(cell === null ? '' : String(cell)); onToast('셀 값을 복사했습니다.') }
    catch (error) { onToast(`복사하지 못했습니다: ${error instanceof Error ? error.message : String(error)}`) }
  }

  if (result.error) return (
    <div className="query-error" role="alert">
      <span className="error-mark">!</span>
      <div><strong>쿼리를 실행하지 못했습니다.</strong><pre>{result.error}</pre></div>
    </div>
  )

  if (!result.columns.length) return (
    <div className="empty-result"><span className="success-mark">✓</span><strong>{result.affectedRows}개 행에 반영했습니다.</strong></div>
  )

  return <div className="result-grid-wrap">
    <div className="grid-tools">
      <label className="grid-search"><Search size={13} /><span className="sr-only">결과 검색</span>
        <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="결과에서 찾기" />
      </label>
      <span>{rows.length}{result.truncated ? '+' : ''}행</span>
      <button className="icon-text" onClick={copyRow} disabled={selected === null} title="선택한 행 복사"><Copy size={13} /> 복사</button>
      <button className="icon-text" onClick={() => onExport(result.columns, rows)} title="CSV로 내보내기"><Download size={13} /> CSV</button>
    </div>
    <div className="grid-scroller">
      <table className="result-table">
        <thead><tr><th className="row-number">#</th>{result.columns.map((column, index) => <th key={`${column}-${index}`}>
          <button onClick={() => toggleSort(index)}>{column}{sort?.column !== index ? <ChevronsUpDown size={12} /> : sort.direction === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} />}</button>
        </th>)}</tr></thead>
        <tbody>{rows.map((row, rowIndex) => <tr key={rowIndex} className={selected === rowIndex ? 'selected' : ''} onClick={() => setSelected(rowIndex)}>
          <td className="row-number">{rowIndex + 1}</td>{row.map((cell, columnIndex) => <td key={columnIndex} onDoubleClick={() => void copyCell(cell)} className={cell === null ? 'null-cell' : typeof cell === 'number' ? 'number-cell' : ''} title={`${display(cell)} (두 번 클릭하여 복사)`}>{display(cell)}</td>)}
        </tr>)}</tbody>
      </table>
      {!rows.length && <div className="no-rows">조건에 맞는 행이 없습니다.</div>}
    </div>
  </div>
}

import type { Cell } from '../shared/types'

function field(value: Cell): string {
  let text = value === null ? '' : String(value)
  // Prevent spreadsheet applications from evaluating a string cell as a formula.
  if (typeof value === 'string' && /^[=+\-@\t\r]/.test(text)) text = `'${text}`
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export function toCsv(columns: string[], rows: Cell[][]): string {
  return '\ufeff' + [columns, ...rows].map(row => row.map(field).join(',')).join('\r\n') + '\r\n'
}

// DB 값을 화면에 넘길 수 있는 값으로 바꿈
// - 큰 정수(bigint)와 10진수는 정밀도를 잃지 않게 문자열로 둠
// - 바이너리는 앞 32바이트만 16진수로 보여 줌(DBeaver resultset.binary.stringMaxLength 기본 32와 같은 취지)
// - 날짜는 DB가 준 문자열을 그대로 쓰고, Date 객체로 오면 DBeaver 기본 형식(yyyy-MM-dd HH:mm:ss.SSS)으로 바꿈
import type { CellValue } from '@shared/types'

const BINARY_PREVIEW_BYTES = 32

const pad = (n: number, w = 2): string => String(n).padStart(w, '0')

export function formatDate(d: Date): string {
  if (Number.isNaN(d.getTime())) return String(d)
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`
  )
}

export function toCell(v: unknown): CellValue {
  if (v === null || v === undefined) return null
  switch (typeof v) {
    case 'string':
    case 'boolean':
      return v
    case 'number':
      return v
    case 'bigint':
      return v.toString()
  }
  if (v instanceof Date) return formatDate(v)
  if (v instanceof Uint8Array) {
    const head = Buffer.from(v.subarray(0, BINARY_PREVIEW_BYTES)).toString('hex')
    return { kind: 'binary', bytes: v.byteLength, preview: head }
  }
  try {
    return JSON.stringify(v, (_k, x) => (typeof x === 'bigint' ? x.toString() : x))
  } catch {
    return String(v)
  }
}

export const toRow = (row: unknown[]): CellValue[] => row.map(toCell)

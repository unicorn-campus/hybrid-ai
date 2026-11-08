import { describe, expect, it } from 'vitest'
import { toCsv } from '../src/main/csv'

describe('CSV export', () => {
  it('preserves Unicode, quotes, delimiters, line breaks, NULL and numeric values', () => {
    expect(toCsv(['이름', '값'], [['a,"b', '두\n줄'], [null, -42]]))
      .toBe('\ufeff이름,값\r\n"a,""b","두\n줄"\r\n,-42\r\n')
  })
  it('escapes formula-like strings but preserves actual negative numbers', () => {
    expect(toCsv(['x'], [['=1+1'], ['+cmd'], ['-1'], ['@SUM(A1)'], [-1]]))
      .toBe("\ufeffx\r\n'=1+1\r\n'+cmd\r\n'-1\r\n'@SUM(A1)\r\n-1\r\n")
  })
})

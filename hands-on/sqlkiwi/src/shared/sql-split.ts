// SQL 스크립트를 문장 단위로 나누는 분리기
//
// DBeaver의 SQLScriptParser 동작을 참고해 새로 만든 것임(코드 복사 아님).
// - 따옴표, 주석 안의 구분자(;)는 무시함
// - 괄호 안, PostgreSQL 달러 따옴표($$ ... $$) 안, SQLite 트리거의 BEGIN ... END 안도 무시함
// - 빈 줄도 문장 경계로 봄(DBeaver 기본값 BLANK_LINE_AND_SEPARATOR와 같음)
// - MySQL의 DELIMITER 명령으로 구분자를 바꿀 수 있음
// - 주석만 있는 조각은 문장으로 치지 않음
import type { DbKind } from './types'

interface DialectRules {
  /** 문자열 따옴표 */
  stringQuotes: string[]
  /** 식별자 따옴표: [여는 글자, 닫는 글자] */
  identQuotes: [string, string][]
  /** 문자열 안에서 백슬래시가 다음 글자를 이스케이프하는지 */
  backslashEscape: boolean
  /** '#'도 한 줄 주석인지(MySQL) */
  hashComment: boolean
  /** '--' 뒤에 공백이 있어야 주석인지(MySQL) */
  dashCommentNeedsSpace: boolean
  /** /* 주석이 중첩되는지(PostgreSQL) */
  nestedBlockComments: boolean
  /** $tag$ 달러 따옴표(PostgreSQL) */
  dollarQuotes: boolean
  /** E'...' 문자열 안 백슬래시 이스케이프(PostgreSQL) */
  escapeStringPrefix: boolean
  /** CREATE TRIGGER ... BEGIN ... END 블록(SQLite) */
  triggerBlocks: boolean
  /** DELIMITER 명령(MySQL) */
  delimiterCommand: boolean
}

const RULES: Record<DbKind, DialectRules> = {
  postgres: {
    stringQuotes: ["'"],
    identQuotes: [['"', '"']],
    backslashEscape: false,
    hashComment: false,
    dashCommentNeedsSpace: false,
    nestedBlockComments: true,
    dollarQuotes: true,
    escapeStringPrefix: true,
    triggerBlocks: false,
    delimiterCommand: false
  },
  mysql: {
    stringQuotes: ["'", '"'],
    identQuotes: [['`', '`']],
    backslashEscape: true,
    hashComment: true,
    dashCommentNeedsSpace: true,
    nestedBlockComments: false,
    dollarQuotes: false,
    escapeStringPrefix: false,
    triggerBlocks: false,
    delimiterCommand: true
  },
  sqlite: {
    stringQuotes: ["'"],
    identQuotes: [
      ['"', '"'],
      ['`', '`'],
      ['[', ']']
    ],
    backslashEscape: false,
    hashComment: false,
    dashCommentNeedsSpace: false,
    nestedBlockComments: false,
    dollarQuotes: false,
    escapeStringPrefix: false,
    triggerBlocks: true,
    delimiterCommand: false
  }
}

export interface StatementRange {
  /** 문장 첫 글자 위치(앞 공백 제외, 주석은 포함) */
  start: number
  /** 문장 마지막 글자 다음 위치(구분자와 뒤 공백 제외) */
  end: number
  /** 구분자까지 포함한 끝 위치 */
  delimiterEnd: number
  text: string
}

export interface SplitOptions {
  /** 빈 줄을 문장 경계로 볼지(기본 true) */
  blankLineIsDelimiter?: boolean
}

const isSpace = (c: string): boolean => c === ' ' || c === '\t' || c === '\r' || c === '\n' || c === '\f'
const isIdentStart = (c: string): boolean => /[A-Za-z_\u0080-￿]/.test(c)
const isIdentChar = (c: string): boolean => /[A-Za-z0-9_$\u0080-￿]/.test(c)

/** pos에서 끝나는 줄의 나머지가 공백뿐이고, 다음 줄도 공백뿐이면(빈 줄) true */
function startsBlankLine(text: string, newlinePos: number): boolean {
  // newlinePos는 '\n' 위치. 다음 줄이 공백만으로 이루어지고 '\n' 또는 끝으로 끝나면 빈 줄
  let i = newlinePos + 1
  while (i < text.length && (text[i] === ' ' || text[i] === '\t' || text[i] === '\r')) i++
  return i < text.length && text[i] === '\n'
}

export function splitStatements(text: string, kind: DbKind, options: SplitOptions = {}): StatementRange[] {
  const rules = RULES[kind]
  const blankLine = options.blankLineIsDelimiter ?? true
  const out: StatementRange[] = []

  let delimiter = ';'
  let segStart = -1 // 현재 문장 첫 글자(공백 아닌 글자) 위치
  let lastCodeEnd = -1 // 마지막으로 본 의미 있는 글자 다음 위치(주석 포함)
  let hasCode = false // 주석이 아닌 코드가 있었는지
  let parenDepth = 0
  let blockDepth = 0
  const words: string[] = [] // 문장 앞쪽 단어 몇 개(트리거 판정용)
  let lineStart = true // 현재 위치가 줄의 첫 의미 있는 글자인지(DELIMITER 판정용)
  let afterDelimiterSameLine = false // 구분자 뒤 같은 줄인지(꼬리 주석은 앞 문장 것으로 봄)

  const pushStatement = (delimEnd: number): void => {
    if (segStart >= 0 && hasCode) {
      out.push({ start: segStart, end: lastCodeEnd, delimiterEnd: delimEnd, text: text.slice(segStart, lastCodeEnd) })
    }
    segStart = -1
    lastCodeEnd = -1
    hasCode = false
    parenDepth = 0
    blockDepth = 0
    words.length = 0
  }

  const markStart = (i: number): void => {
    if (segStart < 0) segStart = i
  }

  const inTrigger = (): boolean => {
    if (!rules.triggerBlocks) return false
    // CREATE [TEMP|TEMPORARY] TRIGGER
    if (words[0] !== 'CREATE') return false
    return words[1] === 'TRIGGER' || ((words[1] === 'TEMP' || words[1] === 'TEMPORARY') && words[2] === 'TRIGGER')
  }

  let i = 0
  const n = text.length
  while (i < n) {
    const c = text[i]

    // ---- 공백 ----
    if (isSpace(c)) {
      if (c === '\n') {
        lineStart = true
        afterDelimiterSameLine = false
        if (
          blankLine &&
          segStart >= 0 &&
          parenDepth === 0 &&
          blockDepth === 0 &&
          startsBlankLine(text, i)
        ) {
          pushStatement(lastCodeEnd)
        }
      }
      i++
      continue
    }

    // ---- MySQL DELIMITER 명령(줄 맨 앞, 문장 밖) ----
    if (rules.delimiterCommand && lineStart && segStart < 0 && /^delimiter[ \t]/i.test(text.slice(i, i + 10))) {
      let j = i + 9
      while (j < n && (text[j] === ' ' || text[j] === '\t')) j++
      let k = j
      while (k < n && !isSpace(text[k])) k++
      if (k > j) delimiter = text.slice(j, k)
      while (k < n && text[k] !== '\n') k++
      i = k
      continue
    }
    lineStart = false

    // ---- 한 줄 주석 ----
    const isDash =
      c === '-' &&
      text[i + 1] === '-' &&
      (!rules.dashCommentNeedsSpace || i + 2 >= n || isSpace(text[i + 2]))
    if (isDash || (rules.hashComment && c === '#')) {
      let j = i
      while (j < n && text[j] !== '\n') j++
      // 구분자 뒤 같은 줄의 주석은 앞 문장의 꼬리로 보고 새 문장을 시작하지 않음
      if (!(segStart < 0 && afterDelimiterSameLine)) {
        markStart(i)
        lastCodeEnd = trimEnd(text, i, j)
      }
      i = j
      continue
    }

    // ---- 여러 줄 주석 ----
    if (c === '/' && text[i + 1] === '*') {
      markStart(i)
      let depth = 1
      let j = i + 2
      while (j < n && depth > 0) {
        if (rules.nestedBlockComments && text[j] === '/' && text[j + 1] === '*') {
          depth++
          j += 2
        } else if (text[j] === '*' && text[j + 1] === '/') {
          depth--
          j += 2
        } else j++
      }
      lastCodeEnd = j
      i = j
      continue
    }

    // ---- 구분자 ----
    if (parenDepth === 0 && blockDepth === 0 && text.startsWith(delimiter, i)) {
      pushStatement(i + delimiter.length)
      i += delimiter.length
      afterDelimiterSameLine = true
      continue
    }

    // 여기부터는 코드
    markStart(i)
    hasCode = true

    // ---- 문자열 ----
    const isEString = rules.escapeStringPrefix && (c === 'E' || c === 'e') && text[i + 1] === "'" && !isIdentChar(text[i - 1] ?? ' ')
    if (rules.stringQuotes.includes(c) || isEString) {
      const q = isEString ? "'" : c
      const backslash = rules.backslashEscape || isEString
      let j = isEString ? i + 2 : i + 1
      while (j < n) {
        if (backslash && text[j] === '\\') {
          j += 2
          continue
        }
        if (text[j] === q) {
          if (text[j + 1] === q) {
            j += 2 // '' 는 따옴표 하나
            continue
          }
          j++
          break
        }
        j++
      }
      lastCodeEnd = Math.min(j, n)
      i = lastCodeEnd
      continue
    }

    // ---- 식별자 따옴표 ----
    const ident = rules.identQuotes.find(([open]) => open === c)
    if (ident) {
      const close = ident[1]
      let j = i + 1
      while (j < n) {
        if (text[j] === close) {
          if (close !== ']' && text[j + 1] === close) {
            j += 2
            continue
          }
          j++
          break
        }
        j++
      }
      lastCodeEnd = Math.min(j, n)
      i = lastCodeEnd
      continue
    }

    // ---- 달러 따옴표 $tag$ ... $tag$ ----
    if (rules.dollarQuotes && c === '$' && !isIdentChar(text[i - 1] ?? ' ')) {
      const m = /^\$([A-Za-z_][A-Za-z0-9_]*)?\$/.exec(text.slice(i, i + 64))
      if (m) {
        const tag = m[0]
        const close = text.indexOf(tag, i + tag.length)
        const j = close < 0 ? n : close + tag.length
        lastCodeEnd = j
        i = j
        continue
      }
    }

    // ---- 괄호 ----
    if (c === '(') parenDepth++
    else if (c === ')') parenDepth = Math.max(0, parenDepth - 1)

    // ---- 단어(키워드) ----
    if (isIdentStart(c)) {
      let j = i + 1
      while (j < n && isIdentChar(text[j])) j++
      const word = text.slice(i, j).toUpperCase()
      if (words.length < 4) words.push(word)
      if (inTrigger() && parenDepth === 0) {
        if (word === 'BEGIN' || word === 'CASE') blockDepth++
        else if (word === 'END') blockDepth = Math.max(0, blockDepth - 1)
      }
      lastCodeEnd = j
      i = j
      continue
    }

    i++
    lastCodeEnd = i
  }

  pushStatement(n)
  return out
}

function trimEnd(text: string, from: number, to: number): number {
  let j = to
  while (j > from && isSpace(text[j - 1])) j--
  return j
}

/**
 * 커서가 있는 문장을 고름 (DBeaver의 Ctrl+Enter 동작)
 * - 커서가 문장 안이면 그 문장
 * - 커서가 문장 뒤 같은 줄(구분자 뒤, 줄 끝 주석)이면 방금 끝낸 문장
 * - 커서가 문장 바로 아래 빈 줄이면 윗 문장
 * - 커서가 다음 문장 앞 들여쓰기 위치면 다음 문장
 * - 그 밖(빈 줄 여러 개 사이 등)은 null
 */
export function statementAt(
  text: string,
  cursor: number,
  kind: DbKind,
  options: SplitOptions = {}
): StatementRange | null {
  const list = splitStatements(text, kind, options)
  for (const r of list) {
    if (cursor >= r.start && cursor <= r.end) return r
  }
  const prev = [...list].reverse().find((r) => r.end < cursor)
  if (prev) {
    const between = text.slice(prev.end, cursor)
    const newlines = (between.match(/\n/g) ?? []).length
    if (newlines === 0) return prev
    if (newlines === 1 && isBlankLineAt(text, cursor)) return prev
  }
  const next = list.find((r) => r.start > cursor)
  if (next && !text.slice(cursor, next.start).includes('\n')) return next
  return null
}

function isBlankLineAt(text: string, pos: number): boolean {
  let a = pos
  while (a > 0 && text[a - 1] !== '\n') a--
  let b = pos
  while (b < text.length && text[b] !== '\n') b++
  return text.slice(a, b).trim() === ''
}

/** 데이터를 바꾸는 문장인지(읽기 전용 연결 차단, 위험 문장 확인용) */
export function firstKeyword(sql: string): string {
  const stripped = sql
    .replace(/^\s*(--[^\n]*\n|#[^\n]*\n|\/\*[\s\S]*?\*\/|\s)+/, '')
    .trimStart()
  const m = /^[A-Za-z]+/.exec(stripped)
  return m ? m[0].toUpperCase() : ''
}

/** WHERE 없는 DELETE, UPDATE처럼 확인이 필요한 문장인지(DBeaver의 isDeleteUpdateDangerous와 같은 목적) */
export function isDangerous(sql: string): boolean {
  const kw = firstKeyword(sql)
  const body = sql.toUpperCase()
  if ((kw === 'DELETE' || kw === 'UPDATE') && !/\bWHERE\b/.test(body)) return true
  if (kw === 'DROP' && /^\s*DROP\s+(TABLE|DATABASE|SCHEMA)\b/i.test(sql.replace(/^\s*(--[^\n]*\n|\/\*[\s\S]*?\*\/)+/, '')))
    return true
  if (kw === 'TRUNCATE') return true
  return false
}

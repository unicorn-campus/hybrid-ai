export interface SqlStatement {
  text: string
  start: number
  end: number
}

type Dialect = 'sqlite' | 'postgres' | 'mysql'

/** SQL 문자열과 주석 안의 구분자를 건드리지 않고 실행 단위로 나눔. */
export function splitSql(source: string, dialect: Dialect = 'sqlite'): SqlStatement[] {
  const result: SqlStatement[] = []
  let start = 0
  let index = 0
  let delimiter = ';'
  let quote: "'" | '"' | '`' | ']' | null = null
  let backslashEscapes = false
  let dollarTag: string | null = null
  let lineComment = false
  let blockDepth = 0

  const push = (end: number, delimiterLength = 0): void => {
    const raw = source.slice(start, end)
    const left = raw.search(/\S/)
    if (left >= 0) {
      const right = raw.search(/\s*$/)
      const textEnd = right >= 0 ? right : raw.length
      const text = raw.slice(left, textEnd)
      if (stripComments(text).trim()) result.push({ text, start: start + left, end: start + textEnd })
    }
    start = end + delimiterLength
  }

  while (index < source.length) {
    const current = source[index]
    const next = source[index + 1]

    if (lineComment) {
      if (current === '\n') lineComment = false
      index += 1
      continue
    }
    if (blockDepth > 0) {
      if (current === '/' && next === '*' && dialect === 'postgres') {
        blockDepth += 1
        index += 2
      } else if (current === '*' && next === '/') {
        blockDepth -= 1
        index += 2
      } else index += 1
      continue
    }
    if (dollarTag) {
      if (source.startsWith(dollarTag, index)) {
        index += dollarTag.length
        dollarTag = null
      } else index += 1
      continue
    }
    if (quote) {
      if (quote === ']' && current === ']') {
        if (next === ']') index += 2
        else { quote = null; index += 1 }
      } else if (current === quote) {
        if (next === quote) index += 2
        else { quote = null; index += 1 }
      } else if (current === '\\' && backslashEscapes) index += 2
      else index += 1
      continue
    }

    if ((index === 0 || source[index - 1] === '\n') && dialect === 'mysql') {
      const line = source.slice(index).match(/^\s*DELIMITER\s+(\S+)\s*(?:\r?\n|$)/i)
      if (line) {
        push(index)
        delimiter = line[1]
        index += line[0].length
        start = index
        continue
      }
    }
    if (current === '-' && next === '-' &&
      (dialect !== 'mysql' || /\s/.test(source[index + 2] ?? ''))) {
      lineComment = true; index += 2; continue
    }
    if (current === '#' && dialect === 'mysql') { lineComment = true; index += 1; continue }
    if (current === '/' && next === '*') { blockDepth = 1; index += 2; continue }
    if (current === "'" || current === '"' || (current === '`' && dialect !== 'postgres')) {
      quote = current as "'" | '"' | '`'
      backslashEscapes = dialect === 'mysql' ||
        (dialect === 'postgres' && current === "'" && /[eE]/.test(source[index - 1] ?? ''))
      index += 1
      continue
    }
    if (current === '[' && dialect === 'sqlite') { quote = ']'; index += 1; continue }
    if (current === '$' && dialect === 'postgres') {
      const match = source.slice(index).match(/^\$[A-Za-z_][A-Za-z0-9_]*\$|^\$\$/)
      if (match) { dollarTag = match[0]; index += match[0].length; continue }
    }
    if (source.startsWith(delimiter, index)) {
      push(index, delimiter.length)
      index += delimiter.length
      continue
    }
    if (delimiter === ';' && (index === 0 || source[index - 1] === '\n')) {
      const go = source.slice(index).match(/^\s*GO\s*(?:\r?\n|$)/i)
      if (go) {
        push(index)
        index += go[0].length
        start = index
        continue
      }
    }
    index += 1
  }
  push(source.length)
  return result
}

export function currentStatement(source: string, cursor: number, dialect: Dialect = 'sqlite'): SqlStatement | null {
  const position = Math.max(0, Math.min(cursor, source.length))
  const statements = splitSql(source, dialect)
  return statements.find((item) => position >= item.start && position <= item.end)
    ?? [...statements].reverse().find((item) => item.end <= position)
    ?? null
}

export function dangerousSql(sql: string): string | null {
  const words = topLevelWords(sql)
  const destructive = words.find((word) => word.value === 'drop' || word.value === 'truncate')
  if (destructive) return destructive.value.toUpperCase()
  const mutationIndex = words.findIndex((word) => word.value === 'delete' || word.value === 'update')
  if (mutationIndex >= 0 && !words.slice(mutationIndex + 1).some((word) => word.value === 'where')) {
    return 'WHERE 없는 UPDATE/DELETE'
  }
  return null
}

export function isReadOnlySql(sql: string): boolean {
  const words = topLevelWords(sql).map((item) => item.value)
  if (words.some((word) => ['insert', 'update', 'delete', 'merge', 'replace', 'create', 'alter', 'drop',
    'truncate', 'vacuum', 'attach', 'detach', 'reindex'].includes(word))) return false
  return ['select', 'show', 'describe', 'desc', 'explain', 'pragma', 'with'].includes(words[0] ?? '')
}

export function quoteIdentifier(value: string, dialect: Dialect): string {
  if (dialect === 'mysql') return '`' + value.replace(/`/g, '``') + '`'
  return '"' + value.replace(/"/g, '""') + '"'
}

function stripComments(sql: string): string {
  return sql.replace(/--[^\r\n]*/g, ' ').replace(/#[^\r\n]*/g, ' ').replace(/\/\*[\s\S]*?\*\//g, ' ')
}

function topLevelWords(sql: string): Array<{ value: string; position: number }> {
  const result: Array<{ value: string; position: number }> = []
  let index = 0
  let depth = 0
  let quote: string | null = null
  let lineComment = false
  let blockComment = false
  let dollar: string | null = null
  while (index < sql.length) {
    const current = sql[index]
    const next = sql[index + 1]
    if (lineComment) { if (current === '\n') lineComment = false; index += 1; continue }
    if (blockComment) {
      if (current === '*' && next === '/') { blockComment = false; index += 2 } else index += 1
      continue
    }
    if (dollar) {
      if (sql.startsWith(dollar, index)) { index += dollar.length; dollar = null } else index += 1
      continue
    }
    if (quote) {
      const close = quote === '[' ? ']' : quote
      if (current === close) {
        if (next === close) index += 2
        else { quote = null; index += 1 }
      } else if (current === '\\') index += 2
      else index += 1
      continue
    }
    if (current === '-' && next === '-') { lineComment = true; index += 2; continue }
    if (current === '#') { lineComment = true; index += 1; continue }
    if (current === '/' && next === '*') { blockComment = true; index += 2; continue }
    if (current === "'" || current === '"' || current === '`' || current === '[') { quote = current; index += 1; continue }
    if (current === '$') {
      const match = sql.slice(index).match(/^\$[A-Za-z_][A-Za-z0-9_]*\$|^\$\$/)
      if (match) { dollar = match[0]; index += match[0].length; continue }
    }
    if (current === '(') { depth += 1; index += 1; continue }
    if (current === ')') { depth = Math.max(0, depth - 1); index += 1; continue }
    if (depth === 0 && /[A-Za-z_]/.test(current)) {
      const match = sql.slice(index).match(/^[A-Za-z_][A-Za-z0-9_$]*/i)![0]
      result.push({ value: match.toLowerCase(), position: index })
      index += match.length
      continue
    }
    index += 1
  }
  return result
}

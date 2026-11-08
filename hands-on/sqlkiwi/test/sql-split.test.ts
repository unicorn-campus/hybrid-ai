import { describe, expect, it } from 'vitest'
import { isDangerous, splitStatements, statementAt } from '../src/shared/sql-split'

const texts = (sql: string, kind: 'postgres' | 'mysql' | 'sqlite') => splitStatements(sql, kind).map((s) => s.text)

describe('splitStatements 공통', () => {
  it('세미콜론으로 나눔', () => {
    expect(texts('select 1; select 2;', 'postgres')).toEqual(['select 1', 'select 2'])
  })
  it('마지막 문장은 세미콜론이 없어도 됨', () => {
    expect(texts('select 1;\nselect 2', 'sqlite')).toEqual(['select 1', 'select 2'])
  })
  it('따옴표와 주석 안의 세미콜론은 무시', () => {
    const sql = "select 'a;b' as x; -- c;d\nselect \"x;y\" from t /* ; */;"
    expect(texts(sql, 'postgres')).toEqual(["select 'a;b' as x", 'select "x;y" from t /* ; */'])
  })
  it("'' 이스케이프를 문자열 끝으로 착각하지 않음", () => {
    expect(texts("select 'it''s;ok'; select 2", 'sqlite')).toEqual(["select 'it''s;ok'", 'select 2'])
  })
  it('빈 줄은 문장 경계(DBeaver 기본값)', () => {
    expect(texts('select 1\n\nselect 2', 'postgres')).toEqual(['select 1', 'select 2'])
  })
  it('빈 줄 구분을 끌 수 있음', () => {
    expect(splitStatements('select 1\n\nfrom t', 'postgres', { blankLineIsDelimiter: false }).map((s) => s.text)).toEqual([
      'select 1\n\nfrom t'
    ])
  })
  it('괄호 안 빈 줄은 경계가 아님', () => {
    expect(texts('select (\n\n1);', 'postgres')).toEqual(['select (\n\n1)'])
  })
  it('주석만 있는 조각은 문장이 아님', () => {
    expect(texts('-- 메모\n\nselect 1;', 'postgres')).toEqual(['select 1'])
  })
  it('문장 바로 위 주석은 문장에 포함', () => {
    expect(texts('-- 고객 조회\nselect 1;', 'postgres')).toEqual(['-- 고객 조회\nselect 1'])
  })
  it('구분자 뒤 같은 줄 주석은 다음 문장에 붙지 않음', () => {
    expect(texts('select 1; -- 끝\nselect 2;', 'postgres')).toEqual(['select 1', 'select 2'])
  })
})

describe('PostgreSQL 방언', () => {
  it('달러 따옴표 안의 세미콜론은 무시', () => {
    const fn = 'create function f() returns int as $$ begin return 1; end; $$ language plpgsql'
    expect(texts(`${fn};\nselect f();`, 'postgres')).toEqual([fn, 'select f()'])
  })
  it('태그 달린 달러 따옴표', () => {
    const fn = 'do $body$ begin perform 1; end $body$'
    expect(texts(`${fn}; select 2`, 'postgres')).toEqual([fn, 'select 2'])
  })
  it('$1 매개변수는 달러 따옴표가 아님', () => {
    expect(texts('select $1; select 2', 'postgres')).toEqual(['select $1', 'select 2'])
  })
  it("E'...' 안 백슬래시 이스케이프", () => {
    expect(texts("select E'a\\';b'; select 2", 'postgres')).toEqual(["select E'a\\';b'", 'select 2'])
  })
  it('중첩 주석', () => {
    expect(texts('/* a /* b; */ c; */ select 1; select 2', 'postgres')).toEqual([
      '/* a /* b; */ c; */ select 1',
      'select 2'
    ])
  })
  it('BEGIN; 은 블록이 아니라 트랜잭션 문장', () => {
    expect(texts('begin; update t set a=1; commit;', 'postgres')).toEqual(['begin', 'update t set a=1', 'commit'])
  })
})

describe('MySQL 방언', () => {
  it('# 주석과 백틱 식별자', () => {
    expect(texts('# 메모;\nselect `a;b` from t; select 2', 'mysql')).toEqual(['# 메모;\nselect `a;b` from t', 'select 2'])
  })
  it('문자열 안 백슬래시 이스케이프', () => {
    expect(texts("select 'a\\';b'; select 2", 'mysql')).toEqual(["select 'a\\';b'", 'select 2'])
  })
  it('--뒤에 공백이 없으면 주석이 아님(MySQL 규칙)', () => {
    expect(texts('select 1--2; select 3', 'mysql')).toEqual(['select 1--2', 'select 3'])
  })
  it('DELIMITER 명령으로 프로시저 본문을 한 문장으로', () => {
    const sql = [
      'DELIMITER //',
      'CREATE PROCEDURE p()',
      'BEGIN',
      '  SELECT 1;',
      '  SELECT 2;',
      'END //',
      'DELIMITER ;',
      'CALL p();'
    ].join('\n')
    expect(texts(sql, 'mysql')).toEqual(['CREATE PROCEDURE p()\nBEGIN\n  SELECT 1;\n  SELECT 2;\nEND', 'CALL p()'])
  })
})

describe('SQLite 방언', () => {
  it('트리거의 BEGIN ... END 안 세미콜론은 무시', () => {
    const trg = 'CREATE TRIGGER trg AFTER INSERT ON t BEGIN\n  UPDATE c SET n = n + 1;\n  INSERT INTO log VALUES (1);\nEND'
    expect(texts(`${trg};\nselect 1;`, 'sqlite')).toEqual([trg, 'select 1'])
  })
  it('트리거 안 CASE ... END', () => {
    const trg = "CREATE TEMP TRIGGER t2 AFTER UPDATE ON t BEGIN SELECT CASE WHEN 1 THEN 'a' END; END"
    expect(texts(`${trg}; select 2`, 'sqlite')).toEqual([trg, 'select 2'])
  })
  it('트리거 밖 BEGIN; 은 트랜잭션', () => {
    expect(texts('begin; insert into t values(1); commit;', 'sqlite')).toEqual(['begin', 'insert into t values(1)', 'commit'])
  })
  it('대괄호 식별자', () => {
    expect(texts('select [a;b] from t; select 2', 'sqlite')).toEqual(['select [a;b] from t', 'select 2'])
  })
})

describe('statementAt (Ctrl+Enter)', () => {
  const sql = 'select 1;\nselect 2\nfrom t;\n\n\nselect 3;'
  //           0         10
  it('커서가 문장 안', () => {
    expect(statementAt(sql, sql.indexOf('from'), 'postgres')?.text).toBe('select 2\nfrom t')
  })
  it('구분자 바로 뒤면 방금 끝낸 문장', () => {
    expect(statementAt(sql, sql.indexOf(';') + 1, 'postgres')?.text).toBe('select 1')
  })
  it('문장 바로 아래 빈 줄이면 윗 문장', () => {
    const pos = sql.indexOf('from t;') + 'from t;'.length + 1
    expect(statementAt(sql, pos, 'postgres')?.text).toBe('select 2\nfrom t')
  })
  it('빈 줄 여러 개 사이 가운데면 없음', () => {
    const pos = sql.indexOf('from t;') + 'from t;'.length + 2
    expect(statementAt(sql, pos, 'postgres')).toBeNull()
  })
  it('문장 앞 들여쓰기 위치면 다음 문장', () => {
    expect(statementAt('select 1;\n   select 2;', 12, 'postgres')?.text).toBe('select 2')
  })
  it('빈 줄 없이 이어진 여러 줄 문장은 하나', () => {
    expect(statementAt('select a,\n  b\nfrom t', 3, 'postgres')?.text).toBe('select a,\n  b\nfrom t')
  })
})

describe('isDangerous', () => {
  it('WHERE 없는 DELETE와 UPDATE', () => {
    expect(isDangerous('delete from t')).toBe(true)
    expect(isDangerous('update t set a = 1')).toBe(true)
    expect(isDangerous('delete from t where id = 1')).toBe(false)
  })
  it('DROP TABLE, TRUNCATE', () => {
    expect(isDangerous('drop table t')).toBe(true)
    expect(isDangerous('truncate t')).toBe(true)
    expect(isDangerous('select 1')).toBe(false)
  })
})

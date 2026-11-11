import { describe, expect, it } from 'vitest'
import { currentStatement, dangerousSql, isReadOnlySql, quoteIdentifier, splitSql } from '../src/shared/sql'

describe('SQL 분할과 안전 판정', () => {
  it('문자열, 주석, PostgreSQL 달러 따옴표 안의 구분자를 보존함', () => {
    const sql = "select ';' as value; -- ;\nselect $$a;b$$ as body; select 3"
    expect(splitSql(sql, 'postgres').map((item) => item.text)).toEqual([
      "select ';' as value", '-- ;\nselect $$a;b$$ as body', 'select 3'
    ])
  })

  it('MySQL DELIMITER로 프로시저 본문을 한 문장으로 유지함', () => {
    const sql = 'DELIMITER //\nCREATE PROCEDURE p() BEGIN SELECT 1; SELECT 2; END//\nDELIMITER ;\nSELECT 3;'
    expect(splitSql(sql, 'mysql').map((item) => item.text)).toEqual([
      'CREATE PROCEDURE p() BEGIN SELECT 1; SELECT 2; END', 'SELECT 3'
    ])
  })

  it('CTE 뒤 변경문과 문자열을 구분하여 위험 SQL을 판정함', () => {
    expect(dangerousSql("DELETE FROM customers RETURNING 'where'")).toBe('WHERE 없는 UPDATE/DELETE')
    expect(dangerousSql('WITH old AS (SELECT 1) DELETE FROM customers')).toBe('WHERE 없는 UPDATE/DELETE')
    expect(dangerousSql('UPDATE customers SET city=\'somewhere\' WHERE id=1')).toBeNull()
    expect(dangerousSql('TRUNCATE TABLE customers')).toBe('TRUNCATE')
    expect(isReadOnlySql('WITH x AS (SELECT 1) SELECT * FROM x')).toBe(true)
    expect(isReadOnlySql('WITH x AS (SELECT 1) DELETE FROM customers WHERE id=1')).toBe(false)
  })

  it('커서 문장과 방언별 식별자 인용을 반환함', () => {
    const sql = 'SELECT 1;\nSELECT 2;'
    expect(currentStatement(sql, sql.indexOf('2'))?.text).toBe('SELECT 2')
    expect(quoteIdentifier('a`b', 'mysql')).toBe('`a``b`')
    expect(quoteIdentifier('a"b', 'postgres')).toBe('"a""b"')
  })
})

import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { createService, type SqlkiwiService } from '../src/main/service'

const directories: string[] = []
const services: SqlkiwiService[] = []

async function fixture(): Promise<{ service: SqlkiwiService; directory: string; demoId: string }> {
  const directory = await mkdtemp(join(tmpdir(), 'sqlkiwi-engine-'))
  directories.push(directory)
  const codec = { encrypt: (value: string) => Buffer.from(`protected:${value}`).toString('base64'),
    decrypt: (value: string) => Buffer.from(value, 'base64').toString().slice('protected:'.length) }
  const service = createService(directory, codec)
  services.push(service)
  const { demoId } = await service.bootstrap()
  return { service, directory, demoId }
}

afterEach(async () => {
  await Promise.all(services.splice(0).map((service) => service.dispose()))
  await Promise.all(directories.splice(0).map((directory) => rm(directory, { recursive: true, force: true })))
})

describe('SqlkiwiService SQLite 통합', () => {
  it('예제 DB의 스키마, 데이터, 상세 정보를 실제로 읽음', async () => {
    const { service, demoId } = await fixture()
    const connected = await service.connect(demoId)
    expect(connected.version).toMatch(/^SQLite 3\./)
    expect(connected.schema.tables.map((table) => table.name)).toEqual(
      expect.arrayContaining(['customers', 'orders', 'products', 'order_items']))

    const details = await service.tableDetails(demoId, { schema: '', name: 'customers', type: 'table' })
    expect(details.columns.find((column) => column.name === 'id')?.primaryKey).toBe(true)
    expect(details.ddl).toContain('CREATE TABLE customers')

    const [result] = await service.query({ connectionId: demoId,
      sql: 'SELECT id, name, city FROM customers ORDER BY id', limit: 2 })
    expect(result.columns).toEqual(['id', 'name', 'city'])
    expect(result.rows).toHaveLength(2)
    expect(result.rows[0]).toEqual([1, '김민준', '서울'])
    expect(result.truncated).toBe(true)
  })

  it('같은 SQLite 세션에서 트랜잭션을 유지함', async () => {
    const { service, demoId } = await fixture()
    await service.connect(demoId)
    await service.query({ connectionId: demoId,
      sql: "BEGIN; UPDATE customers SET city='인천' WHERE id=1; COMMIT", allowDangerous: true })
    const [result] = await service.query({ connectionId: demoId, sql: 'SELECT city FROM customers WHERE id=1' })
    expect(result.rows[0][0]).toBe('인천')
  })

  it('위험 SQL과 읽기 전용 변경을 실행 전에 차단함', async () => {
    const { service, demoId } = await fixture()
    const bootstrap = await service.bootstrap()
    const demo = bootstrap.connections.find((item) => item.id === demoId)!
    await service.connect(demoId)
    await expect(service.query({ connectionId: demoId, sql: "DELETE FROM customers RETURNING 'where'" }))
      .rejects.toThrow(/^DANGEROUS_SQL:/)
    await service.disconnect(demoId)
    const readonly = await service.saveConnection({ ...demo, id: 'readonly', name: '읽기 전용', readOnly: true })
    await service.connect(readonly.id)
    await expect(service.query({ connectionId: readonly.id,
      sql: "UPDATE customers SET city='서울' WHERE id=1", allowDangerous: true })).rejects.toThrow(/^READ_ONLY_CONNECTION:/)
  })

  it('암호화한 비밀번호만 저장하고 공개 프로필에는 평문을 반환하지 않음', async () => {
    const { service, directory } = await fixture()
    const saved = await service.saveConnection({ id: 'pg', name: 'PG', engine: 'postgres',
      host: 'localhost', database: 'demo', username: 'kiwi', password: 'top-secret' })
    expect(saved.password).toBeUndefined()
    expect(saved.hasPassword).toBe(true)
    const state = await readFile(join(directory, 'sqlkiwi-state.json'), 'utf8')
    expect(state).not.toContain('top-secret')
    expect(state).toContain(Buffer.from('protected:top-secret').toString('base64'))

    const updated = await service.saveConnection({ ...saved, name: 'PG 수정', password: '' })
    expect(updated.name).toBe('PG 수정')
    expect(updated.hasPassword).toBe(true)
    const updatedState = await readFile(join(directory, 'sqlkiwi-state.json'), 'utf8')
    expect(updatedState).toContain(Buffer.from('protected:top-secret').toString('base64'))
  })

  it('실행 기록을 남기고 지울 수 있음', async () => {
    const { service, demoId } = await fixture()
    await service.connect(demoId)
    await service.query({ connectionId: demoId, sql: 'SELECT 1 AS one' })
    expect(await service.history()).toHaveLength(1)
    await service.clearHistory()
    expect(await service.history()).toEqual([])
  })

  it('연결 설정을 저장하면 이전 세션을 닫아 새 설정을 강제함', async () => {
    const { service, demoId } = await fixture()
    const bootstrap = await service.bootstrap()
    const demo = bootstrap.connections.find((item) => item.id === demoId)!
    await service.connect(demoId)
    await service.saveConnection({ ...demo, name: '읽기 전용 예제', readOnly: true })
    await expect(service.query({ connectionId: demoId, sql: 'SELECT 1' })).rejects.toThrow(/^NOT_CONNECTED:/)
  })

  it('SQLite 네이티브 실행에 갇힌 쿼리도 프로세스를 종료하여 취소함', async () => {
    const { service, demoId } = await fixture()
    await service.connect(demoId)
    const running = service.query({ connectionId: demoId,
      sql: `WITH RECURSIVE counter(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM counter)
            SELECT sum(x) FROM counter` })
    await new Promise((resolve) => setTimeout(resolve, 100))
    const started = performance.now()
    await service.cancel(demoId)
    await expect(running).rejects.toThrow(/^QUERY_CANCELLED:/)
    expect(performance.now() - started).toBeLessThan(2_000)
  }, 4_000)
})

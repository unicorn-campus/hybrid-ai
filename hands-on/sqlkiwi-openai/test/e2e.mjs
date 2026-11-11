import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright-core'
import { createRequire } from 'node:module'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const require = createRequire(import.meta.url)
const output = resolve('test-results', `run-${Date.now()}`)
const dataDir = resolve(output, 'app-data')
await mkdir(dataDir, { recursive: true })
const env = { ...process.env, SQLKIWI_DATA_DIR: dataDir }
delete env.ELECTRON_RUN_AS_NODE
const launchOptions = { executablePath: process.env.SQLKIWI_EXECUTABLE || require('electron'),
  args: process.env.SQLKIWI_EXECUTABLE ? [] : ['.'], env, timeout: 40_000 }
let app = await electron.launch(launchOptions)
const checks = []
const errors = []
let page
const step = async (name, fn) => {
  let timer
  try {
    await Promise.race([fn(), new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`Timed out: ${name}`)), 25_000)
    })])
  } finally { clearTimeout(timer) }
  checks.push(name)
  console.log(`PASS ${name}`)
}
try {
  page = await app.firstWindow({ timeout: 30_000 })
  page.on('pageerror', error => errors.push(error.message))
  await page.locator('.result-table tbody tr').first().waitFor({ timeout: 30_000 })
  const api = (method, ...args) => page.evaluate(({ method, args }) => window.sqlkiwi[method](...args), { method, args })
  const boot = await api('bootstrap')
  const demo = boot.demoId
  await step('startup renders real sample JOIN results', async () => {
    assert.equal(await page.title(), 'sqlkiwi')
    assert.ok(await page.locator('.result-table tbody tr').count() >= 3)
    assert.equal(await page.evaluate(() => typeof window.require), 'undefined')
    const prefs = await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.getLastWebPreferences())
    assert.equal(prefs.contextIsolation, true)
    assert.equal(prefs.sandbox, true)
    await page.screenshot({ path: resolve(output, 'workbench-dark.png') })
  })
  await step('SQLite schema, DDL and safe integer values', async () => {
    const schema = await api('schema', demo)
    assert.ok(schema.tables.some(t => t.name === 'customers'))
    const table = await api('tableDetails', demo, schema.tables.find(t => t.name === 'customers'))
    assert.ok(table.columns.some(c => c.name === 'id' && c.primaryKey))
    assert.match(table.ddl, /CREATE TABLE/i)
    const [result] = await api('query', { connectionId: demo, sql: 'SELECT COUNT(*) AS n FROM customers' })
    assert.equal(Number(result.rows[0][0]), 4)
    assert.ok(!result.error)
  })
  await step('SQL quoting, row limit and stop after error', async () => {
    const quoted = await api('query', { connectionId: demo, sql: "SELECT 'a;b' AS txt; -- ;\n SELECT NULL AS empty;" })
    assert.equal(quoted.length, 2)
    assert.equal(quoted[0].rows[0][0], 'a;b')
    assert.equal(quoted[1].rows[0][0], null)
    const [limited] = await api('query', { connectionId: demo, sql: 'WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<350) SELECT x FROM n', limit: 200 })
    assert.equal(limited.rows.length, 200)
    assert.equal(limited.truncated, true)
    const failed = await api('query', { connectionId: demo, sql: 'SELECT 1; SELECT * FROM nonexistent_sqlkiwi_table; SELECT 3' })
    assert.equal(failed.length, 2)
    assert.ok(failed[1].error)
  })
  await step('SQLite transactions persist between executions', async () => {
    await api('query', { connectionId: demo, sql: 'CREATE TABLE IF NOT EXISTS e2e_transactions(value INTEGER)' })
    const begin = await api('query', { connectionId: demo, sql: 'BEGIN' })
    assert.ok(!begin[0].error)
    await api('query', { connectionId: demo, sql: 'INSERT INTO e2e_transactions VALUES(42)' })
    await api('query', { connectionId: demo, sql: 'ROLLBACK' })
    const [count] = await api('query', { connectionId: demo, sql: 'SELECT COUNT(*) FROM e2e_transactions' })
    assert.equal(Number(count.rows[0][0]), 0)
  })
  await step('dangerous SQL requires explicit confirmation', async () => {
    await assert.rejects(api('query', { connectionId: demo, sql: 'DELETE FROM e2e_transactions' }), /DANGEROUS_SQL/)
    await assert.rejects(api('query', { connectionId: demo, sql: "DELETE FROM e2e_transactions RETURNING 'where'" }), /DANGEROUS_SQL/)
    const [confirmed] = await api('query', { connectionId: demo, sql: 'DELETE FROM e2e_transactions', allowDangerous: true })
    assert.ok(!confirmed.error)
  })
  await step('SQLite read-only connection prevents writes', async () => {
    const filename = boot.connections.find(c => c.id === demo).filename
    await api('saveConnection', { id: 'e2e-readonly', name: 'Readonly test', engine: 'sqlite', filename, readOnly: true })
    await api('connect', 'e2e-readonly')
    try {
      const results = await api('query', { connectionId: 'e2e-readonly', sql: 'INSERT INTO e2e_transactions VALUES (99)' })
      assert.ok(results[0].error)
    } catch (error) { assert.match(String(error), /read.only|읽기 전용|READ_ONLY/i) }
    await api('disconnect', 'e2e-readonly')
  })
  await step('long-running SQLite query cancels and connection recovers', async () => {
    await page.evaluate(id => {
      window.__pendingQuery = window.sqlkiwi.query({ connectionId: id,
        sql: 'WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n) SELECT SUM(x) FROM n' })
        .then(value => ({ value }), error => ({ error: String(error) }))
    }, demo)
    await new Promise(resolve => setTimeout(resolve, 150))
    await api('cancel', demo)
    const pending = await page.evaluate(() => window.__pendingQuery)
    assert.ok(pending.error || pending.value?.some(item => item.error))
    await api('connect', demo)
    const [result] = await api('query', { connectionId: demo, sql: 'SELECT 7' })
    assert.equal(Number(result.rows[0][0]), 7)
  })
  if (process.env.SQLKIWI_TEST_REMOTE === '1') {
    for (const engine of ['postgres', 'mysql']) {
      await step(`${engine} real connection, schema, query, transaction and password storage`, async () => {
        const id = `e2e-${engine}`
        const connection = { id, name: `${engine} integration`, engine, host: '127.0.0.1',
          port: engine === 'postgres' ? 55433 : 53307, username: engine === 'postgres' ? 'sqlkiwi' : 'root',
          password: 'local-test-only', database: 'sqlkiwi' }
        const version = await api('testConnection', connection)
        console.log(`  ${engine}: testConnection ${version.version}`)
        assert.ok(version.version)
        const saved = await api('saveConnection', connection)
        assert.equal(saved.password, undefined)
        assert.equal(saved.hasPassword, true)
        const { password, ...withoutPassword } = connection
        await api('saveConnection', { ...withoutPassword, password: '' })
        const connected = await api('connect', id)
        console.log(`  ${engine}: connect`)
        assert.ok(connected.version)
        const initial = await api('query', { connectionId: id,
          sql: 'CREATE TABLE IF NOT EXISTS e2e_data (id INTEGER PRIMARY KEY, name VARCHAR(100)); DELETE FROM e2e_data WHERE id > 0; INSERT INTO e2e_data VALUES(1, \'키위\'); SELECT * FROM e2e_data' })
        console.log(`  ${engine}: script`)
        assert.equal(initial.length, 4)
        assert.ok(initial.every(item => !item.error), JSON.stringify(initial))
        assert.ok(initial[3].rows.length > 0, JSON.stringify(initial))
        assert.equal(initial[3].rows[0][1], '키위')
        const schema = await api('schema', id)
        const table = schema.tables.find(t => t.name === 'e2e_data')
        assert.ok(table)
        const details = await api('tableDetails', id, table)
        console.log(`  ${engine}: tableDetails`)
        assert.ok(details.columns.some(c => c.name === 'id'))
        await api('query', { connectionId: id, sql: 'BEGIN' })
        await api('query', { connectionId: id, sql: "INSERT INTO e2e_data VALUES(2,'rollback')" })
        await api('query', { connectionId: id, sql: 'ROLLBACK' })
        const [count] = await api('query', { connectionId: id, sql: 'SELECT COUNT(*) AS n FROM e2e_data' })
        assert.equal(Number(count.rows[0][0]), 1)
        await api('disconnect', id)
        await api('deleteConnection', id)
        const state = await readFile(resolve(dataDir, 'sqlkiwi-state.json'), 'utf8')
        assert.ok(!state.includes('local-test-only'))
      })
      await step(`${engine} cancellation interrupts server query`, async () => {
        const id = `e2e-cancel-${engine}`
        await api('saveConnection', { id, name: `${engine} cancel`, engine, host: '127.0.0.1',
          port: engine === 'postgres' ? 55433 : 53307, username: engine === 'postgres' ? 'sqlkiwi' : 'root',
          password: 'local-test-only', database: 'sqlkiwi' })
        await api('connect', id)
        await page.evaluate(({ id, sql }) => {
          window.__remotePending = window.sqlkiwi.query({ connectionId: id, sql })
            .then(value => ({ value }), error => ({ error: String(error) }))
        }, { id, sql: engine === 'postgres' ? 'SELECT pg_sleep(20)' : 'SELECT SLEEP(20)' })
        await new Promise(resolve => setTimeout(resolve, 200))
        const start = Date.now()
        await api('cancel', id)
        const pending = await page.evaluate(() => window.__remotePending)
        assert.ok(pending.error || pending.value?.some(item => item.error))
        assert.ok(Date.now() - start < 5_000, 'cancel completes promptly')
        await api('connect', id)
        const [result] = await api('query', { connectionId: id, sql: 'SELECT 9' })
        assert.equal(Number(result.rows[0][0]), 9)
        await api('deleteConnection', id)
      })
    }
  }
  await step('query tabs and Ctrl+Enter execute through the UI', async () => {
    await page.getByRole('button', { name: '새 쿼리 탭', exact: true }).click()
    const editor = page.locator('.cm-content')
    await editor.click()
    await page.keyboard.press('Control+A')
    await page.keyboard.type("SELECT 'UI works' AS message, 42 AS answer;")
    await page.keyboard.press('Control+Enter')
    await page.getByRole('cell', { name: 'UI works', exact: true }).waitFor()
    await page.getByRole('textbox', { name: '결과 검색' }).fill('no-match')
    await page.getByText('조건에 맞는 행이 없습니다.', { exact: true }).waitFor()
    await page.getByRole('textbox', { name: '결과 검색' }).fill('')
    await page.screenshot({ path: resolve(output, 'query-result.png') })
  })
  await step('SQL save, open and CSV export write actual local files', async () => {
    const savedSql = resolve(output, 'saved-query.sql')
    const savedCsv = resolve(output, 'exported-results.csv')
    const openedSql = resolve(output, 'opened-query.sql')
    await writeFile(openedSql, "SELECT 'UI works from file' AS message, 77 AS answer;", 'utf8')
    // Keep native file selection deterministic; application file I/O and IPC run unchanged.
    await app.evaluate(({ dialog }, { savedSql, savedCsv, openedSql }) => {
      dialog.showSaveDialog = async (...args) => {
        const options = args[args.length - 1]
        return { canceled: false, filePath: options.filters?.[0]?.extensions?.[0] === 'csv' ? savedCsv : savedSql }
      }
      dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [openedSql] })
    }, { savedSql, savedCsv, openedSql })
    await page.getByRole('button', { name: '저장', exact: true }).click()
    await page.getByText('SQL 파일을 저장했습니다.', { exact: true }).waitFor()
    assert.match(await readFile(savedSql, 'utf8'), /UI works/)
    await page.getByTitle('CSV로 내보내기', { exact: true }).click()
    await page.getByText('CSV 파일을 저장했습니다.', { exact: true }).waitFor()
    assert.match(await readFile(savedCsv, 'utf8'), /message,answer\r\nUI works,42/)
    await page.getByRole('button', { name: '열기', exact: true }).click()
    await page.locator('.cm-content').filter({ hasText: 'UI works from file' }).waitFor()
    await page.locator('.cm-content').click()
    await page.keyboard.press('Control+Enter')
    await page.getByRole('cell', { name: 'UI works from file', exact: true }).waitFor()
  })
  await step('connection dialog tests and saves a real read-only SQLite connection', async () => {
    await page.getByRole('button', { name: '새 연결', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByLabel('연결 이름', { exact: true }).fill('UI readonly')
    await dialog.getByLabel(/^데이터베이스 파일/).fill(boot.connections.find(c => c.id === demo).filename)
    await dialog.getByLabel('읽기 전용으로 연결', { exact: true }).check()
    await dialog.getByRole('button', { name: '연결 테스트', exact: true }).click()
    await dialog.getByRole('status').filter({ hasText: '연결 성공' }).waitFor()
    await page.screenshot({ path: resolve(output, 'connection-dialog.png') })
    await dialog.getByRole('button', { name: '저장', exact: true }).click()
    await dialog.waitFor({ state: 'hidden' })
    const connection = (await api('bootstrap')).connections.find(c => c.name === 'UI readonly')
    assert.ok(connection?.readOnly)
    await page.getByRole('combobox', { name: '현재 연결' }).selectOption(connection.id)
    await page.locator('.cm-content').click()
    await page.keyboard.press('Control+Enter')
    await page.getByRole('cell', { name: 'UI works from file', exact: true }).waitFor()
    await page.getByRole('combobox', { name: '현재 연결' }).selectOption(demo)
  })
  await step('workspace persists SQL tabs after restart', async () => {
    await new Promise(resolve => setTimeout(resolve, 750))
    const workspace = (await api('bootstrap')).workspace
    assert.ok(workspace.tabs.some(tab => tab.sql.includes('UI works')))
    assert.ok((await api('history')).length > 0)
    await app.close()
    app = await electron.launch(launchOptions)
    page = await app.firstWindow()
    page.on('pageerror', error => errors.push(error.message))
    await page.locator('.cm-content').waitFor()
    assert.match(await page.locator('.cm-content').innerText(), /UI works/)
    await page.getByRole('button', { name: '라이트 모드' }).click()
    await page.screenshot({ path: resolve(output, 'workbench-light.png') })
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(1120, 780))
    await new Promise(resolve => setTimeout(resolve, 150))
    await page.getByTitle('현재 문장 또는 선택 영역 실행 (Ctrl+Enter)', { exact: true }).waitFor()
    await page.screenshot({ path: resolve(output, 'compact-layout.png') })
  })
  assert.deepEqual(errors, [], 'renderer must not throw unhandled errors')
  console.log(`E2E passed: ${checks.length}; artifacts: ${output}`)
} catch (error) {
  if (page) await page.screenshot({ path: resolve(output, 'failure.png') }).catch(() => {})
  console.error(error)
  process.exitCode = 1
} finally {
  await writeFile(resolve(output, 'report.json'), JSON.stringify({ checks, errors, passed: !process.exitCode }, null, 2))
  await app.close()
}

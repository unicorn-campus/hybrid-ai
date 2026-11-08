// sqlkiwi 화면 시험: 실제 Electron 앱을 띄워 연결 만들기, 탐색, 실행, 더 가져오기, 정렬, 취소를 해 보고 화면을 찍음
// 준비: npm run build, 시험 DB(test-db/compose.yml) 기동
// 실행: node test/e2e.mjs [스크린샷 폴더]
import { _electron as electron } from 'playwright-core'
import { mkdtempSync, mkdirSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import assert from 'node:assert/strict'

const root = resolve(import.meta.dirname, '..')
const shots = resolve(process.argv[2] ?? join(root, 'test-results'))
mkdirSync(shots, { recursive: true })
const work = mkdtempSync(join(tmpdir(), 'sqlkiwi-e2e-'))
const dbFile = join(work, 'sample.db')

const app = await electron.launch({
  executablePath: join(root, 'node_modules', 'electron', 'dist', 'electron.exe'),
  args: [root],
  env: { ...process.env, SQLKIWI_USER_DATA: join(work, 'userdata') }
})
const page = await app.firstWindow()
await page.setViewportSize?.({ width: 1400, height: 900 })
const shot = (name) => page.screenshot({ path: join(shots, `${name}.png`) })
const log = (m) => console.log(`✓ ${m}`)

async function editorInsert(text) {
  const ed = page.locator('.editor-wrap:visible .cm-content')
  await ed.click()
  await page.keyboard.press('Control+A')
  await page.keyboard.press('Delete')
  await page.keyboard.insertText(text)
}

/** 연결 하나의 트리(연결 행과 그 아래 노드) */
const connTree = (name) => page.locator('ul.tree > li').filter({ has: page.locator('.tree-row.conn', { hasText: name }) })

async function newConnection(kind, fields) {
  await page.getByRole('button', { name: '+ 새 연결' }).click()
  await page.getByRole('radio', { name: new RegExp(kind) }).click()
  for (const [label, value] of Object.entries(fields)) {
    const input = label === 'DB 파일' ? page.getByPlaceholder('파일 경로') : page.getByLabel(label, { exact: true })
    await input.fill(String(value))
  }
}

try {
  await page.waitForSelector('.welcome')
  await shot('01-welcome')
  log('첫 화면')

  // ---- SQLite: 새 파일로 연결 만들기 ----
  await newConnection('SQLite', { 이름: 'sample', 'DB 파일': dbFile })
  await page.getByRole('button', { name: '저장' }).click()
  await page.locator('.tree-row.conn', { hasText: 'sample' }).click()
  await page.waitForSelector('.tree-row.conn .dot.on')
  log('SQLite 연결')

  await page.locator('.tree-row.conn', { hasText: 'sample' }).hover()
  await page.getByTitle('SQL 편집기 열기').first().click()
  await editorInsert(
    [
      '-- 시험 데이터',
      'create table customers (id integer primary key, name text not null);',
      'create table orders (id integer primary key, customer_id integer references customers(id), amount real, memo text);',
      "insert into customers(name) values ('고객1'), ('고객2');",
      'insert into orders(customer_id, amount, memo)',
      '  with recursive g(n) as (select 1 union all select n + 1 from g where n < 450)',
      "  select n % 2 + 1, n * 10.5, case when n % 7 = 0 then null else '주문 ' || n end from g;",
      '',
      'select * from orders'
    ].join('\n')
  )
  await page.keyboard.press('Alt+X')
  await page.waitForSelector('.result-tab:has-text("통계")')
  await page.getByRole('button', { name: '통계' }).click()
  const statRows = await page.locator('table.stats tbody tr').count()
  assert.equal(statRows, 5)
  await shot('02-sqlite-script-stats')
  log('스크립트 실행(5문장) 통계')

  // 마지막 줄(select)에 커서를 두고 Ctrl+Enter
  await page.locator('.editor-wrap:visible .cm-content').click()
  await page.keyboard.press('Control+End')
  await page.keyboard.press('Control+Enter')
  await page.waitForSelector('.statusbar:has-text("200+행")')
  await shot('03-sqlite-first-200')
  log('Ctrl+Enter: 처음 200행과 200+ 표시')

  // 스크롤을 끝까지 내려 자동으로 더 가져오기
  for (let i = 0; i < 6; i++) {
    await page.locator('.grid').evaluate((el) => (el.scrollTop = el.scrollHeight))
    await page.waitForTimeout(300)
  }
  await page.waitForSelector('.statusbar:has-text("450행")')
  await shot('04-sqlite-autofetch-450')
  log('스크롤 끝에서 자동 더 가져오기, 450행')

  // 정렬(모두 받은 상태라 메모리 정렬)
  await page.locator('.cell.head', { hasText: 'amount' }).click()
  await page.locator('.cell.head', { hasText: 'amount' }).click()
  const firstAmount = await page.locator('.grid-row').first().locator('.cell').nth(3).textContent()
  assert.equal(firstAmount, '4725')
  log('머리글 두 번 눌러 내림차순 정렬')

  // NULL 표시
  assert.ok(await page.locator('.cell.null', { hasText: '[NULL]' }).count())
  log('NULL을 [NULL]로 표시')

  // 탐색 트리
  await page.locator('.tree-row', { hasText: '테이블' }).first().click()
  await page.locator('.tree-row', { hasText: 'orders' }).first().click()
  await page.locator('.tree-row', { hasText: '외래 키' }).first().click()
  await page.waitForSelector('.tree-row:has-text("REFERENCES customers(id)")')
  await page.locator('.tree-row', { hasText: '컬럼' }).first().click()
  await shot('05-sqlite-tree')
  log('탐색 트리: 테이블 > 컬럼, 외래 키')

  // SQLite 실행 취소(작업 스레드 종료) 뒤에도 다시 실행 가능
  await editorInsert('with recursive c(x) as (select 1 union all select x + 1 from c) select count(*) from c')
  await page.keyboard.press('Control+Enter')
  await page.waitForTimeout(800)
  await page.getByRole('button', { name: '■ 취소' }).click()
  await page.waitForSelector('.message.err:has-text("취소")', { timeout: 10000 })
  await editorInsert('select count(*) as n from orders')
  await page.keyboard.press('Control+Enter')
  await page.waitForSelector('.grid-row .cell:has-text("450")')
  log('SQLite 무한 질의 취소 뒤 다시 실행')

  // 오류 문장
  await editorInsert('select * from no_such_table')
  await page.keyboard.press('Control+Enter')
  await page.waitForSelector('.message.err')
  log('오류 메시지 표시')

  // ---- PostgreSQL ----
  await newConnection('PostgreSQL', { 이름: 'pg-test', 호스트: '127.0.0.1', 포트: 55432, 데이터베이스: 'kiwi', 사용자: 'kiwi', 비밀번호: 'kiwi' })
  await page.getByRole('button', { name: '연결 시험' }).click()
  await page.waitForSelector('.msg.ok')
  await shot('06-pg-connection-dialog')
  log(`PostgreSQL 연결 시험: ${await page.locator('.msg.ok').textContent()}`)
  await page.getByRole('button', { name: '저장' }).click()
  await page.locator('.tree-row.conn', { hasText: 'pg-test' }).click()
  const pgTree = connTree('pg-test')
  await pgTree.locator('.tree-row', { hasText: 'shop' }).click()
  await pgTree.locator('.tree-row', { hasText: '테이블' }).first().click()
  await pgTree.locator('.tree-row', { hasText: 'orders' }).first().dblclick()
  await page.waitForSelector('.statusbar:has-text("200+행")')
  log('테이블 두 번 눌러 SELECT 실행(200+행)')

  // 남은 행이 있으니 서버 정렬
  await page.locator('.cell.head', { hasText: 'id' }).first().click()
  await page.waitForSelector('.statusbar:has-text("오름차순 (서버)")')
  await page.locator('.cell.head', { hasText: 'id' }).first().click()
  await page.waitForSelector('.statusbar:has-text("내림차순 (서버)")')
  const topId = await page.locator('.grid-row').first().locator('.cell').nth(1).textContent()
  assert.equal(topId, '500')
  await shot('07-pg-server-sort')
  log('남은 행이 있을 때 서버 ORDER BY 정렬(내림차순 첫 행 id=500)')

  // 자동완성
  await editorInsert('select * from shop.ord')
  await page.keyboard.press('Control+Space')
  await page.waitForSelector('.cm-tooltip-autocomplete')
  await shot('08-pg-autocomplete')
  log('자동완성 목록 표시')
  await page.keyboard.press('Escape')

  // 취소
  await editorInsert('select pg_sleep(30)')
  await page.keyboard.press('Control+Enter')
  await page.waitForTimeout(800)
  await page.getByRole('button', { name: '■ 취소' }).click()
  await page.waitForSelector('.message.err:has-text("cancel")', { timeout: 10000 })
  log('실행 취소')

  // 위험 문장 확인 대화상자: 취소를 고르면 실행하지 않음
  page.once('dialog', (d) => d.dismiss())
  await editorInsert('delete from shop.orders')
  await page.keyboard.press('Control+Enter')
  await page.waitForTimeout(500)
  log('WHERE 없는 DELETE는 확인 후 실행(취소함)')

  // ---- MySQL ----
  await newConnection('MySQL', { 이름: 'my-test', 호스트: '127.0.0.1', 포트: 53306, 데이터베이스: 'kiwi', 사용자: 'kiwi', 비밀번호: 'kiwi' })
  await page.getByRole('button', { name: '저장' }).click()
  await page.locator('.tree-row.conn', { hasText: 'my-test' }).click()
  const my = connTree('my-test') // 다른 연결의 같은 이름 노드를 누르지 않게 이 연결 아래로 한정
  await my.locator('.tree-row', { hasText: 'kiwi' }).first().click()
  await my.locator('.tree-row', { hasText: '뷰' }).first().click()
  await my.locator('.tree-row', { hasText: 'customer_totals' }).dblclick()
  await page.waitForSelector('.statusbar:has-text("30행")')
  assert.ok(await page.locator('.cell', { hasText: '고객1' }).count(), '한글 값 표시')
  assert.ok(await page.locator('.col-type', { hasText: 'newdecimal' }).count(), 'MySQL 자료형 이름')
  await shot('09-mysql-view')
  log('MySQL 뷰 열기(30행, 한글과 자료형 표시)')

  // ---- 비밀번호를 저장하지 않은 읽기 전용 연결: 연결할 때 묻고, 쓰기 문장은 앱이 막음 ----
  await newConnection('PostgreSQL', { 이름: 'pg-ro', 호스트: '127.0.0.1', 포트: 55432, 데이터베이스: 'kiwi', 사용자: 'kiwi', 비밀번호: 'kiwi' })
  await page.getByLabel(/비밀번호 저장/).uncheck()
  await page.getByLabel(/읽기 전용 연결/).check()
  await page.getByRole('button', { name: '저장' }).click()
  await page.locator('.tree-row.conn', { hasText: 'pg-ro' }).click()
  await page.waitForSelector('h2:has-text("비밀번호 입력")')
  await shot('10-password-prompt')
  await page.locator('.modal input[type=password]').fill('kiwi')
  await page.getByRole('button', { name: '연결', exact: true }).click()
  await page.waitForSelector('.tree-row.conn:has-text("pg-ro") .dot.on')
  log('비밀번호를 저장하지 않은 연결은 연결할 때 물어봄')
  await page.locator('.tree-row.conn', { hasText: 'pg-ro' }).hover()
  await page.locator('.tree-row.conn', { hasText: 'pg-ro' }).getByTitle('SQL 편집기 열기').click()
  await editorInsert("insert into shop.customers(name) values ('x')")
  await page.keyboard.press('Control+Enter')
  await page.waitForSelector('.message.err:has-text("읽기 전용")')
  await shot('11-readonly-block')
  log('읽기 전용 연결에서 INSERT 차단')

  console.log(`\n모두 통과. 화면: ${shots}`)
} catch (e) {
  await shot('zz-failure').catch(() => undefined)
  console.error('실패:', e)
  process.exitCode = 1
} finally {
  await app.close()
  rmSync(work, { recursive: true, force: true })
}

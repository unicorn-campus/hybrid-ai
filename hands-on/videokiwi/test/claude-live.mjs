// Explicit live Claude subscription test. Video submission is intercepted; this test does not use the GPU.
import assert from 'node:assert/strict'
import { chromium } from 'playwright-core'
import { existsSync } from 'node:fs'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const base = process.env.VIDEOKIWI_URL || 'http://127.0.0.1:3010'
const output = resolve('test-results', `claude-live-${Date.now()}`)
await mkdir(output, { recursive: true })
const executablePath = [process.env.BROWSER_EXECUTABLE, 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/chromium'].filter(Boolean).find(existsSync)
if (!executablePath) throw new Error('BROWSER_EXECUTABLE을 지정해 주세요.')
const browser = await chromium.launch({ executablePath, headless: true, args: ['--disable-gpu'] })
const record = { verified: false, gpuSubmitted: false, errors: [] }
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  page.setDefaultTimeout(15_000)
  page.on('pageerror', error => record.errors.push(error.message))
  await page.goto(base)
  const initial = await page.request.get(base + '/api/jobs').then(response => response.json())
  const example = initial.find(job => (job.input.originalPrompt || job.input.prompt).includes('하인샤'))
  if (example) {
    await page.getByRole('button', { name: '라이브러리', exact: true }).click()
    await page.locator('.library-card').filter({ hasText: '하인샤' }).first().click()
    await page.getByRole('button', { name: '설정 불러오기', exact: true }).click()
  } else {
    await page.getByRole('button', { name: '텍스트에서', exact: true }).click()
    await page.getByLabel('어떻게 움직일까요?').fill('하인샤 대사원에서 멀어지며 하늘로 올라간다. 웅장한 음악과 한글 자막을 보여준다.')
  }
  const original = await page.getByLabel('어떻게 움직일까요?').inputValue()
  const pending = page.waitForResponse(response => response.url() === base + '/api/prompt/optimize', { timeout: 150_000 })
  await page.getByRole('button', { name: /프롬프트 제안/ }).click()
  const response = await pending
  const result = await response.json()
  record.suggestion = result
  assert.equal(response.status(), 200, JSON.stringify(result))
  assert.equal(result.method, 'claude-agent-sdk')
  assert.equal(result.authentication, 'claude-subscription')
  assert.equal(result.model, 'claude-opus-5-5')
  const review = page.getByRole('textbox', { name: '다듬은 프롬프트', exact: true })
  await review.waitFor()
  assert.equal(await review.inputValue(), result.optimized)
  assert.equal(await page.getByLabel('어떻게 움직일까요?').inputValue(), original)
  assert.match(result.optimized, /integrated_multimodal_description:/)
  assert.match(result.optimized, /overall_soundscape:/)
  assert.match(result.optimized, /non_diegetic_music:/)
  assert.match(result.optimized, /no (?:speech|narration)/i)
  const edited = result.optimized + '\n\nKeep the requested camera motion continuous.'
  await review.fill(edited)
  let submitted
  await page.route('**/api/jobs', async route => {
    if (route.request().method() !== 'POST') { await route.continue(); return }
    submitted = route.request().postDataJSON()
    await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ error: '검증용 제출 차단: GPU에 전송하지 않았습니다.' }) })
  })
  await page.getByRole('button', { name: '영상 만들기', exact: true }).click()
  await page.getByText('검증용 제출 차단: GPU에 전송하지 않았습니다.', { exact: true }).waitFor()
  assert.equal(submitted.prompt, edited)
  assert.equal(submitted.originalPrompt, original)
  assert.equal(submitted.optimize, false)
  const final = await page.request.get(base + '/api/jobs').then(response => response.json())
  assert.equal(final.length, initial.length)
  assert.deepEqual(record.errors, [])
  record.verified = true
  record.checked = ['actual subscription SDK response', 'start/end images when available', 'separate scene/audio/music',
    'original text preserved', 'review edits used without copy/paste', 'no video job created']
  await page.screenshot({ path: resolve(output, 'claude-suggestion.png'), fullPage: true })
  console.log(JSON.stringify({ output, verified: true, model: result.model, method: result.method, gpuSubmitted: false }))
} catch (error) {
  record.error = error.stack
  throw error
} finally {
  await writeFile(resolve(output, 'verification.json'), JSON.stringify(record, null, 2))
  await browser.close()
}

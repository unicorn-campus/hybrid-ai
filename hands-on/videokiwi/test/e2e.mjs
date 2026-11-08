import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { mkdir, writeFile, readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { spawn } from 'node:child_process'
import { createServer } from 'node:net'
import { chromium } from 'playwright-core'
import sharp from 'sharp'
import { startMockComfy } from './mock-comfy.mjs'

const output = resolve('test-results', `web-${Date.now()}`)
await mkdir(output, { recursive: true })
const fixture = await startMockComfy(output)
const port = await new Promise(resolvePort => {
  const socket = createServer().listen(0, '127.0.0.1', () => {
    const number = socket.address().port
    socket.close(() => resolvePort(number))
  })
})
const url = `http://127.0.0.1:${port}`
const env = { ...process.env, NODE_ENV: 'test', VIDEOKIWI_TEST_MODE: '1', PORT: String(port), HOST: '127.0.0.1',
  COMFYUI_URL: fixture.url, VIDEOKIWI_DATA_DIR: resolve(output, 'data'), VIDEOKIWI_ACCESS_TOKEN: '' }
const server = spawn(process.execPath, ['dist/server/index.js'], { env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] })
let serverLog = ''
server.stdout.on('data', value => { serverLog += value })
server.stderr.on('data', value => { serverLog += value })
const checks = [], pageErrors = []
const step = async (name, fn) => { await fn(); checks.push(name); console.log(`PASS ${name}`) }
let browser
try {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (server.exitCode !== null) throw new Error(serverLog)
    const ready = await fetch(`${url}/api/health`).then(response => response.ok).catch(() => false)
    if (ready) break
    if (attempt === 99) throw new Error(`Server startup timeout: ${serverLog}`)
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  const paths = [process.env.BROWSER_EXECUTABLE,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/usr/bin/chromium', '/usr/bin/google-chrome'].filter(Boolean)
  const executablePath = paths.find(path => existsSync(path))
  if (!executablePath) throw new Error('BROWSER_EXECUTABLE에 설치된 Chromium 브라우저 경로를 지정해 주세요.')
  browser = await chromium.launch({ executablePath, headless: true, args: ['--disable-gpu'] })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true })
  page.on('pageerror', error => pageErrors.push(error.message))
  await step('local web studio loads with an empty workspace', async () => {
    await page.goto(url)
    await page.getByRole('heading', { name: /첫 장면/ }).waitFor()
    assert.equal(await page.title(), 'VideoKiwi')
    assert.equal((await page.request.get(`${url}/api/bootstrap`).then(response => response.json())).settings.engine.modelReady, true)
    await page.screenshot({ path: resolve(output, 'studio-empty.png'), fullPage: true })
  })
  await step('image upload and editable local prompt optimization', async () => {
    const image = await sharp({ create: { width: 640, height: 352, channels: 3, background: '#7f9940' } }).png().toBuffer()
    const imagePath = resolve(output, 'input.png')
    await writeFile(imagePath, image)
    await page.locator('input[type=file]').first().setInputFiles(imagePath)
    await page.getByAltText(/시작 장면:/).waitFor()
    const original = 'A small cat slowly turns its head toward the window in natural morning light.'
    await page.getByLabel('어떻게 움직일까요?').fill(original)
    await page.getByRole('button', { name: /프롬프트 제안/ }).click()
    const optimized = page.getByRole('textbox', { name: '다듬은 프롬프트', exact: true })
    await optimized.waitFor()
    assert.ok((await optimized.inputValue()).includes(original))
    await optimized.fill(`${await optimized.inputValue()}\n\nKeep the final framing unchanged.`)
  })
  let createdId
  await step('reviewed image prompt reaches the H3 workflow and receives a playable test result', async () => {
    const response = page.waitForResponse(response => response.url() === `${url}/api/jobs` && response.request().method() === 'POST')
    await page.getByRole('button', { name: '영상 만들기', exact: true }).click()
    const createdResponse = await response
    assert.equal(createdResponse.status(), 202)
    const created = await createdResponse.json()
    createdId = created.id
    const progressBar = page.getByRole('progressbar').first()
    await progressBar.waitFor({ timeout: 10_000 })
    const measuredProgress = Number(await progressBar.getAttribute('aria-valuenow'))
    assert.ok(measuredProgress > 0 && measuredProgress <= 100)
    assert.match(await page.locator('.live-progress').innerText(), /샘플링|복원/)
    await page.screenshot({ path: resolve(output, 'studio-progress.png'), fullPage: true })
    await page.locator('.preview-stage video').waitFor({ timeout: 20_000 })
    const actual = (await page.request.get(`${url}/api/jobs`).then(response => response.json())).find(job => job.id === createdId)
    assert.equal(actual.status, 'completed')
    assert.ok(actual.input.prompt.includes('Keep the final framing unchanged.'))
    assert.equal(fixture.submissions.length, 1)
    assert.equal(fixture.submissions[0].prompt['5'].inputs.prompt, actual.input.prompt)
    assert.ok(fixture.submissions[0].prompt['5'].inputs.first_frame)
    await page.locator('.preview-stage video').evaluate(video => video.play())
    assert.equal(await page.locator('.preview-stage video').evaluate(video => video.videoWidth), 640)
    await page.screenshot({ path: resolve(output, 'studio-result.png'), fullPage: true })
  })
  await step('video download streams the engine file and recipe preserves original input', async () => {
    const recipeResponse = await page.request.get(`${url}/api/jobs/${createdId}/recipe`)
    assert.ok(recipeResponse.headers()['content-disposition'].includes('attachment'))
    const recipe = await recipeResponse.json()
    assert.ok(recipe.input.originalPrompt.includes('A small cat'))
    const partial = await page.request.get(`${url}/api/jobs/${createdId}/video`, { headers: { Range: 'bytes=0-127' } })
    assert.equal(partial.status(), 206)
    assert.equal((await partial.body()).length, 128)
    const download = page.waitForEvent('download')
    await page.getByRole('button', { name: /영상.*(?:저장|다운로드)|다운로드/ }).first().click()
    const file = await download
    await file.saveAs(resolve(output, file.suggestedFilename()))
    assert.ok((await readFile(resolve(output, file.suggestedFilename()))).length > 128)
  })
  await step('reusing a job preserves the reviewed final prompt and a new workspace stays selected', async () => {
    await page.getByRole('button', { name: '설정 불러오기', exact: true }).click()
    const restored = page.getByRole('textbox', { name: '다듬은 프롬프트', exact: true })
    assert.ok((await restored.inputValue()).includes('Keep the final framing unchanged.'))
    await page.getByRole('heading', { name: /첫 장면/ }).waitFor()
    const textResponse = await page.request.post(`${url}/api/jobs`, { data: { mode: 'text',
      prompt: 'A tree sways gently in the wind.', duration: 5, resolution: 'preview', aspectRatio: '16:9',
      camera: 'none', profile: 'fast', seed: 42, optimize: true } })
    assert.equal(textResponse.status(), 202)
    const textJob = await textResponse.json()
    for (let n = 0; n < 50; n++) {
      const jobs = await page.request.get(`${url}/api/jobs`).then(response => response.json())
      if (jobs.find(job => job.id === textJob.id)?.status === 'completed') break
      if (n === 49) throw new Error('Text-only mock job did not complete')
      await page.waitForTimeout(200)
    }
    assert.equal(fixture.submissions.length, 2)
    assert.equal(fixture.submissions[1].prompt['5'].inputs.first_frame, undefined)
    assert.equal(fixture.submissions[1].prompt['9'].inputs.steps, 8)
    assert.ok(await page.getByRole('heading', { name: /첫 장면/ }).isVisible())
  })
  await step('library search, engine panel and mobile viewport remain usable', async () => {
    await page.getByRole('button', { name: '라이브러리', exact: true }).click()
    await page.getByPlaceholder('프롬프트 검색').fill('no-matching-scene')
    await page.getByText('조건에 맞는 작업이 없습니다.').waitFor()
    await page.getByPlaceholder('프롬프트 검색').fill('small cat')
    assert.equal(await page.locator('.library-card').count(), 1)
    await page.getByRole('button', { name: '엔진', exact: true }).click()
    await page.getByText('TEST FIXTURE GPU (no inference)', { exact: true }).waitFor()
    await page.getByRole('button', { name: '새 영상', exact: true }).click()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.screenshot({ path: resolve(output, 'studio-mobile.png'), fullPage: true })
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2))
  })
  await step('an unrelated engine job blocks submission without consuming GPU', async () => {
    fixture.setBusy(true)
    const response = await page.request.post(`${url}/api/jobs`, { data: { mode: 'text', prompt: 'A tree sways gently in the wind.',
      duration: 5, resolution: 'preview', aspectRatio: '16:9', camera: 'none', profile: 'balanced', seed: 42, optimize: true } })
    assert.equal(response.status(), 409)
    assert.equal(fixture.submissions.length, 2)
  })
  assert.deepEqual(pageErrors, [])
  await writeFile(resolve(output, 'verification.json'), JSON.stringify({ checks, pageErrors,
    engine: 'mock only; no H3 inference; GPU tests deferred at user request', browser: await browser.version() }, null, 2))
  console.log(`Evidence: ${output}`)
} catch (error) {
  await writeFile(resolve(output, 'failure.txt'), `${error.stack}\n${serverLog}`)
  throw error
} finally {
  await browser?.close()
  server.kill()
  await fixture.close()
}

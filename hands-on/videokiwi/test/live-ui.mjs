// Read-only verification against a running VideoKiwi server. Does not submit generation jobs.
import assert from 'node:assert/strict'
import { chromium } from 'playwright-core'
import { existsSync } from 'node:fs'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const base = process.env.VIDEOKIWI_URL || 'http://127.0.0.1:3010'
const output = resolve('test-results', `live-ui-${Date.now()}`)
await mkdir(output, { recursive: true })
const executablePath = [process.env.BROWSER_EXECUTABLE, 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/chromium'].filter(Boolean).find(existsSync)
if (!executablePath) throw new Error('BROWSER_EXECUTABLE을 지정해 주세요.')
const browser = await chromium.launch({ executablePath, headless: true, args: ['--disable-gpu'] })
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(base)
  const jobs = await page.request.get(base + '/api/jobs').then(response => response.json())
  const completed = jobs.find(job => job.status === 'completed')
  assert.ok(completed, '실제 완료된 영상이 있어야 합니다.')
  await page.getByRole('button', { name: '라이브러리', exact: true }).click()
  await page.locator('.library-card').filter({ hasText: completed.input.originalPrompt || completed.input.prompt }).first().click()
  await page.locator('.preview-stage video').waitFor({ timeout: 30_000 })
  const playback = await page.locator('.preview-stage video').evaluate(async video => {
    video.muted = true
    await video.play()
    await new Promise(resolve => setTimeout(resolve, 800))
    const result = { width: video.videoWidth, height: video.videoHeight, duration: video.duration,
      currentTime: video.currentTime, readyState: video.readyState }
    video.pause()
    return result
  })
  assert.ok(playback.width > 0 && playback.currentTime > 0)
  const bounds = await page.locator('.preview-stage').boundingBox()
  assert.ok(bounds && bounds.x + bounds.width <= 1440, '미리보기가 화면 오른쪽을 넘지 않아야 합니다.')
  assert.deepEqual(errors, [])
  await page.screenshot({ path: resolve(output, 'actual-h3-result.png'), fullPage: true })
  await page.getByRole('button', { name: '설정 불러오기', exact: true }).click()
  const thumbnails = page.locator('.asset-slot img')
  for (let index = 0; index < await thumbnails.count(); index++) {
    await thumbnails.nth(index).evaluate(async img => {
      if (!img.complete) await new Promise((resolve, reject) => { img.onload = resolve; img.onerror = reject })
      if (img.naturalWidth === 0) throw new Error('입력 이미지 미리보기 실패')
    })
  }
  const imagePreviews = await thumbnails.count()
  await writeFile(resolve(output, 'verification.json'), JSON.stringify({ playback, imagePreviews, errors, base }, null, 2))
  console.log(JSON.stringify({ output, playback, imagePreviews, errors }))
} finally { await browser.close() }

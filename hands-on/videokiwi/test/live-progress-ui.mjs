// Read-only UI observer for an already submitted real H3 job. Never submits or cancels jobs.
import assert from 'node:assert/strict'
import { chromium } from 'playwright-core'
import { existsSync } from 'node:fs'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const base = process.env.VIDEOKIWI_URL || 'http://127.0.0.1:3010'
const output = resolve('test-results', `live-progress-${Date.now()}`)
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
  const bar = page.getByRole('progressbar').first()
  await bar.waitFor({ timeout: 180_000 })
  const first = Number(await bar.getAttribute('aria-valuenow'))
  assert.ok(first >= 0 && first <= 100)
  const label = await page.locator('.live-progress').innerText()
  await page.screenshot({ path: resolve(output, 'sampling-progress.png'), fullPage: true })
  await page.waitForFunction(previous => {
    const el = document.querySelector('[role="progressbar"]')
    return el && Number(el.getAttribute('aria-valuenow')) > previous
  }, first, { timeout: 120_000 })
  const next = Number(await bar.getAttribute('aria-valuenow'))
  assert.ok(next > first)
  assert.deepEqual(errors, [])
  const evidence = { first, next, label, errors, gpuSubmitted: false, base }
  await writeFile(resolve(output, 'verification.json'), JSON.stringify(evidence, null, 2))
  console.log(JSON.stringify({ output, ...evidence }))
} finally { await browser.close() }

import 'dotenv/config'
import { resolve, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { readFile, writeFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import express from 'express'
import { ComfyClient } from './comfy.js'
import { Store } from './store.js'
import { VideoService } from './service.js'
import { createApp } from './app.js'
import { lockDataDirectory } from './lock.js'
import { ClaudePromptAdvisor } from './claude-advisor.js'

const root = fileURLToPath(new URL('../../', import.meta.url))
const port = Number(process.env.PORT || 3010)
const host = process.env.HOST || '127.0.0.1'
const accessToken = process.env.VIDEOKIWI_ACCESS_TOKEN || ''
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('PORT는 1부터 65535 사이의 정수여야 합니다.')
if (!['127.0.0.1', 'localhost', '::1'].includes(host) && accessToken.length < 16) {
  throw new Error('다른 기기에 공개하려면 VIDEOKIWI_ACCESS_TOKEN에 16자 이상의 접속 비밀번호를 지정해 주세요.')
}
const data = resolve(process.env.VIDEOKIWI_DATA_DIR || join(root, '.data'))
const unlock = await lockDataDirectory(data)
const clientIdPath = join(data, 'comfy-client-id')
let comfyClientId: string
try { comfyClientId = (await readFile(clientIdPath, 'utf8')).trim() }
catch (error) {
  if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
  comfyClientId = randomUUID()
  await writeFile(clientIdPath, comfyClientId, { mode: 0o600, flag: 'wx' })
}
if (!/^[0-9a-f-]{36}$/i.test(comfyClientId)) throw new Error('저장된 ComfyUI 클라이언트 ID를 확인해 주세요.')
const fixtureMode = process.env.NODE_ENV === 'test' && process.env.VIDEOKIWI_TEST_MODE === '1'
const advisor = fixtureMode ? undefined : new ClaudePromptAdvisor({ workspace: join(data, 'claude-workspace'),
  model: process.env.VIDEOKIWI_CLAUDE_MODEL, executablePath: process.env.VIDEOKIWI_CLAUDE_PATH })
const service = new VideoService(new Store(data), new ComfyClient({ baseUrl: process.env.COMFYUI_URL || 'http://127.0.0.1:8188', clientId: comfyClientId }), advisor)
await service.open()
const app = createApp(service, accessToken)
if (process.env.NODE_ENV !== 'production' && import.meta.url.includes('/src/')) {
  const { createServer } = await import('vite')
  const vite = await createServer({ configFile: join(root, 'vite.config.ts'), server: { middlewareMode: true }, appType: 'spa' })
  app.use(vite.middlewares)
} else {
  app.use(express.static(join(root, 'dist/client')))
  app.get('/{*path}', (_req, res) => { res.sendFile(join(root, 'dist/client/index.html')) })
}
const server = app.listen(port, host, () => console.log(`VideoKiwi: http://${host}:${port}\nMiniMax H3 엔진: ${process.env.COMFYUI_URL || 'http://127.0.0.1:8188'}`))
server.on('error', error => {
  console.error(error.message); service.close()
  void unlock().finally(() => { process.exitCode = 1 })
})
for (const signal of ['SIGINT', 'SIGTERM'] as const) process.on(signal, () => {
  service.close()
  server.close(() => { void unlock().finally(() => process.exit(0)) })
  setTimeout(() => process.exit(0), 3000).unref()
})

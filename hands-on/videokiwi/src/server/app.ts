import express, { type Request, type Response, type NextFunction } from 'express'
import multer from 'multer'
import { Readable } from 'node:stream'
import { timingSafeEqual } from 'node:crypto'
import { isIP } from 'node:net'
import { VideoService } from './service.js'

function sameSecret(a: string, b: string) {
  const left = Buffer.from(a), right = Buffer.from(b)
  return left.length === right.length && timingSafeEqual(left, right)
}
export function createApp(service: VideoService, accessToken = '') {
  const app = express()
  app.disable('x-powered-by')
  app.use((req, res, next) => {
    const hostname = req.hostname.replace(/^\[|\]$/g, '')
    if (!['localhost', '127.0.0.1', '::1'].includes(hostname) && !isIP(hostname)) {
      res.status(403).json({ error: 'localhost 또는 서버 IP 주소로 접속해 주세요.' }); return
    }
    res.setHeader('X-Content-Type-Options', 'nosniff')
    res.setHeader('Referrer-Policy', 'same-origin')
    res.setHeader('X-Frame-Options', 'DENY')
    if (accessToken) {
      const header = req.headers.authorization || ''
      const password = header.startsWith('Basic ') ? Buffer.from(header.slice(6), 'base64').toString('utf8').split(':').slice(1).join(':') : ''
      if (!sameSecret(password, accessToken)) {
        res.setHeader('WWW-Authenticate', 'Basic realm="VideoKiwi", charset="UTF-8"')
        res.status(401).send('VideoKiwi 접속 비밀번호를 입력해 주세요.'); return
      }
    }
    if (!['GET', 'HEAD', 'OPTIONS'].includes(req.method)) {
      const origin = req.headers.origin
      if (origin) {
        try {
          if (new URL(origin).host !== req.headers.host) throw new Error('origin')
        } catch { res.status(403).json({ error: '앱과 같은 주소에서 요청해 주세요.' }); return }
      }
      if (req.headers['sec-fetch-site'] === 'cross-site') {
        res.status(403).json({ error: '외부 사이트의 요청은 허용하지 않습니다.' }); return
      }
    }
    next()
  })
  app.use(express.json({ limit: '64kb' }))
  app.use('/api', (_req, res, next) => { res.setHeader('Cache-Control', 'no-store'); next() })
  app.get('/api/health', (_req, res) => { res.json({ ok: true, model: 'MiniMax H3', mode: 'local' }) })
  app.get('/api/bootstrap', async (_req, res) => {
    res.json({ settings: await service.settings(), jobs: service.store.jobs() })
  })
  app.get('/api/engine', async (_req, res) => { res.json(await service.engine(true)) })
  app.get('/api/jobs', (_req, res) => { res.json(service.store.jobs()) })
  const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 10 * 1024 * 1024, files: 1, fields: 0 } })
  app.post('/api/images', upload.single('image'), async (req, res) => {
    if (!req.file) { res.status(400).json({ error: '이미지를 선택해 주세요.' }); return }
    res.status(201).json(await service.importImage(req.file.buffer, req.file.originalname))
  })
  const videoUpload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 250 * 1024 * 1024, files: 1, fields: 0 } })
  app.post('/api/videos', videoUpload.single('video'), async (req, res) => {
    if (!req.file) { res.status(400).json({ error: '이어서 만들 원본 영상을 선택해 주세요.' }); return }
    res.status(201).json(await service.importVideo(req.file.buffer, req.file.originalname))
  })
  app.post('/api/jobs/:id/extension', async (req, res) => {
    res.json(await service.prepareExtension(req.params.id))
  })
  app.get('/api/extension-sources/:id/video', async (req, res) => {
    const source = await service.extensionSource(req.params.id)
    const type = source.file.endsWith('.webm') ? 'video/webm' : source.file.endsWith('.mov') ? 'video/quicktime' : 'video/mp4'
    res.type(type).sendFile(source.file, { dotfiles: 'allow' })
  })
  app.get('/api/images/:id', (req, res) => {
    const asset = service.store.asset(req.params.id)
    if (!asset) { res.status(404).json({ error: '이미지를 찾을 수 없습니다.' }); return }
    res.type('png').sendFile(asset.file, { dotfiles: 'allow' })
  })
  app.post('/api/prompt/optimize', async (req, res) => { res.json(await service.optimize(req.body)) })
  app.post('/api/jobs', async (req, res) => { res.status(202).json(await service.create(req.body)) })
  app.post('/api/jobs/:id/refresh', async (req, res) => { res.json(await service.refresh(req.params.id)) })
  app.post('/api/jobs/:id/cancel', async (req, res) => { res.json(await service.cancel(req.params.id)) })
  app.delete('/api/jobs/:id', async (req, res) => { await service.delete(req.params.id); res.status(204).end() })
  app.get('/api/jobs/:id/recipe', (req, res) => {
    const job = service.store.job(req.params.id)
    res.attachment(`videokiwi-${job.id.slice(0, 8)}.json`).json({ version: 1, model: 'MiniMax H3',
      input: job.input, plan: job.plan, optimization: job.optimization,
      elapsedSeconds: job.elapsedSeconds, status: job.status, createdAt: job.createdAt,
      extension: job.extension,
      image: job.image && { name: job.image.name, width: job.image.width, height: job.image.height },
      note: '실행 설정과 입력 기록입니다. 동일한 설정이라도 실행 환경에 따라 결과가 달라질 수 있습니다.' })
  })
  app.get('/api/jobs/:id/video', async (req, res) => {
    const local = await service.localVideo(req.params.id)
    if (local) {
      if (req.query.download === '1') res.attachment(`videokiwi-${req.params.id.slice(0, 8)}.mp4`)
      res.type('video/mp4').sendFile(local, { dotfiles: 'allow' })
      return
    }
    const url = await service.video(req.params.id)
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 120_000)
    res.on('close', () => { clearTimeout(timeout); controller.abort() })
    const headers: Record<string, string> = {}
    if (req.headers.range) headers.Range = req.headers.range
    try {
      const remote = await fetch(url, { headers, signal: controller.signal })
      if (!remote.ok || !remote.body) throw Object.assign(new Error('로컬 엔진의 결과 영상을 읽을 수 없습니다.'), { status: 502 })
      res.status(remote.status)
      for (const name of ['content-type', 'content-length', 'content-range', 'accept-ranges']) {
        const value = remote.headers.get(name)
        if (value) res.setHeader(name, value)
      }
      if (req.query.download === '1') res.attachment(`videokiwi-${req.params.id.slice(0, 8)}.mp4`)
      const stream = Readable.fromWeb(remote.body as import('node:stream/web').ReadableStream)
      stream.on('error', error => { if (!res.destroyed) res.destroy(error) })
      stream.pipe(res)
    } catch (error) {
      clearTimeout(timeout)
      if (!res.headersSent) throw error
      res.destroy()
    }
  })
  app.get('/api/events', (req, res) => {
    res.setHeader('Content-Type', 'text/event-stream')
    res.setHeader('Connection', 'keep-alive')
    res.setHeader('X-Accel-Buffering', 'no')
    res.flushHeaders()
    const update = (jobs: unknown) => res.write(`data: ${JSON.stringify(jobs)}\n\n`)
    service.on('jobs', update)
    update(service.store.jobs())
    const heartbeat = setInterval(() => res.write(': heartbeat\n\n'), 20_000)
    req.on('close', () => { clearInterval(heartbeat); service.off('jobs', update) })
  })
  app.use('/api', (_req, res) => { res.status(404).json({ error: '요청한 기능을 찾을 수 없습니다.' }) })
  app.use((error: Error & { status?: number; code?: string }, _req: Request, res: Response, _next: NextFunction) => {
    if (res.headersSent) { res.end(); return }
    const status = error.code === 'LIMIT_FILE_SIZE' ? 413 : error.status || (error instanceof multer.MulterError ? 400 : 400)
    const message = error.code === 'LIMIT_FILE_SIZE'
      ? _req.path === '/api/videos' ? '영상은 250MB 이하로 선택해 주세요.' : '이미지는 10MB 이하로 선택해 주세요.'
      : error.message || '요청을 처리하지 못했습니다.'
    res.status(status).json({ error: message })
  })
  return app
}

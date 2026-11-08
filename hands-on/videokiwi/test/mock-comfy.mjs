// Development test fixture only. It performs no model inference and is never used by the app automatically.
import express from 'express'
import multer from 'multer'
import { randomUUID } from 'node:crypto'
import { readFile, mkdir } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import { resolve } from 'node:path'
import { WebSocketServer, WebSocket } from 'ws'

export async function startMockComfy(directory, options = {}) {
  await mkdir(directory, { recursive: true })
  const videoPath = resolve(directory, 'fixture.mp4')
  const make = spawnSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
    `color=c=0x243d29:s=640x352:r=24:d=${options.duration || 1}`, '-f', 'lavfi', '-i', 'anullsrc=r=32000:cl=stereo',
    '-t', String(options.duration || 1), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', videoPath], { windowsHide: true })
  if (make.status !== 0) throw new Error('E2E 테스트 영상 생성에 ffmpeg가 필요합니다.')
  const video = await readFile(videoPath)
  const app = express()
  const jobs = new Map()
  const submissions = []
  const sockets = new Map()
  const progressEvents = []
  function send(clientId, type, data) {
    const socket = sockets.get(clientId)
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type, data }))
    progressEvents.push({ type, data })
  }
  let externalBusy = false
  app.use(express.json({ limit: '1mb' }))
  app.get('/system_stats', (_req, res) => res.json({ devices: [{ name: 'TEST FIXTURE GPU (no inference)',
    vram_total: 16 * 1024 ** 3, vram_free: 12 * 1024 ** 3 }] }))
  app.get('/object_info', (_req, res) => {
    const names = ['UnetLoaderGGUF', 'CLIPLoaderGGUF', 'VAELoader', 'MiniMaxH3ImageToVideo', 'LoadImage',
      'RandomNoise', 'BasicGuider', 'KSamplerSelect', 'BasicScheduler', 'SamplerCustomAdvanced', 'VAEDecodeTiled',
      'VAEDecodeAudio', 'CreateVideo', 'SaveVideo', 'MiniMaxH3SigmaShift', 'LoraLoaderModelOnly',
      'LoadVideo', 'GetVideoComponents', 'MiniMaxH3AddGuide']
    const info = Object.fromEntries(names.map(name => [name, { input: { required: {} } }]))
    info.UnetLoaderGGUF.input.required.unet_name = [['minimax_h3_fl2va_pruned-Q4_K.gguf']]
    info.CLIPLoaderGGUF.input.required.clip_name = [['qwen3vl-32B-MiniMax-H3-Q2_K.gguf']]
    info.VAELoader.input.required.vae_name = [['minimax_h3_video_vae_fp16.safetensors', 'minimax_h3_audio_vae_fp32.safetensors']]
    info.LoraLoaderModelOnly.input.required.lora_name = [['minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors']]
    res.json(info)
  })
  app.get('/queue', (_req, res) => res.json({ queue_running: externalBusy ? [[1, '22222222-2222-4222-8222-222222222222']] :
    [...jobs.values()].filter(job => !job.complete && !job.canceled).map(job => [1, job.id]), queue_pending: [] }))
  app.post('/upload/image', multer().single('image'), (req, res) => res.json({ name: req.file?.originalname || 'image.png', subfolder: 'fixture', type: 'input' }))
  app.post('/prompt', (req, res) => {
    const id = req.body.prompt_id || randomUUID()
    submissions.push(req.body)
    const job = { id, complete: false, canceled: false, clientId: req.body.client_id }
    jobs.set(id, job)
    const emit = (delay, type, data) => setTimeout(() => {
      if (!job.canceled) send(job.clientId, type, { prompt_id: id, ...data })
    }, delay).unref()
    emit(50, 'execution_start', {})
    emit(150, 'executing', { node: '5' })
    emit(400, 'executing', { node: '10' })
    emit(700, 'progress', { node: '10', value: 1, max: 8 })
    emit(1300, 'progress', { node: '10', value: 3, max: 8 })
    emit(2200, 'progress_state', { nodes: { '5': { state: 'finished', value: 1, max: 1 }, '10': { state: 'running', value: 6, max: 8 } } })
    emit(3000, 'progress', { node: '10', value: 8, max: 8 })
    emit(3200, 'executing', { node: '11' })
    emit(3700, 'progress_state', { nodes: { '10': { state: 'finished', value: 8, max: 8 }, '11': { state: 'running', value: 1, max: 2 } } })
    emit(4200, 'executing', { node: '14' })
    setTimeout(() => {
      if (!job.canceled) {
        job.complete = true
        send(job.clientId, 'executing', { node: null, prompt_id: id })
      }
    }, 4600).unref()
    res.json({ prompt_id: id, number: submissions.length, node_errors: {} })
  })
  app.get('/history/:id', (req, res) => {
    const job = jobs.get(req.params.id)
    if (!job || !job.complete && !job.canceled) { res.json({}); return }
    res.json({ [job.id]: { status: { status_str: job.canceled ? 'error' : 'success', completed: true,
      messages: job.canceled ? [['execution_interrupted', {}]] : [] }, outputs: job.canceled ? {} : {
      '14': { images: [{ filename: 'fixture.mp4', subfolder: 'video', type: 'output' }] }
    } } })
  })
  app.post('/interrupt', (req, res) => { const job = jobs.get(req.body.prompt_id); if (job) job.canceled = true; res.json({}) })
  app.post('/queue', (req, res) => { for (const id of req.body.delete || []) { const job = jobs.get(id); if (job) job.canceled = true }; res.json({}) })
  app.get('/view', (req, res) => {
    const range = req.headers.range
    res.type('mp4').setHeader('Accept-Ranges', 'bytes')
    if (range) {
      const [, a, b] = range.match(/bytes=(\d+)-(\d*)/) || []
      const start = Number(a || 0), end = Math.min(Number(b || video.length - 1), video.length - 1)
      res.status(206).setHeader('Content-Range', `bytes ${start}-${end}/${video.length}`)
      res.send(video.subarray(start, end + 1))
    } else res.send(video)
  })
  const server = await new Promise(resolve => { const s = app.listen(0, '127.0.0.1', () => resolve(s)) })
  const wss = new WebSocketServer({ server, path: '/ws' })
  wss.on('connection', (socket, request) => {
    const clientId = new URL(request.url, 'http://127.0.0.1').searchParams.get('clientId')
    sockets.set(clientId, socket)
    socket.send(JSON.stringify({ type: 'status', data: { sid: clientId, status: { exec_info: { queue_remaining: 0 } } } }))
    socket.on('close', () => { if (sockets.get(clientId) === socket) sockets.delete(clientId) })
  })
  const url = `http://127.0.0.1:${server.address().port}`
  return { url, submissions, progressEvents, setBusy: value => { externalBusy = value }, close: () => new Promise(resolve => {
    for (const socket of wss.clients) socket.terminate()
    wss.close()
    server.closeAllConnections(); server.close(resolve)
  }) }
}

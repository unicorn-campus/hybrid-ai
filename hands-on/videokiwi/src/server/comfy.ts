import { readFile } from 'node:fs/promises'
import type { EngineProgress, EngineStatus, ExecutionPlan, GenerationInput } from '../shared/types.js'
import { ComfyProgressTracker, type WebSocketFactory } from './comfy-progress.js'

type FetchLike = typeof fetch
type WorkflowNode = { class_type: string; inputs: Record<string, unknown> }
type Workflow = Record<string, WorkflowNode>
type VideoRef = { filename: string; subfolder: string; type: string }
type Inspection = {
  status: 'queued' | 'in_progress' | 'completed' | 'failed' | 'interrupted' | 'missing'
  video?: VideoRef
  error?: string
}

const MODEL_FILES = {
  unet: 'minimax_h3_fl2va_pruned-Q4_K.gguf',
  clip: 'qwen3vl-32B-MiniMax-H3-Q2_K.gguf',
  videoVae: 'minimax_h3_video_vae_fp16.safetensors',
  audioVae: 'minimax_h3_audio_vae_fp32.safetensors',
  turboLora: 'minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors'
} as const

const REQUIRED_NODES = [
  'UnetLoaderGGUF', 'CLIPLoaderGGUF', 'VAELoader', 'MiniMaxH3ImageToVideo', 'LoadImage',
  'RandomNoise', 'BasicGuider', 'KSamplerSelect', 'BasicScheduler',
  'SamplerCustomAdvanced', 'VAEDecodeTiled', 'VAEDecodeAudio', 'CreateVideo', 'SaveVideo'
]

function localBaseUrl(value: string): URL {
  const url = new URL(value)
  const host = url.hostname.replace(/^\[|\]$/g, '').toLowerCase()
  if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost', '::1'].includes(host)) {
    throw new Error('ComfyUI 주소는 이 컴퓨터의 HTTP 루프백 주소만 사용할 수 있습니다.')
  }
  url.pathname = url.pathname.replace(/\/$/, '')
  url.search = ''
  url.hash = ''
  return url
}

function record(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown> : undefined
}

function combo(info: Record<string, unknown> | undefined, key: string): string[] {
  const input = record(info?.input)
  const required = record(input?.required)
  const spec = required?.[key]
  if (!Array.isArray(spec) || !Array.isArray(spec[0])) return []
  return spec[0].filter((item): item is string => typeof item === 'string')
}

function queueIds(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.flatMap(item => Array.isArray(item) && typeof item[1] === 'string' ? [item[1]] : [])
}

function safeError(value: unknown): string {
  if (typeof value === 'string') return value.slice(0, 500)
  if (value instanceof Error) return value.message.slice(0, 500)
  return 'ComfyUI 요청을 처리하지 못했습니다.'
}

function validatePromptId(promptId: string): string {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(promptId)) {
    throw new Error('올바르지 않은 작업 ID입니다.')
  }
  return promptId
}

function validatePlan(plan: ExecutionPlan): void {
  if (![plan.width, plan.height].every(n => Number.isInteger(n) && n >= 32 && n <= 16384 && n % 32 === 0)) {
    throw new Error('영상 크기는 32의 배수여야 합니다.')
  }
  if (!Number.isInteger(plan.frames) || plan.frames < 5 || plan.frames > 3600 || plan.frames % 17 !== 5) {
    throw new Error('프레임 수는 MiniMax H3의 17k+5 규칙을 따라야 합니다.')
  }
  if (plan.fps !== 24) throw new Error('MiniMax H3 워크플로는 24fps만 지원합니다.')
  if (plan.turbo && (plan.steps !== 8 || plan.sampler !== 'euler')) {
    throw new Error('빠른 모드는 Euler 8단계 설정이 필요합니다.')
  }
  if (!plan.turbo && (![20, 30].includes(plan.steps) || plan.sampler !== 'res_multistep')) {
    throw new Error('일반 모드는 res_multistep 20단계 또는 30단계 설정이 필요합니다.')
  }
}

async function workflowTemplate(turbo: boolean): Promise<Workflow> {
  const file = turbo ? './workflows/turbo.json' : './workflows/base.json'
  return JSON.parse(await readFile(new URL(file, import.meta.url), 'utf8')) as Workflow
}

export class ComfyClient {
  private readonly base: URL
  private readonly fetcher: FetchLike
  private readonly progressTracker: ComfyProgressTracker
  readonly clientId: string

  constructor(options: {
    baseUrl?: string
    fetch?: FetchLike
    clientId?: string
    webSocketFactory?: WebSocketFactory
  } = {}) {
    this.base = localBaseUrl(options.baseUrl ?? 'http://127.0.0.1:8188')
    this.fetcher = options.fetch ?? fetch
    this.clientId = options.clientId ?? crypto.randomUUID()
    if (!/^[a-zA-Z0-9_-]{1,128}$/.test(this.clientId)) throw new Error('올바르지 않은 ComfyUI 클라이언트 ID입니다.')
    const socketUrl = this.url('/ws')
    socketUrl.protocol = 'ws:'
    socketUrl.searchParams.set('clientId', this.clientId)
    this.progressTracker = new ComfyProgressTracker(socketUrl.toString(), options.webSocketFactory)
  }

  private url(path: string): URL {
    const prefix = this.base.pathname === '/' ? '' : this.base.pathname
    return new URL(`${prefix}${path}`, this.base.origin)
  }

  private async request(path: string, init: RequestInit = {}, timeoutMs = 10_000): Promise<Response> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    try {
      const response = await this.fetcher(this.url(path), { ...init, signal: controller.signal })
      if (!response.ok) throw new Error(`ComfyUI 요청 실패 (${response.status})`)
      return response
    } catch (error) {
      if (controller.signal.aborted) throw new Error('ComfyUI 응답 시간이 초과되었습니다.')
      throw error
    } finally {
      clearTimeout(timer)
    }
  }

  private async json(path: string, init: RequestInit = {}, timeoutMs = 10_000): Promise<unknown> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    try {
      const response = await this.fetcher(this.url(path), { ...init, signal: controller.signal })
      if (!response.ok) throw new Error(`ComfyUI 요청 실패 (${response.status})`)
      try { return await response.json() }
      catch (error) {
        if (controller.signal.aborted) throw error
        throw new Error('ComfyUI가 올바른 JSON을 반환하지 않았습니다.')
      }
    } catch (error) {
      if (controller.signal.aborted) throw new Error('ComfyUI 응답 시간이 초과되었습니다.')
      throw error
    } finally { clearTimeout(timer) }
  }

  connectProgress(): Promise<void> {
    return this.progressTracker.connect()
  }

  trackProgress(promptId: string): void {
    this.progressTracker.track(validatePromptId(promptId))
  }

  onProgress(listener: (event: EngineProgress) => void): () => void {
    return this.progressTracker.on(listener)
  }

  getProgress(promptId: string): EngineProgress | undefined {
    return this.progressTracker.get(validatePromptId(promptId))
  }

  closeProgress(): void {
    this.progressTracker.close()
  }

  async queue(): Promise<{ running: string[]; pending: string[] }> {
    const body = record(await this.json('/queue'))
    if (!body) throw new Error('ComfyUI 큐 응답 형식이 올바르지 않습니다.')
    return { running: queueIds(body.queue_running), pending: queueIds(body.queue_pending) }
  }

  async health(): Promise<EngineStatus> {
    try {
      const [statsValue, objectValue, queue] = await Promise.all([
        this.json('/system_stats'), this.json('/object_info'), this.queue()
      ])
      const stats = record(statsValue) ?? {}
      const objectInfo = record(objectValue) ?? {}
      const devices = Array.isArray(stats.devices) ? stats.devices : []
      const device = record(devices[0])
      const allNodes = REQUIRED_NODES.every(name => record(objectInfo[name]) !== undefined)
      const models =
        combo(record(objectInfo.UnetLoaderGGUF), 'unet_name').includes(MODEL_FILES.unet) &&
        combo(record(objectInfo.CLIPLoaderGGUF), 'clip_name').includes(MODEL_FILES.clip) &&
        combo(record(objectInfo.VAELoader), 'vae_name').includes(MODEL_FILES.videoVae) &&
        combo(record(objectInfo.VAELoader), 'vae_name').includes(MODEL_FILES.audioVae)
      const turboAvailable =
        record(objectInfo.MiniMaxH3SigmaShift) !== undefined &&
        combo(record(objectInfo.LoraLoaderModelOnly), 'lora_name').includes(MODEL_FILES.turboLora)
      const extensionAvailable = ['LoadVideo', 'GetVideoComponents', 'MiniMaxH3AddGuide']
        .every(name => record(objectInfo[name]) !== undefined)
      return {
        connected: true,
        endpoint: this.base.origin,
        modelReady: allNodes && models,
        turboAvailable,
        extensionAvailable,
        gpu: typeof device?.name === 'string' ? device.name : undefined,
        vramTotalMB: typeof device?.vram_total === 'number' ? Math.round(device.vram_total / 1_048_576) : undefined,
        vramFreeMB: typeof device?.vram_free === 'number' ? Math.round(device.vram_free / 1_048_576) : undefined,
        queueRunning: queue.running.length,
        queuePending: queue.pending.length
      }
    } catch (error) {
      return {
        connected: false, endpoint: this.base.origin, modelReady: false, turboAvailable: false,
        extensionAvailable: false,
        queueRunning: 0, queuePending: 0, error: safeError(error)
      }
    }
  }

  async upload(bytes: Uint8Array, name: string): Promise<string> {
    const cleanName = name.replace(/[^a-zA-Z0-9._-]/g, '_').slice(-120)
    if (!cleanName || bytes.byteLength === 0) throw new Error('업로드할 미디어 파일이 비어 있습니다.')
    const form = new FormData()
    const copy = new Uint8Array(bytes.byteLength)
    copy.set(bytes)
    form.append('image', new Blob([copy.buffer]), cleanName)
    form.append('type', 'input')
    form.append('overwrite', 'false')
    const body = record(await this.json('/upload/image', { method: 'POST', body: form }, 30_000))
    const uploaded = record(body?.asset) ?? body
    const uploadedName = typeof uploaded?.name === 'string' ? uploaded.name : undefined
    const subfolder = typeof uploaded?.subfolder === 'string' ? uploaded.subfolder : ''
    if (!uploadedName) throw new Error('ComfyUI 이미지 업로드 응답에 파일명이 없습니다.')
    return [subfolder.replace(/\\/g, '/').replace(/^\/+|\/+$/g, ''), uploadedName].filter(Boolean).join('/')
  }

  async submit(
    input: GenerationInput,
    plan: ExecutionPlan,
    firstImage?: string,
    lastImage?: string,
    guideVideo?: string
  ): Promise<string> {
    validatePlan(plan)
    if (!input.prompt.trim()) throw new Error('영상 설명을 입력해 주세요.')
    if (!Number.isSafeInteger(input.seed) || input.seed < 0) throw new Error('시드는 0 이상의 정수여야 합니다.')
    if (input.mode === 'image' && !firstImage && !guideVideo) {
      throw new Error('이미지 모드에는 시작 이미지 또는 확장 가이드가 필요합니다.')
    }
    if (guideVideo && firstImage) throw new Error('영상 확장 가이드와 시작 이미지를 함께 사용할 수 없습니다.')
    const workflow = await workflowTemplate(plan.turbo)
    workflow['5'].inputs.prompt = input.prompt.trim()
    workflow['5'].inputs.width = plan.width
    workflow['5'].inputs.height = plan.height
    workflow['5'].inputs.length = plan.frames
    workflow['6'].inputs.noise_seed = input.seed
    workflow['8'].inputs.sampler_name = plan.sampler
    workflow['9'].inputs.steps = plan.steps
    workflow['13'].inputs.fps = plan.fps
    workflow['14'].inputs.filename_prefix = `video/VideoKiwi_${crypto.randomUUID()}`
    let nextNode = plan.turbo ? 17 : 15
    if (firstImage) {
      const id = String(nextNode++)
      workflow[id] = { class_type: 'LoadImage', inputs: { image: firstImage } }
      workflow['5'].inputs.first_frame = [id, 0]
    }
    if (lastImage) {
      const id = String(nextNode)
      workflow[id] = { class_type: 'LoadImage', inputs: { image: lastImage } }
      workflow['5'].inputs.last_frame = [id, 0]
    }
    if (guideVideo) {
      workflow['30'] = { class_type: 'LoadVideo', inputs: { file: guideVideo } }
      workflow['31'] = { class_type: 'GetVideoComponents', inputs: { video: ['30', 0] } }
      // The guide clip (last 17k+5 source frames with their sound) is anchored at frame 0,
      // so the new segment starts inside the original motion and soundtrack.
      workflow['32'] = {
        class_type: 'MiniMaxH3AddGuide',
        inputs: {
          positive: ['5', 0], latent: ['5', 1], frame_idx: 0,
          vae: ['3', 0], image: ['31', 0],
          audio_vae: ['4', 0], audio: ['31', 1]
        }
      }
      workflow['7'].inputs.conditioning = ['32', 0]
    }
    await this.connectProgress().catch(() => undefined)
    const requestedId = crypto.randomUUID()
    this.progressTracker.track(requestedId)
    let body: Record<string, unknown> | undefined
    try {
      body = record(await this.json('/prompt', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          prompt: workflow, prompt_id: requestedId, client_id: this.clientId,
          extra_data: { videokiwi: { version: 1 } }
        })
      }, 30_000))
    } catch (error) {
      this.progressTracker.forget(requestedId)
      throw error
    }
    if (!body || typeof body.prompt_id !== 'string') {
      this.progressTracker.forget(requestedId)
      throw new Error('ComfyUI 제출 응답에 작업 ID가 없습니다.')
    }
    const returnedId = validatePromptId(body.prompt_id)
    this.progressTracker.rebind(requestedId, returnedId)
    return returnedId
  }

  async inspect(promptId: string): Promise<Inspection> {
    const id = validatePromptId(promptId)
    const history = record(await this.json(`/history/${encodeURIComponent(id)}`))
    const item = record(history?.[id])
    if (item) {
      const status = record(item.status) ?? {}
      const messages = Array.isArray(status.messages) ? status.messages : []
      const interrupted = messages.some(message => Array.isArray(message) && message[0] === 'execution_interrupted')
      if (interrupted) return { status: 'interrupted' }
      if (status.completed === true || status.status_str === 'success') {
        const outputs = record(item.outputs) ?? {}
        for (const output of Object.values(outputs)) {
          const out = record(output)
          for (const key of ['images', 'videos']) {
            const values = Array.isArray(out?.[key]) ? out[key] as unknown[] : []
            for (const value of values) {
              const media = record(value)
              if (typeof media?.filename === 'string' && /\.(mp4|mkv|webm)$/i.test(media.filename)) {
                return { status: 'completed', video: {
                  filename: media.filename,
                  subfolder: typeof media.subfolder === 'string' ? media.subfolder : '',
                  type: typeof media.type === 'string' ? media.type : 'output'
                } }
              }
            }
          }
        }
        return { status: 'failed', error: '완료 기록에서 영상 파일을 찾지 못했습니다.' }
      }
      const errorMessage = messages.find(message => Array.isArray(message) && message[0] === 'execution_error')
      return { status: 'failed', error: safeError(errorMessage ?? status.status_str) }
    }
    const queue = await this.queue()
    if (queue.running.includes(id)) return { status: 'in_progress' }
    if (queue.pending.includes(id)) return { status: 'queued' }
    return { status: 'missing' }
  }

  async cancel(promptId: string): Promise<'canceled' | 'already_finished'> {
    const id = validatePromptId(promptId)
    let queue = await this.queue()
    if (queue.running.includes(id)) {
      await this.request('/interrupt', {
        method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ prompt_id: id })
      })
      return 'canceled'
    }
    if (queue.pending.includes(id)) {
      await this.request('/queue', {
        method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ delete: [id] })
      })
      queue = await this.queue()
      if (queue.running.includes(id)) {
        await this.request('/interrupt', {
          method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ prompt_id: id })
        })
      } else if (queue.pending.includes(id)) {
        throw new Error('대기 작업 취소를 확인하지 못했습니다.')
      }
      return 'canceled'
    }
    return 'already_finished'
  }

  videoURL(ref: VideoRef): string {
    if (!ref.filename || ref.filename.includes('..') || ref.subfolder.includes('..')) {
      throw new Error('올바르지 않은 영상 파일 경로입니다.')
    }
    const url = this.url('/view')
    url.searchParams.set('filename', ref.filename)
    url.searchParams.set('subfolder', ref.subfolder)
    url.searchParams.set('type', ref.type)
    return url.toString()
  }
}

export type { Inspection, VideoRef }

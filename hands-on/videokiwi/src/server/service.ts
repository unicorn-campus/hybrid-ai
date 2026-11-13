import { EventEmitter } from 'node:events'
import { randomUUID } from 'node:crypto'
import { copyFile, readFile, stat, unlink, writeFile } from 'node:fs/promises'
import { extname, join } from 'node:path'
import sharp from 'sharp'
import type {
  AppSettings,
  EngineProgress,
  EngineStatus,
  ExecutionPlan,
  ExtensionSource,
  GenerationInput,
  ImageAsset,
  PromptAssistantStatus,
  PromptOptimization,
  VideoJob
} from '../shared/types.js'
import { CAMERA_PROMPTS, TERMINAL_STATUSES } from '../shared/types.js'
import { Store, displayImageName, type StoredAsset, type StoredExtensionSource } from './store.js'
import { buildPlan, optimizePrompt, validateInput, ensureAudioBoundaries, normalizeTitle } from './harness.js'
import { ComfyClient } from './comfy.js'
import { concatenateExtendedVideo, extractExtensionGuide, probeVideo } from './video-media.js'

const fail = (message: string, status = 400) => Object.assign(new Error(message), { status })
const terminal = (job: VideoJob) => TERMINAL_STATUSES.includes(job.status)
const publicAsset = ({ id, name, previewUrl, size, mime, width, height, brightness, dominantColor }: ImageAsset): ImageAsset =>
  ({ id, name, previewUrl, size, mime, width, height, brightness, dominantColor })
const publicExtension = ({ file: _file, guideFile: _guide, hasAudio: _audio, ...source }: StoredExtensionSource): ExtensionSource => source
const MAX_VIDEO_BYTES = 250 * 1024 * 1024

export interface PromptAdvisor {
  status(): Promise<PromptAssistantStatus>
  optimize(input: GenerationInput, image?: StoredAsset, endImage?: StoredAsset): Promise<PromptOptimization>
}

interface ProgressClient {
  trackProgress(promptId: string): void
  connectProgress(): Promise<void>
  onProgress(callback: (progress: EngineProgress) => void): () => void
  getProgress(promptId: string): EngineProgress | undefined
  closeProgress(): void
}

export class VideoService extends EventEmitter {
  private creating = false
  private checking = new Set<string>()
  private submitting = new Set<string>()
  private canceling = new Set<string>()
  private preparingExtensions = new Map<string, Promise<ExtensionSource>>()
  private engineCache?: { at: number; value: EngineStatus }
  private timer?: NodeJS.Timeout
  private progressSaveTimer?: NodeJS.Timeout
  private progressUnsubscribe?: () => void
  private progressDirty = false
  private lastProgressSavedAt = 0
  private media = new Map<string, { filename: string; subfolder: string; type: string }>()
  constructor(readonly store: Store, readonly client: ComfyClient, readonly advisor?: PromptAdvisor) { super() }
  private progressClient(): Partial<ProgressClient> {
    return this.client as unknown as Partial<ProgressClient>
  }
  async open() {
    await this.store.open()
    for (const job of this.store.state.jobs) {
      if (!terminal(job) && !job.requestId) {
        job.status = 'interrupted'
        job.error = '서버가 제출 중 종료되었습니다. 중복 생성을 피하려면 ComfyUI 기록을 확인한 뒤 다시 만들어 주세요.'
      }
    }
    const progress = this.progressClient()
    if (progress.onProgress) {
      this.progressUnsubscribe = progress.onProgress(event => {
        void this.receiveProgress(event).catch(error => console.error('진행 상태 저장 실패:', String(error)))
      })
    }
    if (progress.trackProgress) {
      for (const job of this.store.state.jobs) {
        if (!terminal(job) && job.requestId) progress.trackProgress(job.requestId)
      }
    }
    if (progress.connectProgress) {
      // 엔진이 아직 꺼져 있어도 앱은 그대로 뜸. 진행 연결은 잠시 재시도하고, 영상 제출 때 다시 연결함
      await progress.connectProgress().catch(error => console.warn(
        '안내: MiniMax H3 엔진에 아직 연결하지 못했습니다.\n' +
        `  원인: ${error instanceof Error ? error.message : String(error)}\n` +
        '  엔진이 꺼져 있다면 ~/AI/H3-Local/start-h3.cmd로 켜 주세요. 켠 뒤 영상을 만들면 자동으로 다시 연결합니다.'
      ))
    }
    await this.store.save()
    this.timer = setInterval(() => { void this.poll().catch(error => console.error('상태 확인 실패:', String(error))) }, 3000)
    this.timer.unref()
    void this.poll().catch(() => {})
  }
  close() {
    if (this.timer) clearInterval(this.timer)
    if (this.progressSaveTimer) clearTimeout(this.progressSaveTimer)
    this.progressUnsubscribe?.()
    this.timer = undefined
    this.progressSaveTimer = undefined
    this.progressUnsubscribe = undefined
    this.progressClient().closeProgress?.()
    if (this.progressDirty) void this.store.save().catch(() => {})
    this.progressDirty = false
  }
  private clearNodeProgress(job: VideoJob) {
    delete job.progress
    delete job.progressKind
    delete job.progressNode
    delete job.progressValue
    delete job.progressMax
  }
  private applyProgressEvent(event: EngineProgress): VideoJob | undefined {
    const job = this.store.state.jobs.find(item => item.requestId === event.promptId)
    if (!job || terminal(job)) return undefined
    const eventTime = Date.parse(event.updatedAt)
    const currentTime = job.progressUpdatedAt ? Date.parse(job.progressUpdatedAt) : Number.NaN
    if (Number.isFinite(eventTime) && Number.isFinite(currentTime) && eventTime < currentTime) return undefined

    const timestamp = Number.isFinite(eventTime) ? event.updatedAt : new Date().toISOString()
    const stage = event.stage.trim()
    if (stage) job.stage = stage
    job.progressUpdatedAt = timestamp
    job.progressConnected = event.kind !== 'disconnected' && event.connected

    if (event.kind === 'disconnected' || event.kind === 'complete') {
      this.clearNodeProgress(job)
    } else if (event.kind === 'node') {
      this.clearNodeProgress(job)
      job.progressKind = 'node'
      if (event.node) job.progressNode = event.node
    } else {
      const value = event.value
      const max = event.max
      const measured = typeof value === 'number' && Number.isFinite(value) &&
        typeof max === 'number' && Number.isFinite(max) && max > 0
      if (measured) {
        const calculated = value / max * 100
        const percent = typeof event.percent === 'number' && Number.isFinite(event.percent)
          ? event.percent : calculated
        job.progress = Math.max(0, Math.min(100, percent))
        job.progressKind = event.kind
        job.progressValue = value
        job.progressMax = max
        if (event.node) job.progressNode = event.node
        else delete job.progressNode
      } else {
        this.clearNodeProgress(job)
        job.progressKind = 'node'
        if (event.node) job.progressNode = event.node
      }
    }

    if (event.kind !== 'disconnected' && ['uploading', 'queued'].includes(job.status)) {
      job.status = 'in_progress'
    }
    const now = Date.now()
    job.elapsedSeconds = job.submittedAt ? Math.round((now - Date.parse(job.submittedAt)) / 1000) : undefined
    job.updatedAt = new Date(now).toISOString()
    return job
  }
  private async persistProgress() {
    if (!this.progressDirty) return
    this.progressDirty = false
    this.lastProgressSavedAt = Date.now()
    try { await this.store.save() }
    catch (error) {
      this.progressDirty = true
      throw error
    }
  }
  private async progressChanged() {
    this.emit('jobs', this.store.jobs())
    this.progressDirty = true
    const wait = Math.max(0, 1000 - (Date.now() - this.lastProgressSavedAt))
    if (wait === 0) {
      if (this.progressSaveTimer) clearTimeout(this.progressSaveTimer)
      this.progressSaveTimer = undefined
      await this.persistProgress()
      return
    }
    if (!this.progressSaveTimer) {
      this.progressSaveTimer = setTimeout(() => {
        this.progressSaveTimer = undefined
        void this.persistProgress().catch(error => console.error('진행 상태 저장 실패:', String(error)))
      }, wait)
      this.progressSaveTimer.unref()
    }
  }
  private async receiveProgress(event: EngineProgress) {
    if (!this.applyProgressEvent(event)) return
    await this.progressChanged()
  }
  async engine(force = false): Promise<EngineStatus> {
    if (!force && this.engineCache && Date.now() - this.engineCache.at < 5000) return this.engineCache.value
    const value = await this.client.health()
    this.engineCache = { at: Date.now(), value }
    return value
  }
  async settings(): Promise<AppSettings> {
    const [engine, promptAssistant] = await Promise.all([this.engine(), this.advisor?.status()])
    return { engine, promptAssistant, dataDirectory: this.store.directory }
  }
  async changed() {
    if (this.progressSaveTimer) clearTimeout(this.progressSaveTimer)
    this.progressSaveTimer = undefined
    this.progressDirty = false
    this.lastProgressSavedAt = Date.now()
    await this.store.save()
    this.emit('jobs', this.store.jobs())
  }
  async importImage(bytes: Buffer, name: string): Promise<ImageAsset> {
    if (!bytes.length || bytes.length > 10 * 1024 * 1024) throw fail('이미지는 10MB 이하로 선택해 주세요.')
    let result: Buffer
    try {
      const metadata = await sharp(bytes, { limitInputPixels: 40_000_000 }).metadata()
      if (!['jpeg', 'png', 'webp'].includes(metadata.format || '') || (metadata.pages || 1) > 1) {
        throw new Error('unsupported')
      }
      result = await sharp(bytes, { limitInputPixels: 40_000_000 }).rotate()
        .resize({ width: 2048, height: 2048, fit: 'inside', withoutEnlargement: true })
        .removeAlpha().png().toBuffer()
    } catch { throw fail('PNG, JPG 또는 WebP 정지 이미지를 선택해 주세요.') }
    const { width, height } = await sharp(result).metadata()
    const stats = await sharp(result).stats()
    const id = randomUUID()
    const file = join(this.store.directory, 'images', `${id}.png`)
    await writeFile(file, result)
    const color = stats.dominant
    const hex = '#' + [color.r, color.g, color.b].map(v => v.toString(16).padStart(2, '0')).join('')
    const mean = stats.channels.map(channel => channel.mean)
    const asset = {
      id, name: displayImageName(name).replace(/[\\/\x00-\x1f]/g, '_').slice(-140) || 'image.png', file,
      previewUrl: `/api/images/${id}`, size: result.length, mime: 'image/png',
      width: width!, height: height!, dominantColor: hex,
      brightness: Math.round((mean[0] * 0.2126 + mean[1] * 0.7152 + mean[2] * 0.0722) / 255 * 100)
    }
    this.store.state.assets.push(asset)
    await this.store.save()
    return publicAsset(asset)
  }
  private extensionGeometry(width: number, height: number): { width: number; height: number } {
    if ([width, height].every(value => value >= 32 && value <= 864 && value % 32 === 0)) return { width, height }
    const ratio = width / height
    const area = 864 * 480
    let targetHeight = Math.max(32, Math.floor(Math.sqrt(area / ratio) / 32) * 32)
    let targetWidth = Math.max(32, Math.floor(targetHeight * ratio / 32) * 32)
    while (targetWidth * targetHeight > area) {
      if (targetWidth >= targetHeight) targetWidth -= 32
      else targetHeight -= 32
    }
    return { width: targetWidth, height: targetHeight }
  }
  private async storeExtension(file: string, name: string, sourceJobId?: string): Promise<ExtensionSource> {
    const info = await probeVideo(file)
    if (info.duration > 300) throw fail('확장할 영상은 5분 이하여야 합니다.')
    const availableFrames = info.frames ?? Math.floor(info.duration * 24 + 0.001)
    const guideFrames = availableFrames >= 22 ? 22 : availableFrames >= 5 ? 5 : 0
    if (!guideFrames) throw fail('확장할 영상은 최소 5프레임 이상이어야 합니다.')
    const geometry = this.extensionGeometry(info.width, info.height)
    const id = randomUUID()
    const guideFile = join(this.store.directory, 'videos', `${id}.guide.mp4`)
    const guide = await extractExtensionGuide(file, guideFile, { ...geometry, fps: 24, guideFrames })
    const imageBytes = await readFile(guide.lastFramePath)
    const image = await this.importImage(imageBytes, `${name.replace(/\.[^.]+$/u, '')}-마지막.png`)
    const source: StoredExtensionSource = {
      id, name: displayImageName(name).replace(/[\\/\x00-\x1f]/g, '_').slice(-140) || 'source.mp4',
      videoUrl: `/api/extension-sources/${id}/video`, image, ...geometry,
      duration: info.duration, fps: 24, guideFrames, sourceJobId,
      file, guideFile: guide.guidePath, hasAudio: info.hasAudio
    }
    this.store.state.extensionSources.push(source)
    await this.store.save()
    return publicExtension(source)
  }
  async importVideo(bytes: Buffer, name: string): Promise<ExtensionSource> {
    if (!bytes.length || bytes.length > MAX_VIDEO_BYTES) throw fail('영상은 250MB 이하로 선택해 주세요.')
    const extension = extname(name).toLowerCase()
    if (!['.mp4', '.mov', '.webm'].includes(extension)) throw fail('MP4, MOV 또는 WebM 영상을 선택해 주세요.')
    const file = join(this.store.directory, 'videos', `${randomUUID()}.source${extension}`)
    await writeFile(file, bytes, { flag: 'wx' })
    try { return await this.storeExtension(file, name) }
    catch (error) { await unlink(file).catch(() => undefined); throw error }
  }
  async prepareExtension(jobId: string): Promise<ExtensionSource> {
    const existing = this.store.state.extensionSources.find(source => source.sourceJobId === jobId)
    if (existing) return publicExtension(existing)
    const inFlight = this.preparingExtensions.get(jobId)
    if (inFlight) return inFlight
    const preparation = this.prepareExtensionJob(jobId)
    this.preparingExtensions.set(jobId, preparation)
    try { return await preparation }
    finally { this.preparingExtensions.delete(jobId) }
  }
  private async prepareExtensionJob(jobId: string): Promise<ExtensionSource> {
    const job = this.store.job(jobId)
    if (job.status !== 'completed') throw fail('완료된 영상만 이어서 만들 수 있습니다.', 409)
    const file = join(this.store.directory, 'videos', `${randomUUID()}.source.mp4`)
    try {
      if (job.localPath) await copyFile(job.localPath, file)
      else {
        const url = await this.video(jobId)
        const response = await fetch(url, { signal: AbortSignal.timeout(120_000) })
        if (!response.ok) throw new Error(`원본 영상 읽기 실패 (${response.status})`)
        const declared = Number(response.headers.get('content-length'))
        if (Number.isFinite(declared) && declared > MAX_VIDEO_BYTES) throw fail('영상은 250MB 이하여야 합니다.')
        const bytes = Buffer.from(await response.arrayBuffer())
        if (bytes.length > MAX_VIDEO_BYTES) throw fail('영상은 250MB 이하여야 합니다.')
        await writeFile(file, bytes, { flag: 'wx' })
      }
      return await this.storeExtension(file, `videokiwi-${job.id.slice(0, 8)}.mp4`, job.id)
    } catch (error) { await unlink(file).catch(() => undefined); throw error }
  }
  extensionSource(id: string): StoredExtensionSource {
    const source = this.store.extensionSource(id)
    if (!source) throw fail('확장 원본 영상을 찾을 수 없습니다.', 404)
    return source
  }
  async localVideo(id: string): Promise<string | undefined> {
    const path = this.store.job(id).localPath
    if (!path) return undefined
    const value = await stat(path).catch(() => undefined)
    return value?.isFile() ? path : undefined
  }
  inputs(value: unknown) {
    const input = validateInput(value)
    const extension = this.store.extensionSource(input.extensionSourceId)
    const extensionImage = extension ? this.store.asset(extension.image.id) : undefined
    const image = this.store.asset(input.imageId) ?? extensionImage
    const endImage = this.store.asset(input.endImageId)
    if (input.extensionSourceId && !extension) throw fail('선택한 확장 원본 영상이 없습니다. 다시 선택해 주세요.')
    if (input.mode === 'image' && !image) throw fail('시작 이미지 또는 확장 원본 영상을 먼저 추가해 주세요.')
    if (input.imageId && !image || input.endImageId && !endImage) throw fail('선택한 이미지가 없습니다. 다시 추가해 주세요.')
    return { input, image, endImage, extension }
  }
  async optimize(value: unknown) {
    const { input, image, endImage } = this.inputs(value)
    if (this.advisor) return this.advisor.optimize(input, image, endImage)
    return optimizePrompt(input, image, endImage)
  }
  async create(value: unknown): Promise<VideoJob> {
    if (this.creating || this.store.state.jobs.some(job => !terminal(job))) {
      throw fail('이미 진행 중인 작업이 있습니다. 완료되거나 취소된 뒤 다시 만들어 주세요.', 409)
    }
    this.creating = true
    try {
      const { input, image, endImage, extension } = this.inputs(value)
      const engine = await this.engine(true)
      if (!engine.connected || !engine.modelReady) throw fail(engine.error || '로컬 H3 엔진과 모델 준비 상태를 확인해 주세요.', 503)
      if (extension && !engine.extensionAvailable) throw fail('로컬 H3 엔진에서 영상 확장 노드를 찾지 못했습니다.', 503)
      if (engine.queueRunning || engine.queuePending) throw fail('ComfyUI가 다른 작업을 처리하고 있습니다. 기존 작업이 끝난 뒤 다시 만들어 주세요.', 409)
      const optimization = input.optimize
        ? this.advisor ? await this.advisor.optimize(input, image, endImage) : optimizePrompt(input, image, endImage)
        : undefined
      let manualPrompt = input.prompt
      const reviewed = input.originalPrompt && input.originalPrompt !== input.prompt
      if (!optimization && !reviewed) {
        const camera = CAMERA_PROMPTS[input.camera]
        if (camera && !manualPrompt.includes(camera)) manualPrompt += `\n\nCamera: ${camera}`
        if (input.audio && !manualPrompt.includes(input.audio)) manualPrompt += `\n\nAudio: ${input.audio}`
      }
      if (extension) manualPrompt += '\n\nContinue directly from the supplied ending motion. Preserve subject identity, movement direction, camera motion, lighting, and spatial continuity without a cut or reset.'
      // The title is a library label; keep it on the job, out of the engine input and the recipe input.
      const { title, ...engineInput } = input
      const actualInput: GenerationInput = { ...engineInput, originalPrompt: input.originalPrompt || input.prompt,
        prompt: ensureAudioBoundaries(input, optimization?.optimized || manualPrompt) }
      const plan = buildPlan(actualInput, engine, image, extension)
      const now = new Date().toISOString()
      const job: VideoJob = { id: randomUUID(), title, input: actualInput, status: 'uploading', createdAt: now, updatedAt: now,
        image: image ? publicAsset(image) : undefined, endImage: endImage ? publicAsset(endImage) : undefined,
        plan, optimization, stage: '입력 준비', warnings: plan.warnings,
        extension: extension ? {
          sourceId: extension.id, sourceJobId: extension.sourceJobId,
          sourceDuration: extension.duration, overlapFrames: extension.guideFrames,
          addedDuration: Number(((plan.frames - extension.guideFrames) / plan.fps).toFixed(3)),
          totalDuration: Number((extension.duration + (plan.frames - extension.guideFrames) / plan.fps).toFixed(3))
        } : undefined }
      this.store.state.jobs.push(job)
      await this.changed()
      this.submitting.add(job.id)
      void this.submit(job, plan).catch(error => console.error('작업 저장 실패:', String(error)))
        .finally(() => this.submitting.delete(job.id))
      return job
    } finally { this.creating = false }
  }
  private async submit(job: VideoJob, plan: ExecutionPlan) {
    try {
      let first: string | undefined, last: string | undefined, guideVideo: string | undefined
      if (job.image && !job.extension) {
        const asset = this.store.asset(job.image.id)!
        first = await this.client.upload(await readFile(asset.file), `${asset.id}.png`)
      }
      if (job.endImage) {
        const asset = this.store.asset(job.endImage.id)!
        last = await this.client.upload(await readFile(asset.file), `${asset.id}.png`)
      }
      if (job.extension) {
        const source = this.extensionSource(job.extension.sourceId)
        guideVideo = await this.client.upload(await readFile(source.guideFile), `${source.id}.mp4`)
      }
      // This POST is intentionally never retried: a timeout can still mean the engine accepted it.
      job.stage = '엔진에 제출'
      job.submittedAt = new Date().toISOString()
      await this.changed()
      job.requestId = await this.client.submit(job.input, plan, first, last, guideVideo)
      job.status = 'queued'
      job.stage = '생성 대기'
      const progress = this.progressClient()
      progress.trackProgress?.(job.requestId)
      const cached = progress.getProgress?.(job.requestId)
      if (cached) this.applyProgressEvent(cached)
    } catch (error) {
      job.status = 'interrupted'
      job.error = `${(error as Error).message} 제출 여부가 불확실하면 ComfyUI 기록을 확인해 주세요. 자동 재제출하지 않습니다.`
      job.stage = '확인 필요'
    }
    job.updatedAt = new Date().toISOString()
    await this.changed()
  }
  async poll() {
    await Promise.allSettled(this.store.state.jobs.filter(job => !terminal(job) && job.requestId)
      .map(job => this.refresh(job.id)))
  }
  async refresh(id: string): Promise<VideoJob> {
    const job = this.store.job(id)
    if (terminal(job) && job.status !== 'interrupted' || !job.requestId || this.checking.has(id) || this.canceling.has(id)) return job
    this.checking.add(id)
    try {
      const result = await this.client.inspect(job.requestId)
      const preserveEventStage = Boolean(
        job.progressUpdatedAt &&
        ['queued', 'in_progress'].includes(job.status) &&
        ['queued', 'in_progress'].includes(result.status)
      )
      if (result.status === 'missing') {
        job.status = 'interrupted'
        job.error = '엔진의 대기열과 기록에서 작업을 찾을 수 없습니다. 엔진 기록을 확인한 뒤 다시 만들어 주세요.'
      } else {
        if (!(preserveEventStage && job.status === 'in_progress' && result.status === 'queued')) {
          job.status = result.status
        }
        job.error = result.error
      }
      if (!preserveEventStage || terminal(job)) {
        job.stage = ({ queued: '생성 대기', in_progress: '영상과 소리 생성', completed: '완료',
          failed: '생성 실패', interrupted: '확인 필요', canceled: '취소됨', uploading: '입력 준비' } as const)[job.status]
      }
      if (result.video) {
        this.media.set(id, result.video)
        job.videoUrl = `/api/jobs/${id}/video`
      }
      if (job.status === 'completed' && job.extension && !job.localPath && result.video) {
        // The engine only made the new segment. Keep the job running until it is joined to the source.
        job.status = 'in_progress'
        job.stage = '원본과 이어 붙이기'
        this.clearNodeProgress(job)
        job.updatedAt = new Date().toISOString()
        await this.changed()
        try {
          await this.finalizeExtension(job, result.video)
          job.status = 'completed'
          job.stage = '완료'
          job.error = undefined
        } catch (error) {
          job.status = 'interrupted'
          job.stage = '확인 필요'
          job.error = `새 구간은 생성됐지만 원본과 이어 붙이지 못했습니다. ${(error as Error).message} ` +
            '상태 다시 확인을 누르면 이어 붙이기만 다시 시도합니다.'
        }
      }
      if (job.status === 'completed' && !result.video && !job.videoUrl) {
        job.status = 'failed'
        job.stage = '생성 실패'
        job.error = '엔진 작업은 종료됐지만 MP4 결과를 찾을 수 없습니다.'
      }
      if (job.status === 'completed') {
        this.clearNodeProgress(job)
        job.progress = 100
        job.progressUpdatedAt = new Date().toISOString()
      } else if (terminal(job)) {
        this.clearNodeProgress(job)
      }
      job.elapsedSeconds = job.submittedAt ? Math.round((Date.now() - Date.parse(job.submittedAt)) / 1000) : undefined
      if (terminal(job)) job.completedAt = new Date().toISOString()
      if (!terminal(job) && (job.elapsedSeconds || 0) > 3600) {
        job.status = 'interrupted'
        job.stage = '확인 필요'
        job.warnings = [...new Set([...(job.warnings || []), '1시간 동안 기다려 자동 상태 확인을 멈췄습니다. 엔진 작업은 유지하며 새로고침으로 다시 확인할 수 있습니다.'])]
      }
      job.updatedAt = new Date().toISOString()
      await this.changed()
    } catch (error) {
      // A polling outage is not proof of generation failure. Keep the remote ID for reconnection.
      if (!job.progressUpdatedAt || job.progressConnected === false) job.stage = '엔진 재연결 대기'
      job.error = (error as Error).message
      job.updatedAt = new Date().toISOString()
      await this.changed()
    } finally { this.checking.delete(id) }
    return job
  }
  private async finalizeExtension(job: VideoJob, ref: { filename: string; subfolder: string; type: string }) {
    const extension = job.extension!
    const plan = job.plan!
    const source = this.extensionSource(extension.sourceId)
    const directory = join(this.store.directory, 'videos')
    const segment = join(directory, `${job.id}.segment.mp4`)
    const output = join(directory, `${job.id}.extended.mp4`)
    // A previous attempt may have stopped halfway; both files belong only to this job.
    await Promise.all([unlink(segment).catch(() => undefined), unlink(output).catch(() => undefined)])
    const response = await fetch(this.client.videoURL(ref), { signal: AbortSignal.timeout(120_000) })
    if (!response.ok) throw new Error(`엔진에서 새 구간을 읽지 못했습니다 (${response.status}).`)
    const bytes = Buffer.from(await response.arrayBuffer())
    if (!bytes.length || bytes.length > MAX_VIDEO_BYTES) throw new Error('엔진이 돌려준 새 구간의 크기가 올바르지 않습니다.')
    await writeFile(segment, bytes, { flag: 'wx' })
    try {
      const joined = await concatenateExtendedVideo(source.file, segment, output, {
        overlapFrames: extension.overlapFrames, fps: plan.fps, width: plan.width, height: plan.height
      })
      const segmentInfo = await probeVideo(segment)
      extension.addedDuration = Number(Math.max(0, segmentInfo.duration - extension.overlapFrames / plan.fps).toFixed(3))
      extension.totalDuration = Number(joined.duration.toFixed(3))
      job.localPath = output
    } finally {
      await unlink(segment).catch(() => undefined)
    }
  }
  async cancel(id: string) {
    const job = this.store.job(id)
    if (terminal(job)) return job
    if (this.submitting.has(id) || !job.requestId) throw fail('엔진에 제출 중입니다. 작업 번호가 확인된 뒤 취소해 주세요.', 409)
    if (this.canceling.has(id) || this.checking.has(id)) throw fail('상태 확인 중입니다. 잠시 후 다시 취소해 주세요.', 409)
    this.canceling.add(id)
    try {
      const result = await this.client.cancel(job.requestId)
      if (result === 'already_finished') {
        this.canceling.delete(id)
        return await this.refresh(id)
      }
      job.status = 'canceled'
      job.stage = '취소됨'
      this.clearNodeProgress(job)
      job.updatedAt = new Date().toISOString()
      await this.changed()
      return job
    } finally { this.canceling.delete(id) }
  }
  async rename(id: string, value: unknown): Promise<VideoJob> {
    const job = this.store.job(id)
    let title: string | undefined
    try { title = normalizeTitle(value) }
    catch (error) { throw fail((error as Error).message) }
    if (title) job.title = title
    else delete job.title
    job.updatedAt = new Date().toISOString()
    await this.changed()
    return job
  }
  async delete(id: string) {
    const job = this.store.job(id)
    if (!terminal(job)) throw fail('진행 중인 작업은 먼저 취소해 주세요.', 409)
    this.store.state.jobs = this.store.state.jobs.filter(item => item.id !== id)
    this.media.delete(id)
    await this.changed()
  }
  async video(id: string): Promise<string> {
    const job = this.store.job(id)
    if (job.status !== 'completed' || !job.requestId) throw fail('완료된 영상만 열 수 있습니다.', 409)
    let ref = this.media.get(id)
    if (!ref) {
      const actual = await this.client.inspect(job.requestId)
      ref = actual.video
      if (!ref) throw fail('엔진에서 결과 파일을 찾을 수 없습니다.', 404)
      this.media.set(id, ref)
    }
    return this.client.videoURL(ref)
  }
}

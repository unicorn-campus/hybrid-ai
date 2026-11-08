import { execFileSync } from 'node:child_process'
import { createServer, type Server } from 'node:http'
import { mkdtemp, readFile, rm, stat } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { Store } from '../src/server/store.js'
import { VideoService } from '../src/server/service.js'
import type { ComfyClient } from '../src/server/comfy.js'
import { probeVideo } from '../src/server/video-media.js'
import type { EngineStatus, GenerationInput } from '../src/shared/types.js'

const engine: EngineStatus = { connected: true, endpoint: 'http://127.0.0.1:8188', modelReady: true,
  turboAvailable: true, extensionAvailable: true, queueRunning: 0, queuePending: 0 }
const cleanups: (() => Promise<void>)[] = []
afterEach(async () => { for (const cleanup of cleanups.splice(0).reverse()) await cleanup() })

function clip(path: string, color: string, seconds: number) {
  execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y',
    '-f', 'lavfi', '-i', `color=c=${color}:s=320x192:r=24:d=${seconds}`,
    '-f', 'lavfi', '-i', `sine=frequency=440:sample_rate=48000:d=${seconds}`,
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', path], { windowsHide: true, timeout: 30_000 })
}

async function setup(segmentAvailable: () => boolean) {
  const root = await mkdtemp(join(tmpdir(), 'videokiwi-extension-'))
  const source = join(root, 'source.mp4')
  const segment = join(root, 'segment.mp4')
  clip(source, 'red', 2)
  clip(segment, 'blue', 141 / 24)
  const server: Server = createServer(async (_req, res) => {
    if (!segmentAvailable()) { res.statusCode = 503; res.end(); return }
    res.setHeader('content-type', 'video/mp4')
    res.end(await readFile(segment))
  })
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
  const port = (server.address() as { port: number }).port
  let submitted: { input: GenerationInput; guide?: string; first?: string; last?: string } | undefined
  const client = {
    health: async () => engine,
    upload: async (_bytes: Uint8Array, name: string) => `videokiwi/${name}`,
    submit: async (input: GenerationInput, _plan: unknown, first?: string, last?: string, guide?: string) => {
      submitted = { input, first, last, guide }
      return 'f9d03f65-5bce-499c-91ed-151c560ebae9'
    },
    inspect: async () => ({ status: 'completed' as const, video: { filename: 'segment.mp4', subfolder: 'video', type: 'output' } }),
    cancel: async () => 'canceled' as const,
    videoURL: () => `http://127.0.0.1:${port}/view`
  }
  const service = new VideoService(new Store(join(root, '.data')), client as unknown as ComfyClient)
  await service.open()
  cleanups.push(async () => {
    service.close(); await service.store.save()
    await new Promise<void>(resolve => server.close(() => resolve()))
    await rm(root, { recursive: true, force: true })
  })
  return { service, source, submitted: () => submitted }
}

async function submitted(service: VideoService, id: string) {
  for (let n = 0; n < 300 && service.store.job(id).status === 'uploading'; n++) await new Promise(resolve => setTimeout(resolve, 10))
}

describe('영상 이어 만들기 서비스', () => {
  it('원본 끝 가이드로 제출하고, 완료 후 겹친 구간을 빼고 원본 뒤에 이어 붙임', async () => {
    const { service, source, submitted: sent } = await setup(() => true)
    const extension = await service.importVideo(await readFile(source), 'my-clip.mp4')
    expect(extension).toMatchObject({ width: 320, height: 192, guideFrames: 22, fps: 24 })

    const job = await service.create({ mode: 'image', prompt: '고양이가 창가에서 걸어 나갑니다.', duration: 5,
      resolution: 'preview', aspectRatio: 'auto', camera: 'none', profile: 'balanced', seed: 7, optimize: false,
      extensionSourceId: extension.id })
    await submitted(service, job.id)
    expect(job.status).toBe('queued')
    expect(sent()?.guide).toMatch(/\.mp4$/)
    expect(sent()?.first).toBeUndefined()
    expect(job.plan).toMatchObject({ width: 320, height: 192, frames: 141 })

    await service.refresh(job.id)
    expect(job.status).toBe('completed')
    expect(job.localPath).toMatch(/\.extended\.mp4$/)
    const joined = await probeVideo(job.localPath!)
    // 48 source frames + (141 generated - 22 overlapping guide frames)
    expect(joined.frames).toBeGreaterThanOrEqual(166)
    expect(joined.frames).toBeLessThanOrEqual(168)
    expect(joined).toMatchObject({ width: 320, height: 192, hasAudio: true })
    expect(job.extension?.totalDuration).toBeCloseTo(167 / 24, 1)
    expect(job.extension?.addedDuration).toBeCloseTo(119 / 24, 1)
    await expect(service.localVideo(job.id)).resolves.toBe(job.localPath)
  })

  it('이어 붙이기에 실패하면 완료로 표시하지 않고, 다시 확인하면 이어 붙이기만 재시도함', async () => {
    let available = false
    const { service, source } = await setup(() => available)
    const extension = await service.importVideo(await readFile(source), 'retry.mp4')
    const job = await service.create({ mode: 'image', prompt: '같은 방향으로 계속 달립니다.', duration: 5,
      resolution: 'preview', aspectRatio: 'auto', camera: 'none', profile: 'balanced', seed: 7, optimize: false,
      extensionSourceId: extension.id })
    await submitted(service, job.id)
    await service.refresh(job.id)
    expect(job.status).toBe('interrupted')
    expect(job.error).toContain('이어 붙이지 못했습니다')
    expect(job.localPath).toBeUndefined()

    available = true
    await service.refresh(job.id)
    expect(job.status).toBe('completed')
    expect(job.error).toBeUndefined()
    expect((await stat(job.localPath!)).size).toBeGreaterThan(0)
  })

  it('완료된 이어 만들기 결과를 다시 원본으로 골라 연속 확장할 수 있음', async () => {
    const { service, source } = await setup(() => true)
    const extension = await service.importVideo(await readFile(source), 'chain.mp4')
    const job = await service.create({ mode: 'image', prompt: '카메라가 계속 앞으로 갑니다.', duration: 5,
      resolution: 'preview', aspectRatio: 'auto', camera: 'none', profile: 'balanced', seed: 7, optimize: false,
      extensionSourceId: extension.id })
    await submitted(service, job.id)
    await service.refresh(job.id)
    const next = await service.prepareExtension(job.id)
    expect(next.sourceJobId).toBe(job.id)
    expect(next.duration).toBeCloseTo(167 / 24, 1)
  })
})

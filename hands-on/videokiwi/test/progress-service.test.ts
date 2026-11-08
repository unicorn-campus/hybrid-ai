import { afterEach, describe, expect, it } from 'vitest'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Store } from '../src/server/store.js'
import { VideoService } from '../src/server/service.js'
import type { ComfyClient } from '../src/server/comfy.js'
import type { EngineProgress, EngineStatus, GenerationInput } from '../src/shared/types.js'

const promptId = 'f9d03f65-5bce-499c-91ed-151c560ebae9'
const otherPromptId = 'a7e79960-c823-4b1e-87d7-f50092eb68cc'
const input: GenerationInput = {
  mode: 'text',
  prompt: 'A bird flies above the clouds.',
  duration: 5,
  resolution: 'preview',
  aspectRatio: '16:9',
  camera: 'none',
  profile: 'fast',
  seed: 42,
  optimize: false
}
const engine: EngineStatus = {
  connected: true,
  endpoint: 'http://127.0.0.1:8188',
  modelReady: true,
  turboAvailable: true,
  queueRunning: 0,
  queuePending: 0
}

type InspectStatus = 'queued' | 'in_progress' | 'completed'

function progressClient() {
  const listeners = new Set<(progress: EngineProgress) => void>()
  const cache = new Map<string, EngineProgress>()
  const tracked: string[] = []
  let inspectStatus: InspectStatus = 'queued'
  let connected = 0
  let closed = 0
  let unsubscribed = 0
  let submitCache: EngineProgress | undefined
  const client = {
    health: async () => engine,
    upload: async () => 'videokiwi/upload.png',
    submit: async () => {
      if (submitCache) cache.set(promptId, submitCache)
      return promptId
    },
    inspect: async () => inspectStatus === 'completed'
      ? {
          status: 'completed' as const,
          video: { filename: 'sample.mp4', subfolder: 'video', type: 'output' }
        }
      : { status: inspectStatus },
    cancel: async () => 'canceled' as const,
    videoURL: () => 'http://127.0.0.1:8188/view?filename=sample.mp4',
    trackProgress: (id: string) => { tracked.push(id) },
    connectProgress: async () => { connected++ },
    onProgress: (callback: (progress: EngineProgress) => void) => {
      listeners.add(callback)
      return () => { listeners.delete(callback); unsubscribed++ }
    },
    getProgress: (id: string) => cache.get(id),
    closeProgress: () => { closed++ }
  }
  return {
    client: client as unknown as ComfyClient,
    tracked,
    connected: () => connected,
    closed: () => closed,
    unsubscribed: () => unsubscribed,
    setInspect: (status: InspectStatus) => { inspectStatus = status },
    setSubmitCache: (progress: EngineProgress) => { submitCache = progress },
    emit: (progress: EngineProgress) => {
      cache.set(progress.promptId, progress)
      for (const listener of listeners) listener(progress)
    }
  }
}

const cleanups: (() => Promise<void>)[] = []

async function fixture() {
  const temporary = await mkdtemp(join(tmpdir(), 'videokiwi-progress-'))
  const directory = join(temporary, '.data')
  const progress = progressClient()
  const service = new VideoService(new Store(directory), progress.client)
  await service.open()
  cleanups.push(async () => {
    service.close()
    await service.store.save()
    await rm(temporary, { recursive: true, force: true })
  })
  return { service, directory, progress }
}

async function submitted(service: VideoService) {
  const job = await service.create(input)
  for (let attempt = 0; attempt < 100 && !job.requestId; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 5))
  }
  expect(job.requestId).toBe(promptId)
  return job
}

async function delivered() {
  await new Promise(resolve => setTimeout(resolve, 10))
}

const event = (
  kind: EngineProgress['kind'],
  stage: string,
  offset: number,
  overrides: Partial<EngineProgress> = {}
): EngineProgress => ({
  promptId,
  kind,
  stage,
  connected: kind !== 'disconnected',
  updatedAt: new Date(Date.UTC(2026, 10, 9, 0, 0, offset)).toISOString(),
  ...overrides
})

afterEach(async () => {
  for (const cleanup of cleanups.splice(0).reverse()) await cleanup()
})

describe('ComfyUI 진행 이벤트 서비스 연결', () => {
  it('정확한 작업만 실행 상태로 바꾸고 실제 단계 수치와 노드 전환을 SSE 상태로 전달한다', async () => {
    const { service, progress } = await fixture()
    const job = await submitted(service)
    let jobEvents = 0
    service.on('jobs', () => { jobEvents++ })

    progress.emit(event('sampling', '샘플링 중', 1, {
      promptId: otherPromptId,
      node: '10',
      percent: 37.5,
      value: 3,
      max: 8
    }))
    await delivered()
    expect(job.status).toBe('queued')
    expect(job.progress).toBeUndefined()

    progress.emit(event('node', '텍스트와 이미지 인코딩 중', 2, { node: '5' }))
    await delivered()
    expect(job.status).toBe('in_progress')
    expect(job.stage).toBe('텍스트와 이미지 인코딩 중')
    expect(job.progressKind).toBe('node')
    expect(job.progress).toBeUndefined()

    progress.emit(event('sampling', '영상과 소리 샘플링 중', 3, {
      node: '10',
      percent: 37.5,
      value: 3,
      max: 8
    }))
    await delivered()
    expect(job).toMatchObject({
      progress: 37.5,
      progressKind: 'sampling',
      progressNode: '10',
      progressValue: 3,
      progressMax: 8,
      progressConnected: true
    })

    progress.emit(event('decode', '영상 복원 중', 4, { node: '11' }))
    await delivered()
    expect(job.stage).toBe('영상 복원 중')
    expect(job.progressKind).toBe('node')
    expect(job.progressNode).toBe('11')
    expect(job.progress).toBeUndefined()
    expect(job.progressValue).toBeUndefined()
    expect(job.progressMax).toBeUndefined()

    progress.setInspect('in_progress')
    await service.refresh(job.id)
    expect(job.stage).toBe('영상 복원 중')
    expect(jobEvents).toBeGreaterThanOrEqual(3)
  })

  it('연결 해제는 수치를 비우되 실패로 확정하지 않고 HTTP 확인을 계속한다', async () => {
    const { service, progress } = await fixture()
    const job = await submitted(service)
    progress.emit(event('sampling', '샘플링 중', 1, {
      node: '10',
      percent: 100,
      value: 8,
      max: 8
    }))
    await delivered()

    progress.emit(event('disconnected', '진행 정보 재연결 대기', 2))
    await delivered()
    expect(job.status).toBe('in_progress')
    expect(job.progressConnected).toBe(false)
    expect(job.progress).toBeUndefined()
    expect(job.progressKind).toBeUndefined()
    expect(job.progressValue).toBeUndefined()

    progress.setInspect('in_progress')
    await service.refresh(job.id)
    expect(job.status).toBe('in_progress')
    expect(job.stage).toBe('진행 정보 재연결 대기')
  })

  it('100%나 complete 이벤트만으로 완료하지 않고 history 완료 기록에서 확정한다', async () => {
    const { service, progress } = await fixture()
    const job = await submitted(service)
    progress.emit(event('sampling', '샘플링 중', 1, {
      node: '10',
      percent: 100,
      value: 8,
      max: 8
    }))
    await delivered()
    expect(job.status).toBe('in_progress')

    progress.emit(event('complete', '완료 기록 확인 중', 2))
    await delivered()
    expect(job.status).toBe('in_progress')
    expect(job.progress).toBeUndefined()
    expect(job.progressKind).toBeUndefined()

    progress.setInspect('completed')
    await service.refresh(job.id)
    expect(job.status).toBe('completed')
    expect(job.stage).toBe('완료')
    expect(job.progress).toBe(100)
    expect(job.progressKind).toBeUndefined()
    expect(job.progressValue).toBeUndefined()
    expect(job.progressMax).toBeUndefined()
  })

  it('제출 응답 직후 캐시된 이벤트를 읽어 초기 진행 상태 유실을 막는다', async () => {
    const { service, progress } = await fixture()
    progress.setSubmitCache(event('sampling', '샘플링 시작', 1, {
      node: '10',
      percent: 12.5,
      value: 1,
      max: 8
    }))
    const job = await submitted(service)
    expect(progress.tracked).toContain(promptId)
    expect(job).toMatchObject({
      status: 'in_progress',
      stage: '샘플링 시작',
      progress: 12.5,
      progressValue: 1,
      progressMax: 8
    })
  })

  it('오래된 이벤트가 새 진행 단계를 되돌리지 않는다', async () => {
    const { service, progress } = await fixture()
    const job = await submitted(service)
    progress.emit(event('node', '영상 복원 중', 5, { node: '11' }))
    await delivered()
    progress.emit(event('sampling', '이전 샘플링 단계', 4, {
      node: '10',
      percent: 50,
      value: 4,
      max: 8
    }))
    await delivered()
    expect(job.stage).toBe('영상 복원 중')
    expect(job.progressKind).toBe('node')
  })

  it('서버 재시작 시 저장된 활성 작업을 다시 추적하고 종료 시 구독을 정리한다', async () => {
    const { service, directory } = await fixture()
    service.store.state.jobs.push({
      id: 'restored-job',
      requestId: promptId,
      input,
      status: 'in_progress',
      stage: '영상과 소리 생성',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    })
    await service.store.save()
    service.close()

    const nextProgress = progressClient()
    const reopened = new VideoService(new Store(directory), nextProgress.client)
    await reopened.open()
    expect(nextProgress.tracked).toContain(promptId)
    expect(nextProgress.connected()).toBe(1)
    reopened.close()
    expect(nextProgress.unsubscribed()).toBe(1)
    expect(nextProgress.closed()).toBe(1)
  })
})

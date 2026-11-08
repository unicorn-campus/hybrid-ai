import { afterEach, describe, expect, it } from 'vitest'
import { mkdtemp, rm, readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { Server } from 'node:http'
import sharp from 'sharp'
import { Store } from '../src/server/store.js'
import { VideoService } from '../src/server/service.js'
import { createApp } from '../src/server/app.js'
import type { ComfyClient } from '../src/server/comfy.js'
import type { GenerationInput, EngineStatus } from '../src/shared/types.js'

const input: GenerationInput = { mode: 'text', prompt: 'A small cat slowly turns its head beside a window.',
  duration: 5, resolution: 'preview', aspectRatio: '16:9', camera: 'static', profile: 'balanced', seed: 42, optimize: true }
const engine: EngineStatus = { connected: true, endpoint: 'http://127.0.0.1:8188', modelReady: true,
  turboAvailable: true, queueRunning: 0, queuePending: 0, vramTotalMB: 16376 }
const cleanups: (() => Promise<void>)[] = []
async function setup(options: { busy?: boolean; submitError?: boolean } = {}) {
  const temporary = await mkdtemp(join(tmpdir(), 'videokiwi-test-'))
  const directory = join(temporary, '.data')
  let calls = 0, submitted: GenerationInput | undefined
  const client = {
    health: async () => ({ ...engine, queueRunning: options.busy ? 1 : 0 }),
    upload: async () => 'videokiwi/upload.png',
    submit: async (value: GenerationInput) => {
      calls++; submitted = value
      if (options.submitError) throw new Error('제출 응답 시간 초과')
      return 'f9d03f65-5bce-499c-91ed-151c560ebae9'
    },
    inspect: async () => ({ status: 'completed' as const, video: { filename: 'sample.mp4', subfolder: 'video', type: 'output' } }),
    cancel: async () => 'canceled' as const,
    videoURL: () => 'http://127.0.0.1:8188/view?filename=sample.mp4'
  }
  const service = new VideoService(new Store(directory), client as unknown as ComfyClient)
  await service.open()
  cleanups.push(async () => { service.close(); await service.store.save(); await rm(temporary, { recursive: true, force: true }) })
  return { service, directory, client, calls: () => calls, submitted: () => submitted }
}
async function settled(service: VideoService, id: string) {
  for (let n = 0; n < 100 && service.store.job(id).status === 'uploading'; n++) await new Promise(resolve => setTimeout(resolve, 10))
}
afterEach(async () => { for (const cleanup of cleanups.splice(0).reverse()) await cleanup() })

describe('로컬 H3 실행 서비스', () => {
  it('개선 프롬프트를 실제 제출하고 원문, 설정, 시간을 보존한다', async () => {
    const { service, submitted, directory, calls } = await setup()
    const job = await service.create(input)
    await settled(service, job.id)
    expect(calls()).toBe(1)
    expect(submitted()?.prompt).toContain(input.prompt)
    expect(submitted()?.prompt.length).toBeGreaterThan(input.prompt.length)
    expect(job.input.originalPrompt).toBe(input.prompt)
    await service.refresh(job.id)
    expect(job.status).toBe('completed')
    expect(job.videoUrl).toContain(job.id)
    expect(job.plan?.frames).toBe(124)
    const persisted = JSON.parse(await readFile(join(directory, 'state.json'), 'utf8'))
    expect(persisted.jobs[0].requestId).toBe(job.requestId)
    expect(persisted.jobs[0].optimization.method).toBe('local-rules')
  })
  it('다른 ComfyUI 작업이 진행 중이면 제출하지 않는다', async () => {
    const { service, calls } = await setup({ busy: true })
    await expect(service.create(input)).rejects.toThrow(/다른 작업/)
    expect(calls()).toBe(0)
    expect(service.store.jobs()).toHaveLength(0)
  })
  it('사용자가 검토하고 수정한 최종 문장을 다시 작성하지 않는다', async () => {
    const { service, submitted } = await setup()
    const reviewed = 'My reviewed final prompt. Keep this exact camera direction.'
    const job = await service.create({ ...input, prompt: reviewed, originalPrompt: input.prompt, optimize: false })
    await settled(service, job.id)
    expect(submitted()?.prompt).toContain(reviewed)
    expect(submitted()?.prompt).toContain('overall_soundscape:')
    expect(job.input.originalPrompt).toBe(input.prompt)
  })
  it('Claude 제안 오류를 규칙 기반 성공으로 바꾸지 않는다', async () => {
    const { service, client, directory } = await setup()
    const withClaude = new VideoService(new Store(directory), client as unknown as ComfyClient, {
      status: async () => ({ provider: 'claude-agent-sdk', model: 'sonnet', authentication: 'claude-subscription', available: true }),
      optimize: async () => { throw new Error('Claude 사용 한도에 도달했습니다.') }
    })
    await withClaude.open()
    try {
      await expect(withClaude.optimize(input)).rejects.toThrow('Claude 사용 한도')
      await expect(withClaude.create(input)).rejects.toThrow('Claude 사용 한도')
      expect(service.store.jobs()).toHaveLength(0)
    } finally { withClaude.close() }
  })
  it('더블 클릭으로 두 작업을 제출하지 않는다', async () => {
    const { service, calls } = await setup()
    const responses = await Promise.allSettled([service.create(input), service.create(input)])
    expect(responses.filter(item => item.status === 'fulfilled')).toHaveLength(1)
    const job = service.store.jobs()[0]
    await settled(service, job.id)
    expect(calls()).toBe(1)
  })
  it('제출 응답이 유실되어도 자동 재제출하지 않는다', async () => {
    const { service, calls } = await setup({ submitError: true })
    const job = await service.create(input)
    await settled(service, job.id)
    await service.poll()
    expect(calls()).toBe(1)
    expect(job.status).toBe('interrupted')
    expect(job.error).toContain('자동 재제출하지 않습니다')
  })
  it('연결 장애를 생성 실패로 확정하지 않고 ID로 재연결한다', async () => {
    const { service, client } = await setup()
    const job = await service.create(input)
    await settled(service, job.id)
    const original = client.inspect
    client.inspect = async () => { throw new Error('엔진 연결 실패') }
    await service.refresh(job.id)
    expect(job.status).toBe('queued')
    expect(job.stage).toContain('재연결')
    client.inspect = original
    await service.refresh(job.id)
    expect(job.status).toBe('completed')
  })
  it('이미지 파일을 검사하고 크기, 밝기, 색을 로컬에서 측정한다', async () => {
    const { service } = await setup()
    const bytes = await sharp({ create: { width: 100, height: 70, channels: 3, background: '#ff0000' } }).png().toBuffer()
    const image = await service.importImage(bytes, '../a.png')
    expect(image.width).toBe(100)
    expect(image.height).toBe(70)
    expect(image.brightness).toBeGreaterThan(0)
    expect(image.name).not.toContain('/')
    expect(image).not.toHaveProperty('file')
    await expect(service.importImage(Buffer.from('<script>bad</script>'), 'bad.png')).rejects.toThrow(/정지 이미지/)
  })
  it('재시작 시 미확정 제출을 자동 실행하지 않는다', async () => {
    const { service, directory, client, calls } = await setup()
    service.store.state.jobs.push({ id: 'interrupted-id', input, status: 'uploading', createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() })
    await service.store.save()
    const reopened = new VideoService(new Store(directory), client as unknown as ComfyClient)
    await reopened.open()
    reopened.close()
    expect(reopened.store.job('interrupted-id').status).toBe('interrupted')
    expect(calls()).toBe(0)
  })
})

describe('웹 API 경계', () => {
  async function web() {
    const fixture = await setup()
    const app = createApp(fixture.service)
    const server = await new Promise<Server>(resolve => {
      const server = app.listen(0, '127.0.0.1', () => resolve(server))
    })
    cleanups.push(() => new Promise<void>(resolve => { server.closeAllConnections(); server.close(() => resolve()) }))
    const address = server.address() as { port: number }
    return { ...fixture, url: `http://127.0.0.1:${address.port}` }
  }
  it('외부 Origin에서 생성을 요청할 수 없고 알려지지 않은 API는 JSON 404를 준다', async () => {
    const { url, calls } = await web()
    const refused = await fetch(`${url}/api/jobs`, { method: 'POST', headers: { Origin: 'https://unrelated.example', 'Content-Type': 'application/json' }, body: JSON.stringify(input) })
    expect(refused.status).toBe(403)
    expect(calls()).toBe(0)
    const missing = await fetch(`${url}/api/missing`)
    expect(missing.status).toBe(404)
    expect(await missing.json()).toHaveProperty('error')
  })
  it('업로드부터 최적화, 제출, 상태, 레시피 다운로드까지 연결한다', async () => {
    const { url, service } = await web()
    const bytes = await sharp({ create: { width: 128, height: 72, channels: 3, background: '#327f42' } }).png().toBuffer()
    const form = new FormData()
    form.append('image', new Blob([new Uint8Array(bytes)]), 'scene.png')
    const upload = await fetch(`${url}/api/images`, { method: 'POST', body: form })
    expect(upload.status).toBe(201)
    const image = await upload.json()
    const imageInput = { ...input, mode: 'image', imageId: image.id }
    const optimize = await fetch(`${url}/api/prompt/optimize`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(imageInput) })
    expect((await optimize.json()).method).toBe('local-rules')
    const create = await fetch(`${url}/api/jobs`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(imageInput) })
    expect(create.status).toBe(202)
    const job = await create.json()
    await settled(service, job.id)
    await service.refresh(job.id)
    const recipe = await fetch(`${url}/api/jobs/${job.id}/recipe`)
    expect(recipe.headers.get('content-disposition')).toContain('attachment')
    expect((await recipe.json()).input.originalPrompt).toBe(input.prompt)
    const preview = await fetch(`${url}${image.previewUrl}`)
    expect(preview.status).toBe(200)
    expect(preview.headers.get('content-type')).toContain('image/png')
    expect(new Uint8Array(await preview.arrayBuffer()).slice(0, 4)).toEqual(new Uint8Array([137, 80, 78, 71]))
  })
  it('제목은 기록에만 저장하고 엔진 입력에는 넣지 않으며, 나중에 고치거나 지울 수 있다', async () => {
    const { url, service, submitted } = await web()
    const create = await fetch(`${url}/api/jobs`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...input, title: '  창가   고양이\n첫 시도 ' }) })
    const job = await create.json()
    await settled(service, job.id)
    expect(job.title).toBe('창가 고양이 첫 시도')
    expect(job.input.title).toBeUndefined()
    expect(submitted()?.title).toBeUndefined()
    expect(JSON.stringify(submitted())).not.toContain('창가 고양이')

    const renamed = await fetch(`${url}/api/jobs/${job.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: '최종: 고양이/산책?' }) })
    expect(renamed.status).toBe(200)
    expect((await renamed.json()).title).toBe('최종: 고양이/산책?')
    const recipe = await fetch(`${url}/api/jobs/${job.id}/recipe`)
    const disposition = decodeURIComponent(recipe.headers.get('content-disposition') || '')
    expect(disposition).toContain(`최종 고양이 산책-${job.id.slice(0, 8)}.json`)
    expect((await recipe.json()).title).toBe('최종: 고양이/산책?')

    const tooLong = await fetch(`${url}/api/jobs/${job.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: '가'.repeat(61) }) })
    expect(tooLong.status).toBe(400)
    expect((await tooLong.json()).error).toContain('60자')

    const cleared = await fetch(`${url}/api/jobs/${job.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: '   ' }) })
    expect((await cleared.json()).title).toBeUndefined()
    const fallback = await fetch(`${url}/api/jobs/${job.id}/recipe`)
    expect(fallback.headers.get('content-disposition')).toContain(`videokiwi-${job.id.slice(0, 8)}.json`)
    const persisted = JSON.parse(await readFile(join(service.store.directory, 'state.json'), 'utf8'))
    expect(persisted.jobs[0].title).toBeUndefined()
  })
})

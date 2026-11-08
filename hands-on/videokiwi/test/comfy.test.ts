import { describe, expect, it, vi } from 'vitest'
import { ComfyClient } from '../src/server/comfy.js'
import type { WebSocketFactory, WebSocketLike } from '../src/server/comfy-progress.js'
import type { ExecutionPlan, GenerationInput } from '../src/shared/types.js'

const PROMPT_ID = '11111111-1111-4111-8111-111111111111'

function openSocketFactory(urls: string[] = []): WebSocketFactory {
  return (url) => {
    urls.push(url)
    const listeners = new Map<string, Array<(event: Event) => void>>()
    const socket: WebSocketLike = {
      readyState: 0,
      addEventListener(type, listener) {
        const values = listeners.get(type) ?? []
        values.push(listener as (event: Event) => void)
        listeners.set(type, values)
      },
      close() {}
    }
    queueMicrotask(() => {
      Object.defineProperty(socket, 'readyState', { value: 1 })
      for (const listener of listeners.get('open') ?? []) listener(new Event('open'))
    })
    return socket
  }
}

function response(value: unknown, status = 200): Response {
  return new Response(value === undefined ? null : JSON.stringify(value), {
    status, headers: { 'content-type': 'application/json' }
  })
}

function input(overrides: Partial<GenerationInput> = {}): GenerationInput {
  return {
    mode: 'text', prompt: 'A kiwi bird walks through soft morning light.', duration: 5,
    resolution: 'preview', aspectRatio: '16:9', camera: 'push-in', profile: 'quality',
    seed: 42, ...overrides
  }
}

function plan(overrides: Partial<ExecutionPlan> = {}): ExecutionPlan {
  return {
    width: 640, height: 352, frames: 124, fps: 24, steps: 20,
    sampler: 'res_multistep', turbo: false, actualDuration: 124 / 24, warnings: [], ...overrides
  }
}

describe('ComfyClient', () => {
  it('텍스트, 시작 이미지와 끝 이미지를 기본 워크플로에 연결함', async () => {
    let submitted: Record<string, unknown> | undefined
    const socketUrls: string[] = []
    const fake = vi.fn(async (url: URL | RequestInfo, init?: RequestInit) => {
      expect(new URL(String(url)).pathname).toBe('/prompt')
      submitted = JSON.parse(String(init?.body)) as Record<string, unknown>
      return response({ prompt_id: PROMPT_ID })
    }) as unknown as typeof fetch
    const client = new ComfyClient({
      baseUrl: 'http://127.0.0.1:8188', fetch: fake, clientId: 'videokiwi-client',
      webSocketFactory: openSocketFactory(socketUrls)
    })
    await expect(client.submit(input({ mode: 'image' }), plan({ steps: 30 }), 'first.png', 'last.png')).resolves.toBe(PROMPT_ID)
    const workflow = submitted?.prompt as Record<string, { class_type: string; inputs: Record<string, unknown> }>
    expect(workflow['5'].inputs).toMatchObject({ width: 640, height: 352, length: 124, first_frame: ['15', 0], last_frame: ['16', 0] })
    expect(workflow['5'].inputs.prompt).toBe('A kiwi bird walks through soft morning light.')
    expect(workflow['9'].inputs.steps).toBe(30)
    expect(workflow['15']).toEqual({ class_type: 'LoadImage', inputs: { image: 'first.png' } })
    expect(workflow['16']).toEqual({ class_type: 'LoadImage', inputs: { image: 'last.png' } })
    expect((submitted?.extra_data as Record<string, unknown>).videokiwi).toEqual({ version: 1 })
    expect(submitted?.client_id).toBe('videokiwi-client')
    expect(submitted?.prompt_id).toMatch(/^[0-9a-f-]{36}$/)
    expect(socketUrls).toEqual(['ws://127.0.0.1:8188/ws?clientId=videokiwi-client'])
    client.closeProgress()
  })

  it('빠른 워크플로는 LoRA, SigmaShift, Euler 8단계를 유지함', async () => {
    let workflow: Record<string, { class_type: string; inputs: Record<string, unknown> }> = {}
    const fake = vi.fn(async (_url: URL | RequestInfo, init?: RequestInit) => {
      workflow = (JSON.parse(String(init?.body)) as { prompt: typeof workflow }).prompt
      return response({ prompt_id: PROMPT_ID })
    }) as unknown as typeof fetch
    const client = new ComfyClient({ fetch: fake, webSocketFactory: openSocketFactory() })
    await client.submit(input({ mode: 'image', profile: 'fast' }), plan({ turbo: true, steps: 8, sampler: 'euler' }), 'first.png')
    expect(workflow['15'].class_type).toBe('LoraLoaderModelOnly')
    expect(workflow['16']).toMatchObject({ class_type: 'MiniMaxH3SigmaShift', inputs: { shift_video: 12, shift_audio: 3 } })
    expect(workflow['8'].inputs.sampler_name).toBe('euler')
    expect(workflow['9'].inputs.steps).toBe(8)
    expect(workflow['17']).toEqual({ class_type: 'LoadImage', inputs: { image: 'first.png' } })
    client.closeProgress()
  })

  it('원본 끝의 가이드 영상을 새 영상 첫 구간에 연결함', async () => {
    let workflow: Record<string, { class_type: string; inputs: Record<string, unknown> }> = {}
    const fake = vi.fn(async (_url: URL | RequestInfo, init?: RequestInit) => {
      workflow = (JSON.parse(String(init?.body)) as { prompt: typeof workflow }).prompt
      return response({ prompt_id: PROMPT_ID })
    }) as unknown as typeof fetch
    const client = new ComfyClient({ fetch: fake, webSocketFactory: openSocketFactory() })
    await client.submit(
      input({ mode: 'image', extensionSourceId: 'source-1' }),
      plan({ frames: 141, actualDuration: 141 / 24 }), undefined, undefined, 'guide.mp4'
    )
    expect(workflow['30']).toEqual({ class_type: 'LoadVideo', inputs: { file: 'guide.mp4' } })
    expect(workflow['31']).toEqual({ class_type: 'GetVideoComponents', inputs: { video: ['30', 0] } })
    expect(workflow['32']).toEqual({
      class_type: 'MiniMaxH3AddGuide',
      inputs: {
        positive: ['5', 0], latent: ['5', 1], frame_idx: 0, vae: ['3', 0], image: ['31', 0],
        audio_vae: ['4', 0], audio: ['31', 1]
      }
    })
    expect(workflow['7'].inputs.conditioning).toEqual(['32', 0])
    expect(workflow['10'].inputs.latent_image).toEqual(['5', 1])
    expect(workflow['5'].inputs.first_frame).toBeUndefined()
    client.closeProgress()
  })

  it('영상 확장에 끝 장면을 함께 지정하면 끝 키프레임과 가이드를 모두 연결함', async () => {
    let workflow: Record<string, { class_type: string; inputs: Record<string, unknown> }> = {}
    const fake = vi.fn(async (_url: URL | RequestInfo, init?: RequestInit) => {
      workflow = (JSON.parse(String(init?.body)) as { prompt: typeof workflow }).prompt
      return response({ prompt_id: PROMPT_ID })
    }) as unknown as typeof fetch
    const client = new ComfyClient({ fetch: fake, webSocketFactory: openSocketFactory() })
    await client.submit(
      input({ mode: 'image', extensionSourceId: 'source-1', endImageId: 'end-1' }),
      plan({ frames: 141, actualDuration: 141 / 24 }), undefined, 'end.png', 'guide.mp4'
    )
    const lastFrame = workflow['5'].inputs.last_frame as [string, number]
    expect(workflow[lastFrame[0]]).toEqual({ class_type: 'LoadImage', inputs: { image: 'end.png' } })
    expect(workflow['32'].inputs.positive).toEqual(['5', 0])
    expect(workflow['7'].inputs.conditioning).toEqual(['32', 0])
    await expect(client.submit(
      input({ mode: 'image', extensionSourceId: 'source-1' }), plan(), 'start.png', undefined, 'guide.mp4'
    )).rejects.toThrow('시작 이미지')
    client.closeProgress()
  })

  it('업로드 결과의 하위 폴더와 파일명을 LoadImage 값으로 반환함', async () => {
    const fake = vi.fn(async () => response({ name: 'kiwi.png', subfolder: 'VideoKiwi', type: 'input' })) as unknown as typeof fetch
    const client = new ComfyClient({ fetch: fake })
    await expect(client.upload(new Uint8Array([1, 2, 3]), 'kiwi.png')).resolves.toBe('VideoKiwi/kiwi.png')
  })

  it('완료 기록에서 SaveVideo의 MP4를 찾고 보기 URL을 만듦', async () => {
    const fake = vi.fn(async () => response({
      [PROMPT_ID]: { status: { status_str: 'success', completed: true }, outputs: {
        '14': { images: [{ filename: 'VideoKiwi_1.mp4', subfolder: 'video', type: 'output' }] }
      } }
    })) as unknown as typeof fetch
    const client = new ComfyClient({ fetch: fake })
    const result = await client.inspect(PROMPT_ID)
    expect(result.status).toBe('completed')
    expect(client.videoURL(result.video!)).toBe('http://127.0.0.1:8188/view?filename=VideoKiwi_1.mp4&subfolder=video&type=output')
  })

  it('다른 실행 작업은 중단하지 않음', async () => {
    const other = '22222222-2222-4222-8222-222222222222'
    const fake = vi.fn(async (url: URL | RequestInfo) => {
      const path = new URL(String(url)).pathname
      if (path === '/queue') return response({ queue_running: [[1, other]], queue_pending: [] })
      throw new Error(`unexpected write ${path}`)
    }) as unknown as typeof fetch
    const client = new ComfyClient({ fetch: fake })
    await expect(client.cancel(PROMPT_ID)).resolves.toBe('already_finished')
    expect(fake).toHaveBeenCalledTimes(1)
  })

  it('대기 작업만 ID로 삭제하고 실행 작업은 ID를 넣어 중단함', async () => {
    let queueCalls = 0
    const calls: string[] = []
    const fake = vi.fn(async (url: URL | RequestInfo, init?: RequestInit) => {
      const path = new URL(String(url)).pathname
      calls.push(`${init?.method ?? 'GET'} ${path} ${String(init?.body ?? '')}`)
      if (path === '/queue' && !init?.method) {
        queueCalls += 1
        return response(queueCalls === 1 ? { queue_running: [], queue_pending: [[2, PROMPT_ID]] } : { queue_running: [], queue_pending: [] })
      }
      if (path === '/queue' && init?.method === 'POST') return response(undefined)
      throw new Error(`unexpected ${path}`)
    }) as unknown as typeof fetch
    const client = new ComfyClient({ fetch: fake })
    await expect(client.cancel(PROMPT_ID)).resolves.toBe('canceled')
    expect(calls.some(call => call.includes(`"delete":["${PROMPT_ID}"]`))).toBe(true)
    expect(calls.some(call => call.includes('/interrupt'))).toBe(false)
  })

  it('HTTP 오류와 응답 시간 초과를 쉬운 오류로 바꿈', async () => {
    const failed = new ComfyClient({ fetch: vi.fn(async () => response({ error: 'busy' }, 503)) as unknown as typeof fetch })
    await expect(failed.queue()).rejects.toThrow('ComfyUI 요청 실패 (503)')
    const timeoutFetch = vi.fn(async (_url: URL | RequestInfo, init?: RequestInit) => await new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
    })) as unknown as typeof fetch
    const timed = new ComfyClient({ fetch: timeoutFetch })
    vi.useFakeTimers()
    const pending = timed.queue()
    const assertion = expect(pending).rejects.toThrow('응답 시간이 초과')
    await vi.advanceTimersByTimeAsync(10_001)
    await assertion
    vi.useRealTimers()
  })

  it('외부 호스트를 ComfyUI 주소로 허용하지 않음', () => {
    expect(() => new ComfyClient({ baseUrl: 'https://example.com' })).toThrow('루프백')
  })
})

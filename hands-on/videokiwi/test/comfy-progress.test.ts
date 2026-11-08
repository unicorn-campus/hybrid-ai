import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ComfyProgressTracker,
  type WebSocketFactory,
  type WebSocketLike
} from '../src/server/comfy-progress.js'
import type { EngineProgress } from '../src/shared/types.js'

const PROMPT_ID = '11111111-1111-4111-8111-111111111111'
const OTHER_ID = '22222222-2222-4222-8222-222222222222'

class FakeSocket implements WebSocketLike {
  readyState = 0
  private closed = false
  private readonly listeners = new Map<string, Array<(event: Event | MessageEvent) => void>>()

  constructor(readonly url: string) {}

  addEventListener(type: 'open' | 'message' | 'error' | 'close', listener: (event: Event | MessageEvent) => void): void {
    const values = this.listeners.get(type) ?? []
    values.push(listener)
    this.listeners.set(type, values)
  }

  open(): void {
    this.readyState = 1
    this.emit('open', new Event('open'))
  }

  message(value: unknown): void {
    this.emit('message', { data: value } as MessageEvent)
  }

  serverClose(): void {
    this.close()
  }

  close(): void {
    if (this.closed) return
    this.closed = true
    this.readyState = 3
    this.emit('close', new Event('close'))
  }

  private emit(type: string, event: Event | MessageEvent): void {
    for (const listener of this.listeners.get(type) ?? []) listener(event)
  }
}

function sockets(): { values: FakeSocket[]; factory: WebSocketFactory } {
  const values: FakeSocket[] = []
  return {
    values,
    factory: (url) => {
      const socket = new FakeSocket(url)
      values.push(socket)
      return socket
    }
  }
}

async function connectedTracker() {
  const created = sockets()
  const tracker = new ComfyProgressTracker('ws://127.0.0.1:8188/ws?clientId=test', created.factory)
  const connecting = tracker.connect()
  created.values[0].open()
  await connecting
  return { tracker, socket: created.values[0], created }
}

afterEach(() => vi.useRealTimers())

describe('ComfyProgressTracker', () => {
  it('8단계 샘플링의 3단계를 37.5%로 보고함', async () => {
    const { tracker, socket } = await connectedTracker()
    tracker.track(PROMPT_ID)
    const events: EngineProgress[] = []
    tracker.on((event) => events.push(event))

    socket.message(JSON.stringify({
      type: 'progress', data: { prompt_id: PROMPT_ID, node: '10', value: 3, max: 8 }
    }))

    expect(events.at(-1)).toMatchObject({
      promptId: PROMPT_ID, stage: '영상과 소리 생성', node: '10', kind: 'sampling',
      value: 3, max: 8, percent: 37.5, connected: true
    })
    expect(tracker.get(PROMPT_ID)?.percent).toBe(37.5)
    tracker.close()
  })

  it('다음 노드로 바뀌면 이전 샘플링 수치를 이어 쓰지 않음', async () => {
    const { tracker, socket } = await connectedTracker()
    tracker.track(PROMPT_ID)
    socket.message(JSON.stringify({
      type: 'progress', data: { prompt_id: PROMPT_ID, node: '10', value: 8, max: 8 }
    }))
    socket.message(JSON.stringify({ type: 'executing', data: { prompt_id: PROMPT_ID, node: '11' } }))

    expect(tracker.get(PROMPT_ID)).toMatchObject({
      stage: '영상 복원', node: '11', kind: 'decode', connected: true
    })
    expect(tracker.get(PROMPT_ID)).not.toHaveProperty('percent')
    expect(tracker.get(PROMPT_ID)).not.toHaveProperty('value')
    expect(tracker.get(PROMPT_ID)).not.toHaveProperty('max')
    tracker.close()
  })

  it('progress_state에서 현재 실행 중인 노드를 선택하고 완료 노드는 제외함', async () => {
    const { tracker, socket } = await connectedTracker()
    tracker.track(PROMPT_ID)
    socket.message(JSON.stringify({ type: 'executing', data: { prompt_id: PROMPT_ID, node: '10' } }))
    socket.message(JSON.stringify({
      type: 'progress_state',
      data: { prompt_id: PROMPT_ID, nodes: { '10': { state: 'running', value: 0, max: 1, node_id: '10' } } }
    }))
    expect(tracker.get(PROMPT_ID)).not.toHaveProperty('percent')
    socket.message(JSON.stringify({
      type: 'progress_state',
      data: {
        prompt_id: PROMPT_ID,
        nodes: {
          '9': { state: 'finished', value: 8, max: 8, node_id: '9' },
          '10': { state: 'running', value: 3, max: 8, node_id: '10' },
          '11': { state: 'running', value: 1, max: 4, node_id: '11' }
        }
      }
    }))

    expect(tracker.get(PROMPT_ID)).toMatchObject({ node: '10', value: 3, max: 8, percent: 37.5 })
    tracker.close()
  })

  it('다른 작업과 잘못된 메시지를 무시하고 ID 없는 executing은 단일 작업에만 귀속함', async () => {
    const { tracker, socket } = await connectedTracker()
    tracker.track(PROMPT_ID)
    const events: EngineProgress[] = []
    tracker.on((event) => events.push(event))

    socket.message(new Uint8Array([1, 2, 3]))
    socket.message('{malformed')
    socket.message(JSON.stringify({ type: 'progress', data: { prompt_id: OTHER_ID, node: '10', value: 3, max: 8 } }))
    socket.message(JSON.stringify({ type: 'progress', data: { prompt_id: PROMPT_ID, node: '10', value: 3, max: 0 } }))
    socket.message(JSON.stringify({ type: 'executing', data: { node: '5' } }))
    expect(events).toHaveLength(1)
    expect(events[0]).toMatchObject({ promptId: PROMPT_ID, node: '5' })

    tracker.track(OTHER_ID)
    socket.message(JSON.stringify({ type: 'executing', data: { node: '10' } }))
    expect(events).toHaveLength(1)
    tracker.close()
  })

  it('연결 종료를 별도 상태로 알리고 1초 뒤 재연결하며 명시적 종료 후에는 재시도하지 않음', async () => {
    vi.useFakeTimers()
    const { tracker, socket, created } = await connectedTracker()
    tracker.track(PROMPT_ID)
    const events: EngineProgress[] = []
    tracker.on((event) => events.push(event))

    socket.serverClose()
    expect(events.at(-1)).toMatchObject({
      promptId: PROMPT_ID, kind: 'disconnected', connected: false, stage: '진행 연결 끊김'
    })
    await vi.advanceTimersByTimeAsync(999)
    expect(created.values).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(created.values).toHaveLength(2)
    created.values[1].open()
    created.values[1].message(JSON.stringify({
      type: 'progress', data: { prompt_id: PROMPT_ID, node: '10', value: 2, max: 8 }
    }))
    socket.message(JSON.stringify({
      type: 'progress', data: { prompt_id: PROMPT_ID, node: '10', value: 7, max: 8 }
    }))
    expect(tracker.get(PROMPT_ID)?.percent).toBe(25)

    tracker.close()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(created.values).toHaveLength(2)
  })

  it('연결은 3초 안에 열리지 않으면 실패하고 재연결은 10회에서 멈춤', async () => {
    vi.useFakeTimers()
    const created = sockets()
    const tracker = new ComfyProgressTracker('ws://127.0.0.1:8188/ws?clientId=test', created.factory)
    const rejected = expect(tracker.connect()).rejects.toThrow('시간이 초과')
    await vi.advanceTimersByTimeAsync(3_001)
    await rejected
    await vi.runAllTimersAsync()
    expect(created.values).toHaveLength(11)
    tracker.close()
  })

  it('연결 중 명시적으로 종료하면 대기와 재연결 타이머를 정리함', async () => {
    vi.useFakeTimers()
    const created = sockets()
    const tracker = new ComfyProgressTracker('ws://127.0.0.1:8188/ws?clientId=test', created.factory)
    const rejected = expect(tracker.connect()).rejects.toThrow('종료')
    tracker.close()
    await rejected
    await vi.advanceTimersByTimeAsync(30_000)
    expect(created.values).toHaveLength(1)
  })

  it('실행 종료 이벤트는 완료 신호만 남기고 HTTP 결과 판정용 상세 상태를 만들지 않음', async () => {
    const { tracker, socket } = await connectedTracker()
    tracker.track(PROMPT_ID)
    socket.message(JSON.stringify({ type: 'executing', data: { prompt_id: PROMPT_ID, node: null } }))
    expect(tracker.get(PROMPT_ID)).toMatchObject({
      promptId: PROMPT_ID, kind: 'complete', stage: '엔진 실행 종료', connected: true
    })
    expect(tracker.get(PROMPT_ID)).not.toHaveProperty('percent')
    tracker.close()
  })
})

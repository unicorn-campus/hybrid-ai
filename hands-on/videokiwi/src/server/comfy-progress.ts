import type { EngineProgress } from '../shared/types.js'

export interface WebSocketLike {
  readonly readyState: number
  addEventListener(type: 'open' | 'message' | 'error' | 'close', listener: (event: Event | MessageEvent) => void): void
  close(): void
}

export type WebSocketFactory = (url: string) => WebSocketLike

type Listener = (event: EngineProgress) => void

const CONNECTING = 0
const OPEN = 1
const CONNECT_TIMEOUT_MS = 3_000
const MAX_RECONNECTS = 10

const NODE_STAGES: Record<string, { stage: string; kind: EngineProgress['kind'] }> = {
  '1': { stage: '영상 모델 준비', kind: 'node' },
  '2': { stage: '텍스트 모델 준비', kind: 'node' },
  '3': { stage: '영상 복원 모델 준비', kind: 'node' },
  '4': { stage: '음성 복원 모델 준비', kind: 'node' },
  '5': { stage: '영상과 소리 입력 인코딩', kind: 'node' },
  '10': { stage: '영상과 소리 생성', kind: 'sampling' },
  '11': { stage: '영상 복원', kind: 'decode' },
  '12': { stage: '음성 복원', kind: 'decode' },
  '13': { stage: '영상과 소리 합치기', kind: 'node' },
  '14': { stage: '영상 저장', kind: 'node' }
  , '30': { stage: '확장 원본 불러오기', kind: 'node' }
  , '31': { stage: '이어질 움직임 읽기', kind: 'node' }
  , '32': { stage: '이어질 움직임 적용', kind: 'node' }
}

function record(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown> : undefined
}

function stageFor(node: string | undefined): { stage: string; kind: EngineProgress['kind'] } {
  return node ? NODE_STAGES[node] ?? { stage: '영상 처리', kind: 'node' } : { stage: '영상 처리', kind: 'node' }
}

function validProgress(value: unknown, max: unknown): { value: number; max: number; percent: number } | undefined {
  if (typeof value !== 'number' || typeof max !== 'number' || !Number.isFinite(value) || !Number.isFinite(max) || max <= 0) {
    return undefined
  }
  return { value, max, percent: Math.max(0, Math.min(100, value / max * 100)) }
}

export class ComfyProgressTracker {
  private socket?: WebSocketLike
  private connectPromise?: Promise<void>
  private cancelConnect?: () => void
  private reconnectTimer?: ReturnType<typeof setTimeout>
  private reconnectAttempts = 0
  private reconnectScheduled = false
  private closed = false
  private readonly tracked = new Set<string>()
  private readonly currentNodes = new Map<string, string>()
  private readonly progress = new Map<string, EngineProgress>()
  private readonly listeners = new Set<Listener>()

  constructor(
    private readonly wsUrl: string,
    private readonly factory: WebSocketFactory = (url) => new WebSocket(url) as unknown as WebSocketLike
  ) {}

  async connect(): Promise<void> {
    if (this.closed) throw new Error('ComfyUI 진행 연결이 종료되었습니다.')
    if (this.socket?.readyState === OPEN) return
    if (this.connectPromise) return this.connectPromise

    let socket: WebSocketLike
    try {
      socket = this.factory(this.wsUrl)
      this.socket = socket
    } catch {
      this.scheduleReconnect()
      throw new Error('ComfyUI 진행 연결을 시작하지 못했습니다.')
    }

    const connection = new Promise<void>((resolve, reject) => {
      let settled = false
      let opened = false
      const finish = (error?: Error) => {
        if (settled) return
        settled = true
        clearTimeout(timeout)
        if (error) reject(error)
        else resolve()
      }
      this.cancelConnect = () => finish(new Error('ComfyUI 진행 연결이 종료되었습니다.'))
      const timeout = setTimeout(() => {
        finish(new Error('ComfyUI 진행 연결 시간이 초과되었습니다.'))
        this.scheduleReconnect()
        try { socket.close() } catch { /* 재연결 예약됨 */ }
      }, CONNECT_TIMEOUT_MS)

      socket.addEventListener('open', () => {
        if (this.socket !== socket) return
        opened = true
        this.reconnectAttempts = 0
        this.reconnectScheduled = false
        finish()
      })
      socket.addEventListener('message', (event) => {
        if (this.socket === socket) this.handleMessage((event as MessageEvent).data)
      })
      socket.addEventListener('error', () => {
        if (this.socket !== socket) return
        if (!opened) {
          finish(new Error('ComfyUI 진행 연결에 실패했습니다.'))
          this.scheduleReconnect()
          try { socket.close() } catch { /* 재연결 예약됨 */ }
        }
      })
      socket.addEventListener('close', () => {
        if (this.socket !== socket) return
        this.socket = undefined
        if (!opened) finish(new Error('ComfyUI 진행 연결이 닫혔습니다.'))
        this.emitDisconnected()
        this.scheduleReconnect()
      })
    })
    this.connectPromise = connection
    try {
      await connection
    } finally {
      if (this.connectPromise === connection) {
        this.connectPromise = undefined
        this.cancelConnect = undefined
      }
    }
  }

  track(promptId: string): void {
    this.tracked.add(promptId)
  }

  rebind(fromPromptId: string, toPromptId: string): void {
    if (fromPromptId === toPromptId || !this.tracked.delete(fromPromptId)) return
    this.tracked.add(toPromptId)
    const existing = this.progress.get(fromPromptId)
    if (existing) {
      this.progress.delete(fromPromptId)
      this.progress.set(toPromptId, { ...existing, promptId: toPromptId })
    }
    const node = this.currentNodes.get(fromPromptId)
    this.currentNodes.delete(fromPromptId)
    if (node) this.currentNodes.set(toPromptId, node)
  }

  forget(promptId: string): void {
    this.tracked.delete(promptId)
    this.currentNodes.delete(promptId)
    this.progress.delete(promptId)
  }

  get(promptId: string): EngineProgress | undefined {
    const value = this.progress.get(promptId)
    return value ? { ...value } : undefined
  }

  on(listener: Listener): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  close(): void {
    this.closed = true
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.reconnectTimer = undefined
    this.reconnectScheduled = false
    this.cancelConnect?.()
    this.cancelConnect = undefined
    this.connectPromise = undefined
    const socket = this.socket
    this.socket = undefined
    try { socket?.close() } catch { /* 종료 중 오류 무시 */ }
    this.listeners.clear()
    this.tracked.clear()
    this.currentNodes.clear()
    this.progress.clear()
  }

  private handleMessage(raw: unknown): void {
    if (typeof raw !== 'string') return
    let message: Record<string, unknown>
    try {
      const parsed = record(JSON.parse(raw))
      if (!parsed) return
      message = parsed
    } catch { return }
    const type = typeof message.type === 'string' ? message.type : ''
    const data = record(message.data)
    if (!data) return
    const promptId = this.resolvePromptId(data.prompt_id, type)
    if (!promptId || !this.tracked.has(promptId)) return

    if (type === 'executing') this.handleExecuting(promptId, data.node)
    else if (type === 'progress') this.handleNodeProgress(promptId, data.node, data.value, data.max)
    else if (type === 'progress_state') this.handleProgressState(promptId, data.nodes)
  }

  private resolvePromptId(value: unknown, type: string): string | undefined {
    if (typeof value === 'string') return value
    if (type === 'executing' && this.tracked.size === 1) return this.tracked.values().next().value
    return undefined
  }

  private handleExecuting(promptId: string, value: unknown): void {
    if (value === null) {
      this.currentNodes.delete(promptId)
      this.emit({ promptId, stage: '엔진 실행 종료', kind: 'complete', connected: true, updatedAt: new Date().toISOString() })
      this.tracked.delete(promptId)
      return
    }
    if (typeof value !== 'string' && typeof value !== 'number') return
    const node = String(value)
    this.currentNodes.set(promptId, node)
    const stage = stageFor(node)
    this.emit({ promptId, node, ...stage, connected: true, updatedAt: new Date().toISOString() })
  }

  private handleNodeProgress(promptId: string, nodeValue: unknown, value: unknown, max: unknown): void {
    const fallbackNode = this.currentNodes.get(promptId)
    const node = typeof nodeValue === 'string' || typeof nodeValue === 'number' ? String(nodeValue) : fallbackNode
    if (!node) return
    const measured = validProgress(value, max)
    if (!measured) return
    this.currentNodes.set(promptId, node)
    this.emit({
      promptId, node, ...stageFor(node), ...measured, connected: true, updatedAt: new Date().toISOString()
    })
  }

  private handleProgressState(promptId: string, nodesValue: unknown): void {
    const nodes = record(nodesValue)
    if (!nodes) return
    const running = Object.entries(nodes)
      .map(([id, state]) => [id, record(state)] as const)
      .filter((entry): entry is readonly [string, Record<string, unknown>] => entry[1]?.state === 'running')
    if (!running.length) return
    const current = this.currentNodes.get(promptId)
    const selected = running.find(([id]) => id === current) ?? running[running.length - 1]
    const [fallbackId, state] = selected
    const node = typeof state.node_id === 'string' || typeof state.node_id === 'number'
      ? String(state.node_id) : fallbackId
    if (state.value === 0 && state.max === 1) {
      this.handleExecuting(promptId, node)
      return
    }
    this.handleNodeProgress(promptId, node, state.value, state.max)
  }

  private emit(event: EngineProgress): void {
    this.progress.set(event.promptId, event)
    for (const listener of this.listeners) listener({ ...event })
  }

  private emitDisconnected(): void {
    if (this.closed) return
    for (const promptId of this.tracked) {
      this.emit({
        promptId, stage: '진행 연결 끊김', kind: 'disconnected', connected: false,
        updatedAt: new Date().toISOString()
      })
    }
  }

  private scheduleReconnect(): void {
    if (this.closed || this.reconnectScheduled || this.reconnectAttempts >= MAX_RECONNECTS) return
    this.reconnectScheduled = true
    const delay = Math.min(15_000, 1_000 * 2 ** this.reconnectAttempts)
    this.reconnectAttempts += 1
    this.reconnectTimer = setTimeout(() => {
      this.reconnectScheduled = false
      void this.connect().catch(() => undefined)
    }, delay)
  }
}

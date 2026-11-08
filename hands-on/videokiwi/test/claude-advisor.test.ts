import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { query } from '@anthropic-ai/claude-agent-sdk'
import sharp from 'sharp'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ClaudePromptAdvisor } from '../src/server/claude-advisor.js'
import type { GenerationInput, ImageAsset, PromptAssistantStatus } from '../src/shared/types.js'

interface Capture {
  request?: Parameters<typeof query>[0]
  userMessage?: Record<string, unknown>
  closed?: boolean
}

const tempDirectories: string[] = []

function input(overrides: Partial<GenerationInput> = {}): GenerationInput {
  return {
    mode: 'text',
    prompt: '대사원에서 멀어지며 웅장한 음악',
    duration: 5,
    resolution: 'preview',
    aspectRatio: '16:9',
    camera: 'pull-out',
    profile: 'balanced',
    seed: 42,
    ...overrides
  }
}

function available(): PromptAssistantStatus {
  return {
    provider: 'claude-agent-sdk',
    model: 'claude-opus-5-5',
    authentication: 'claude-subscription',
    available: true
  }
}

function fakeQuery(capture: Capture, suggestion: Record<string, unknown>) {
  return vi.fn((request: Parameters<typeof query>[0]) => {
    capture.request = request
    return {
      close() { capture.closed = true },
      async *[Symbol.asyncIterator]() {
        if (typeof request.prompt !== 'string') {
          for await (const message of request.prompt) capture.userMessage = message as unknown as Record<string, unknown>
        }
        yield {
          type: 'system', subtype: 'init', apiKeySource: 'none', model: 'claude-opus-5-5',
          claude_code_version: '2.1.319', cwd: 'workspace', tools: [], mcp_servers: [], permissionMode: 'dontAsk',
          slash_commands: [], output_style: 'default', skills: [], plugins: [], session_id: 'session',
          uuid: 'init', fast_mode_state: 'off'
        }
        yield {
          type: 'result', subtype: 'success', duration_ms: 1, duration_api_ms: 1, is_error: false,
          num_turns: 1, result: JSON.stringify(suggestion), total_cost_usd: 0,
          usage: {}, modelUsage: { 'claude-opus-5-5': {} }, permission_denials: [],
          structured_output: suggestion, stop_reason: null, uuid: 'result', session_id: 'session'
        }
      }
    }
  }) as unknown as typeof query
}

function suggestion(overrides: Record<string, unknown> = {}) {
  return {
    visual: 'The camera slowly pulls away from 대사원 while preserving its visible form.',
    soundscape: 'Soft wind across the courtyard. Grand orchestral music rises.',
    music: 'Grand instrumental orchestral score with a gradual crescendo.',
    dialogueRequested: false,
    notes: ['고유명사는 원문 그대로 유지했습니다.'],
    captionNote: '자막 요청 없음',
    ...overrides
  }
}

afterEach(async () => {
  vi.useRealTimers()
  delete process.env.ANTHROPIC_API_KEY
  delete process.env.CLAUDE_CODE_OAUTH_TOKEN
  delete process.env.AWS_ACCESS_KEY_ID
  await Promise.all(tempDirectories.splice(0).map((directory) => rm(directory, { recursive: true, force: true })))
})

describe('ClaudePromptAdvisor', () => {
  it('구독 로그인만 사용하는 격리된 SDK 옵션과 구조화 출력을 전달함', async () => {
    process.env.ANTHROPIC_API_KEY = 'must-not-leak'
    process.env.CLAUDE_CODE_OAUTH_TOKEN = 'must-not-leak'
    process.env.AWS_ACCESS_KEY_ID = 'must-not-leak'
    const capture: Capture = {}
    const advisor = new ClaudePromptAdvisor({ workspace: process.cwd(), queryFn: fakeQuery(capture, suggestion()) })
    vi.spyOn(advisor, 'status').mockResolvedValue(available())

    const result = await advisor.optimize(input())
    const options = capture.request?.options

    expect(options).toMatchObject({
      cwd: process.cwd(), model: 'claude-opus-5-5', maxTurns: 3, tools: [], mcpServers: {},
      strictMcpConfig: true, plugins: [], settingSources: [], persistSession: false,
      permissionMode: 'dontAsk', permissionPrompts: 'none', verbatimPrompts: true,
      managedSettings: { disableAllHooks: true, autoMemoryEnabled: false, disableBundledSkills: true },
      outputFormat: { type: 'json_schema' }
    })
    expect(options?.env?.ANTHROPIC_API_KEY).toBeUndefined()
    expect(options?.env?.CLAUDE_CODE_OAUTH_TOKEN).toBeUndefined()
    expect(options?.env?.AWS_ACCESS_KEY_ID).toBeUndefined()
    expect(await options?.canUseTool?.('Bash', {}, {
      signal: new AbortController().signal, toolUseID: 'tool', requestId: 'request'
    })).toMatchObject({ behavior: 'deny' })
    expect(result).toMatchObject({
      method: 'claude-agent-sdk', model: 'claude-opus-5-5', authentication: 'claude-subscription'
    })
    expect(capture.closed).toBe(true)

  })

  it('시작 이미지와 끝 이미지를 축소한 base64 멀티모달 메시지로 전달함', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'videokiwi-advisor-'))
    tempDirectories.push(directory)
    const firstFile = join(directory, 'first.png')
    const lastFile = join(directory, 'last.png')
    await sharp({ create: { width: 1600, height: 900, channels: 3, background: '#62a36b' } }).png().toFile(firstFile)
    await sharp({ create: { width: 900, height: 1600, channels: 3, background: '#8da8d8' } }).png().toFile(lastFile)
    const asset = (file: string, id: string): ImageAsset & { file: string } => ({
      id, file, name: `${id}.png`, previewUrl: '', size: 100, mime: 'image/png', width: 1600, height: 900
    })
    const capture: Capture = {}
    const advisor = new ClaudePromptAdvisor({ workspace: directory, queryFn: fakeQuery(capture, suggestion()) })
    vi.spyOn(advisor, 'status').mockResolvedValue(available())

    await advisor.optimize(input({
      mode: 'image', imageDescription: '초록빛 시작 프레임을 참고', audio: '바람과 새소리. No speech.'
    }), asset(firstFile, 'first'), asset(lastFile, 'last'))

    const message = capture.userMessage?.message as { content: Array<{ type: string; source?: { data?: string; media_type?: string } }> }
    const images = message.content.filter((block) => block.type === 'image')
    const text = (message.content[0] as unknown as { text: string }).text
    expect(images).toHaveLength(2)
    expect(images.every((block) => block.source?.media_type === 'image/jpeg' && (block.source.data?.length || 0) > 20)).toBe(true)
    expect(text).toContain('<이미지_설명>초록빛 시작 프레임을 참고</이미지_설명>')
    expect(text).toContain('<소리_설명>바람과 새소리. No speech.</소리_설명>')
  })

  it('대사원을 대사로 오인하지 않고 음악을 환경음 구역에서 제거함', async () => {
    const advisor = new ClaudePromptAdvisor({ workspace: process.cwd(), queryFn: fakeQuery({}, suggestion()) })
    vi.spyOn(advisor, 'status').mockResolvedValue(available())

    const result = await advisor.optimize(input())

    expect(result.optimized).toContain('overall_soundscape: Soft wind across the courtyard. No speech. No narration.')
    expect(result.optimized).toContain('non_diegetic_music: Grand instrumental orchestral score')
    expect(result.optimized).not.toContain('overall_soundscape: 대사원에서 멀어지며 웅장한 음악')
  })

  it('No speech는 전체 무음으로, no music은 환경음 제거로 해석하지 않음', async () => {
    const speechCapture: Capture = {}
    const speechAdvisor = new ClaudePromptAdvisor({
      workspace: process.cwd(), queryFn: fakeQuery(speechCapture, suggestion({ soundscape: 'Wind and birds.', music: 'Triumphant music.' }))
    })
    vi.spyOn(speechAdvisor, 'status').mockResolvedValue(available())
    const speechResult = await speechAdvisor.optimize(input({ prompt: 'A bird flies. No speech. Triumphant music.' }))
    expect(speechResult.optimized).toContain('overall_soundscape: Wind and birds. No speech. No narration.')
    expect(speechResult.optimized).toContain('non_diegetic_music: Triumphant music.')

    const musicAdvisor = new ClaudePromptAdvisor({
      workspace: process.cwd(), queryFn: fakeQuery({}, suggestion({ soundscape: 'Wind and birds.', music: 'None.' }))
    })
    vi.spyOn(musicAdvisor, 'status').mockResolvedValue(available())
    const musicResult = await musicAdvisor.optimize(input({ prompt: 'A bird flies with wind and birdsong, no music.' }))
    expect(musicResult.optimized).toContain('overall_soundscape: Wind and birds. No speech. No narration.')
    expect(musicResult.optimized).toContain('non_diegetic_music: None.')
  })

  it('영상 확장에서는 원본 마지막 장면에 이어질 구간임을 SDK에 전달함', async () => {
    const capture: Capture = {}
    const advisor = new ClaudePromptAdvisor({ workspace: process.cwd(), queryFn: fakeQuery(capture, suggestion()) })
    vi.spyOn(advisor, 'status').mockResolvedValue(available())
    await advisor.optimize(input({ extensionSourceId: 'source-id', prompt: '고양이가 창밖을 다시 봅니다.' }))
    const message = capture.userMessage?.message as { content: Array<{ text?: string }> }
    expect(message.content[0].text).toContain('<영상_확장 direction="sequel">')
    expect(message.content[0].text).toContain('원본의 마지막 장면')
  })

  it('인증 불가 상태에서는 SDK 질의를 시작하지 않음', async () => {
    const queryFn = fakeQuery({}, suggestion())
    const advisor = new ClaudePromptAdvisor({ workspace: process.cwd(), queryFn })
    vi.spyOn(advisor, 'status').mockResolvedValue({ ...available(), available: false, error: 'Claude Code 구독 로그인이 필요합니다.' })

    await expect(advisor.optimize(input())).rejects.toThrow('Claude Code 구독 로그인이 필요합니다.')
    expect(queryFn).not.toHaveBeenCalled()
  })

  it('120초가 지나면 질의를 중단하고 민감한 원문 없이 시간 초과를 보고함', async () => {
    vi.useFakeTimers()
    let markStarted!: () => void
    const started = new Promise<void>((resolve) => { markStarted = resolve })
    const queryFn = vi.fn((request: Parameters<typeof query>[0]) => {
      markStarted()
      return {
        close: vi.fn(),
        async *[Symbol.asyncIterator]() {
          await new Promise<void>((_resolve, reject) => {
            request.options?.abortController?.signal.addEventListener('abort', () => reject(new Error('token=secret aborted')))
          })
        }
      }
    }) as unknown as typeof query
    const advisor = new ClaudePromptAdvisor({ workspace: process.cwd(), queryFn })
    vi.spyOn(advisor, 'status').mockResolvedValue(available())

    const rejection = expect(advisor.optimize(input())).rejects.toThrow('Claude 프롬프트 제안 시간이 초과되었습니다.')
    await started
    await vi.advanceTimersByTimeAsync(120_001)
    await rejection
  })
})

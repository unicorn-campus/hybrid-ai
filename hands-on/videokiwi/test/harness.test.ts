import { describe, expect, it } from 'vitest'
import type { EngineStatus, GenerationInput, ImageAsset } from '../src/shared/types.js'
import {
  buildPlan,
  ensureAudioBoundaries,
  optimizePrompt,
  speechRequested,
  validateInput
} from '../src/server/harness.js'

const input = (overrides: Partial<GenerationInput> = {}): GenerationInput => ({
  mode: 'text',
  prompt: '고양이가 천천히 카메라 쪽으로 고개를 돌린다',
  duration: 5,
  resolution: 'preview',
  aspectRatio: 'auto',
  camera: 'static',
  profile: 'balanced',
  seed: 42,
  optimize: true,
  ...overrides
})

const engine = (overrides: Partial<EngineStatus> = {}): EngineStatus => ({
  connected: true,
  endpoint: 'http://127.0.0.1:8188',
  modelReady: true,
  turboAvailable: true,
  queueRunning: 0,
  queuePending: 0,
  ...overrides
})

const image: ImageAsset = {
  id: 'start-1',
  name: 'start.png',
  previewUrl: '/media/start-1',
  size: 1024,
  mime: 'image/png',
  width: 1200,
  height: 800,
  brightness: 0.62,
  dominantColor: '#7c634f'
}

describe('validateInput', () => {
  it('정상 입력을 필요한 필드만 남겨 반환한다', () => {
    const value = validateInput({ ...input(), ignored: 'value' })
    expect(value.prompt).toContain('고양이')
    expect(value.seed).toBe(42)
    expect(value).not.toHaveProperty('ignored')
  })

  it.each([
    [{ ...input(), duration: 7 }, '영상 길이'],
    [{ ...input(), seed: -1 }, '시드'],
    [{ ...input(), profile: 'turbo' }, '실행 프로파일'],
    [{ ...input({ mode: 'image' }), imageId: undefined }, '시작 이미지']
  ])('잘못된 생성 입력을 거부한다', (value, message) => {
    expect(() => validateInput(value)).toThrow(message)
  })

  it('원문과 사용자가 검토한 최종 프롬프트의 길이 경계를 구분한다', () => {
    expect(() => validateInput({ ...input(), prompt: '가'.repeat(4_001) })).toThrow('4000자')
    const reviewed = validateInput({
      ...input(),
      originalPrompt: '가'.repeat(4_000),
      prompt: '나'.repeat(8_000)
    })
    expect(reviewed.prompt).toHaveLength(8_000)
    expect(() => validateInput({
      ...input(),
      originalPrompt: '가'.repeat(4_000),
      prompt: '나'.repeat(8_001)
    })).toThrow('8000자')
  })
})

describe('optimizePrompt', () => {
  it('사용자 원문과 명시한 카메라 조건을 보존한다', () => {
    const result = optimizePrompt(input(), image)
    expect(result.optimized).toContain(input().prompt)
    expect(result.optimized).toContain('Locked-off static camera')
    expect(result.method).toBe('local-rules')
    expect(result.checks.every((check) => check.passed)).toBe(true)
  })

  it('빠른 움직임과 컷 전환을 느리거나 단일 쇼트로 바꾸지 않는다', () => {
    const result = optimizePrompt(input({
      prompt: '인물이 빠르게 달리고 장면이 세 번 컷 전환된다',
      camera: 'none'
    }))
    expect(result.optimized).toContain('빠르게 달리고 장면이 세 번 컷 전환된다')
    expect(result.optimized).not.toMatch(/slow|one continuous shot/iu)
    expect(result.optimized).toContain('Respect every requested speed, cut, transition')
  })

  it('원문의 카메라 연출과 선택 프리셋이 겹치면 원문을 우선한다', () => {
    const result = optimizePrompt(input({
      prompt: '카메라는 오른쪽으로 빠르게 팬한다',
      camera: 'static'
    }))
    expect(result.optimized).toContain('카메라는 오른쪽으로 빠르게 팬한다')
    expect(result.optimized).not.toContain('Locked-off static camera')
    expect(result.notes.join(' ')).toContain('원문 연출을 우선')
    const conflictCheck = result.checks.find((check) => check.label === '상충 규칙 방지')
    expect(conflictCheck).toMatchObject({ passed: true })
    expect(conflictCheck?.detail).toContain('카메라 지시를 감지')
  })

  it('피사체가 카메라 쪽으로 고개를 돌리는 행동은 카메라 연출로 오인하지 않는다', () => {
    const result = optimizePrompt(input({
      prompt: '고양이가 카메라 쪽으로 고개를 돌린다',
      camera: 'static'
    }))
    expect(result.optimized).toContain('Locked-off static camera')
    expect(result.notes.join(' ')).not.toContain('원문 연출을 우선')
  })

  it('이미지를 보고 피사체를 추측하지 않고 측정값만 기록한다', () => {
    const result = optimizePrompt(input({
      mode: 'image',
      imageId: image.id,
      prompt: '화면 속 대상이 천천히 오른쪽으로 움직인다'
    }), image)
    expect(result.imageFacts).toEqual({
      width: 1200,
      height: 800,
      brightness: 0.62,
      dominantColor: '#7c634f'
    })
    expect(result.optimized).not.toMatch(/\b(?:cat|person)\b|고양이|인물/iu)
    expect(result.notes.join(' ')).toContain('1200×800')
  })

  it('재최적화할 때 컴파일 구역을 중복하지 않는다', () => {
    const once = optimizePrompt(input())
    const twice = optimizePrompt(input({ prompt: once.optimized }))
    expect(twice.optimized.match(/integrated_multimodal_description:/gu)).toHaveLength(1)
    expect(twice.optimized.match(/overall_soundscape:/gu)).toHaveLength(1)
    expect(twice.optimized.match(/non_diegetic_music:/gu)).toHaveLength(1)
    expect(twice.optimized.match(/VideoKiwi audio boundary:/gu)).toHaveLength(1)
    expect(twice.original).toBe(input().prompt)
  })

  it('명시된 음악 요청과 자막 요청에 기본 금지 규칙을 덧붙이지 않는다', () => {
    const result = optimizePrompt(input({ prompt: '화면에 제목을 표시하고 잔잔한 음악을 재생한다' }))
    expect(result.optimized).not.toContain('No unwanted visible text')
    expect(result.optimized).not.toContain('Do not add music')
  })

  it('기존 H3 멀티모달 구조를 유지하고 재최적화해도 구역을 중복하지 않는다', () => {
    const structured = [
      'integrated_multimodal_description: A kite rises quickly. No lettering.',
      'overall_soundscape: Strong wind and rope creaks. No speech.',
      'non_diegetic_music: N/A.'
    ].join('\n\n')
    const once = optimizePrompt(input({ prompt: structured, camera: 'none' }))
    const twice = optimizePrompt(input({ prompt: once.optimized, camera: 'none' }))
    expect(twice.optimized.match(/integrated_multimodal_description:/gu)).toHaveLength(1)
    expect(twice.optimized.match(/overall_soundscape:/gu)).toHaveLength(1)
    expect(twice.optimized.match(/non_diegetic_music:/gu)).toHaveLength(1)
    expect(twice.optimized.match(/VideoKiwi guidance:/gu)).toHaveLength(1)
    expect(twice.optimized).toContain('A kite rises quickly. No lettering.')
    expect(twice.optimized).toContain('Strong wind and rope creaks. No speech.')
  })

  it('구조화 H3 프롬프트에서도 원문의 카메라 연출을 우선한다', () => {
    const structured = [
      'integrated_multimodal_description: A wide scene. The camera pans rapidly to the right.',
      'overall_soundscape: Wind.',
      'non_diegetic_music: N/A.'
    ].join('\n\n')
    const result = optimizePrompt(input({ prompt: structured, camera: 'static' }))
    expect(result.optimized).toContain('The camera pans rapidly to the right.')
    expect(result.optimized).not.toContain('Locked-off static camera')
    expect(result.notes.join(' ')).toContain('원문 연출을 우선')
  })

  it('일반 원문도 H3 세 구역으로 컴파일하고 장면을 발화 대본과 분리한다', () => {
    const result = optimizePrompt(input({ prompt: '비 오는 골목을 천천히 보여준다' }))
    expect(result.optimized.match(/integrated_multimodal_description:/gu)).toHaveLength(1)
    expect(result.optimized.match(/overall_soundscape:/gu)).toHaveLength(1)
    expect(result.optimized.match(/non_diegetic_music:/gu)).toHaveLength(1)
    expect(result.optimized).toContain('Treat the scene description as visual direction, not spoken content.')
    expect(result.optimized).toContain('No speech, no narration, no vocals.')
    expect(result.optimized).toContain('Do not read the scene description aloud.')
  })

  it('음악과 자막 요청을 장면 설명에서 분리하고 정확한 자막 문구를 안내한다', () => {
    const prompt =
      '하인샤 대사원의 모습을 점점 멀게 보여주면서 하늘로 시점이 이동. ' +
      '멀리서 하늘치가 날라오는 모습을 그림. 웅장한 백그라운드 뮤직과 하단에 적당한 한글 자막 보여줘요.'
    const result = optimizePrompt(input({ prompt, audio: '웅장한 음악' }))
    expect(result.optimized).toContain(prompt)
    expect(result.optimized).toContain('non_diegetic_music: 웅장한 음악')
    expect(result.optimized).toContain('No speech, no narration, no vocals.')
    expect(result.notes.join(' ')).toContain('정확한 문구가 없습니다')
  })
})

describe('audio boundaries', () => {
  it.each([
    ['대사: "안녕하세요"', true],
    ['인물이 반갑다고 말한다', true],
    ['하인샤 대사원의 전경', false],
    ['대사관 앞을 보여준다', false],
    ['대사 없음', false],
    ['자막: 대사: 안녕하세요', false]
  ])('명시적 발화만 구분한다: %s', (prompt, expected) => {
    expect(speechRequested(input({ prompt }))).toBe(expected)
  })

  it('명시적 대사를 보존하면서 장면 설명 낭독은 막는다', () => {
    const prompt = '인물이 카메라를 보며 말한다. 대사: "어서 오세요"'
    const result = ensureAudioBoundaries(input({ prompt }), prompt)
    expect(result).toContain(prompt)
    expect(result).toContain('Only produce explicitly requested speech or vocals.')
    expect(result).toContain('Do not read the scene description aloud.')
    expect(result).not.toContain('No speech, no narration, no vocals.')
  })

  it('음악만 요청하면 발화와 내레이션은 계속 금지한다', () => {
    const result = ensureAudioBoundaries(
      input({ prompt: '별이 빛나는 밤하늘', audio: '잔잔한 피아노 음악' }),
      '별이 빛나는 밤하늘'
    )
    expect(result).toContain('overall_soundscape: Subtle natural ambience')
    expect(result).toContain('No speech, no narration, no vocals.')
    expect(result).toContain('non_diegetic_music: 잔잔한 피아노 음악')
  })

  it('사용자가 검토한 일반 최종 문장에도 제출 직전 안전 경계를 적용한다', () => {
    const finalPrompt = '사용자가 수정한 최종 장면'
    const result = ensureAudioBoundaries(input({ prompt: finalPrompt }), finalPrompt)
    expect(result).toContain(finalPrompt)
    expect(result).toContain('No speech, no narration, no vocals.')
    expect(result.match(/integrated_multimodal_description:/gu)).toHaveLength(1)
    expect(result.match(/overall_soundscape:/gu)).toHaveLength(1)
    expect(result.match(/non_diegetic_music:/gu)).toHaveLength(1)
  })

  it('두 번 적용해도 H3 구역과 오디오 경계를 중복하지 않는다', () => {
    const first = ensureAudioBoundaries(input(), input().prompt)
    const second = ensureAudioBoundaries(input(), first)
    expect(second.match(/integrated_multimodal_description:/gu)).toHaveLength(1)
    expect(second.match(/overall_soundscape:/gu)).toHaveLength(1)
    expect(second.match(/non_diegetic_music:/gu)).toHaveLength(1)
    expect(second.match(/VideoKiwi audio boundary:/gu)).toHaveLength(1)
  })

  it('무음 요청은 환경음과 배경 음악을 모두 비운다', () => {
    const result = ensureAudioBoundaries(
      input({ prompt: '빈 방을 보여준다', audio: '완전한 무음' }),
      '빈 방을 보여준다'
    )
    expect(result).toContain('overall_soundscape: Silence. No environmental sound.')
    expect(result).toContain('non_diegetic_music: N/A.')
    expect(result).not.toContain('Subtle natural ambience')
  })

  it('레거시 안내문의 silence 단어를 무음 요청으로 오인하지 않는다', () => {
    const prompt = 'Follow audio and silence instructions in the user scene exactly.'
    const result = ensureAudioBoundaries(input({ prompt }), prompt)
    expect(result).toContain('Subtle natural ambience')
    expect(result).not.toContain('Silence. No environmental sound.')
  })

  it('무음이 아니라는 사용자 지시를 무음 요청으로 오인하지 않는다', () => {
    const result = ensureAudioBoundaries(
      input({ prompt: '폭포를 보여준다', audio: '무음 말고 물소리를 들려준다' }),
      '폭포를 보여준다'
    )
    expect(result).toContain('무음 말고 물소리를 들려준다')
    expect(result).not.toContain('Silence. No environmental sound.')
  })

  it('구조화 프롬프트의 상세 음악 설명을 짧은 오디오 필드로 덮어쓰지 않는다', () => {
    const prompt = [
      'integrated_multimodal_description: 구름 위를 비행한다.',
      'overall_soundscape: 강한 바람 소리.',
      'non_diegetic_music: 낮은 현악기와 북이 점차 고조되는 웅장한 기악곡.'
    ].join('\n\n')
    const result = ensureAudioBoundaries(input({ prompt, audio: '웅장한 음악' }), prompt)
    expect(result).toContain('낮은 현악기와 북이 점차 고조되는 웅장한 기악곡.')
    expect(result).not.toContain('non_diegetic_music: 웅장한 음악')
  })
})

describe('buildPlan', () => {
  it.each([
    [5, 124, 5.167],
    [10, 243, 10.125],
    [15, 362, 15.083]
  ])('%s초 요청을 H3 프레임 그리드로 올림한다', (duration, frames, actualDuration) => {
    const plan = buildPlan(input({ duration }), engine())
    expect(plan.frames).toBe(frames)
    expect(plan.actualDuration).toBe(actualDuration)
  })

  it('Turbo LoRA가 없으면 빠른 프로파일도 기본 20단계를 유지한다', () => {
    const plan = buildPlan(input({ profile: 'fast' }), engine({ turboAvailable: false }))
    expect(plan).toMatchObject({ steps: 20, sampler: 'res_multistep', turbo: false })
    expect(plan.warnings.join(' ')).toContain('Turbo LoRA')
  })

  it('Turbo LoRA가 있으면 결합된 8단계 경로를 선택한다', () => {
    const plan = buildPlan(input({ profile: 'fast' }), engine())
    expect(plan).toMatchObject({ steps: 8, sampler: 'euler', turbo: true })
  })

  it('이미지 자동 비율을 32배수와 안전 면적 안에서 계산한다', () => {
    const plan = buildPlan(input({ mode: 'image', imageId: image.id, aspectRatio: 'auto' }), engine(), image)
    expect(plan.width % 32).toBe(0)
    expect(plan.height % 32).toBe(0)
    expect(plan.width * plan.height).toBeLessThanOrEqual(640 * 352)
    expect(plan.width / plan.height).toBeGreaterThan(1.4)
  })

  it('영상 확장은 22프레임 가이드 뒤에 약 5초를 이어 생성함', () => {
    const extension = {
      id: 'source-1', name: 'source.mp4', videoUrl: '/api/extension-sources/source-1/video',
      image, width: 640, height: 352, duration: 5.167, fps: 24, guideFrames: 22
    }
    const plan = buildPlan(input({
      mode: 'image', imageId: undefined, extensionSourceId: extension.id, duration: 5, aspectRatio: 'auto'
    }), engine({ extensionAvailable: true }), undefined, extension)
    expect(plan).toMatchObject({ frames: 141, width: 640, height: 352, actualDuration: 5.875 })
    expect(plan.warnings.join(' ')).toContain('4.958초')
  })

  it('영상 확장은 화면비와 출력 크기 선택 대신 원본 크기를 유지함', () => {
    const extension = {
      id: 'source-2', name: 'wide.mp4', videoUrl: '/api/extension-sources/source-2/video',
      image, width: 864, height: 480, duration: 10, fps: 24, guideFrames: 22
    }
    const plan = buildPlan(input({
      mode: 'image', extensionSourceId: extension.id, aspectRatio: '9:16', resolution: 'preview'
    }), engine({ extensionAvailable: true }), undefined, extension)
    expect(plan).toMatchObject({ width: 864, height: 480 })
    expect(plan.warnings.join(' ')).toContain('원본 크기 864×480')
  })

  it('영상 확장은 끝 장면을 허용하고 별도 시작 이미지는 거부함', () => {
    const withEnd = validateInput(input({ mode: 'image', extensionSourceId: 'source-1', endImageId: 'end-1' }))
    expect(withEnd).toMatchObject({ extensionSourceId: 'source-1', endImageId: 'end-1', imageId: undefined })
    expect(() => validateInput(input({ mode: 'image', extensionSourceId: 'source-1', imageId: 'start-1' })))
      .toThrow('시작 이미지')
    expect(() => validateInput(input({ mode: 'image', endImageId: 'end-1' }))).toThrow('시작 이미지가 필요')
  })
})

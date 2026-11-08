import {
  CAMERA_PROMPTS,
  type AspectRatio,
  type EngineStatus,
  type ExecutionPlan,
  type ExtensionSource,
  type GenerationInput,
  type ImageAsset,
  type PerformanceProfile,
  type PromptOptimization
} from '../shared/types.js'

const MODES = new Set(['text', 'image'])
const RESOLUTIONS = new Set(['preview', 'standard'])
const ASPECT_RATIOS = new Set<AspectRatio>(['auto', '16:9', '9:16', '1:1', '4:3', '3:4', '21:9'])
const CAMERAS = new Set(['none', 'push-in', 'pull-out', 'orbit', 'pan-left', 'static'])
const PROFILES = new Set<PerformanceProfile>(['fast', 'balanced', 'quality'])
const DURATIONS = new Set([5, 10, 15])
const MAX_SOURCE_PROMPT_LENGTH = 4_000
const MAX_GENERATION_PROMPT_LENGTH = 8_000
const MAX_SEED = 0xffff_ffff
const COMPILED_PREFIX = '[VideoKiwi H3 prompt]'
const H3_GUIDANCE_PREFIX = 'VideoKiwi guidance:'
const VISUAL_ONLY_BOUNDARY = 'Treat the scene description as visual direction, not spoken content.'
const AUDIO_BOUNDARY_PREFIX = 'VideoKiwi audio boundary:'

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const requiredString = (value: unknown, name: string, maxLength = MAX_SOURCE_PROMPT_LENGTH): string => {
  if (typeof value !== 'string' || !value.trim()) throw new Error(`${name}을 입력해 주세요.`)
  const normalized = value.trim()
  if (normalized.length > maxLength) throw new Error(`${name}은 ${maxLength}자 이하여야 합니다.`)
  return normalized
}

const optionalString = (value: unknown, name: string, maxLength: number): string | undefined => {
  if (value === undefined) return undefined
  if (typeof value !== 'string') throw new Error(`${name}은 문자열이어야 합니다.`)
  const normalized = value.trim()
  if (!normalized) return undefined
  if (normalized.length > maxLength) throw new Error(`${name}은 ${maxLength}자 이하여야 합니다.`)
  return normalized
}

export const MAX_TITLE_LENGTH = 60

/** A record title is only a human label for the library. It is never sent to Claude or the H3 engine. */
export function normalizeTitle(value: unknown): string | undefined {
  if (value === undefined || value === null) return undefined
  if (typeof value !== 'string') throw new Error('제목은 문자열이어야 합니다.')
  const normalized = value.replace(/[\u0000-\u001f\u007f]/gu, ' ').replace(/\s+/gu, ' ').trim()
  if (!normalized) return undefined
  if ([...normalized].length > MAX_TITLE_LENGTH) throw new Error(`제목은 ${MAX_TITLE_LENGTH}자 이하로 입력해 주세요.`)
  return normalized
}

const imageId = (value: unknown, name: string): string | undefined => {
  const normalized = optionalString(value, name, 200)
  if (normalized && !/^[A-Za-z0-9_-]+$/u.test(normalized)) {
    throw new Error(`${name} 형식이 올바르지 않습니다.`)
  }
  return normalized
}

export function validateInput(value: unknown): GenerationInput {
  if (!isRecord(value)) throw new Error('생성 요청은 객체여야 합니다.')
  if (typeof value.mode !== 'string' || !MODES.has(value.mode)) throw new Error('생성 방식이 올바르지 않습니다.')
  if (typeof value.resolution !== 'string' || !RESOLUTIONS.has(value.resolution)) {
    throw new Error('해상도 프로파일이 올바르지 않습니다.')
  }
  if (typeof value.aspectRatio !== 'string' || !ASPECT_RATIOS.has(value.aspectRatio as AspectRatio)) {
    throw new Error('화면 비율이 올바르지 않습니다.')
  }
  if (typeof value.camera !== 'string' || !CAMERAS.has(value.camera)) throw new Error('카메라 설정이 올바르지 않습니다.')
  if (typeof value.profile !== 'string' || !PROFILES.has(value.profile as PerformanceProfile)) {
    throw new Error('실행 프로파일이 올바르지 않습니다.')
  }
  if (typeof value.duration !== 'number' || !DURATIONS.has(value.duration)) {
    throw new Error('영상 길이는 5초, 10초 또는 15초여야 합니다.')
  }
  if (!Number.isInteger(value.seed) || (value.seed as number) < 0 || (value.seed as number) > MAX_SEED) {
    throw new Error(`시드는 0에서 ${MAX_SEED} 사이의 정수여야 합니다.`)
  }
  if (value.optimize !== undefined && typeof value.optimize !== 'boolean') {
    throw new Error('프롬프트 개선 설정은 참 또는 거짓이어야 합니다.')
  }

  const firstImageId = imageId(value.imageId, '시작 이미지 ID')
  const lastImageId = imageId(value.endImageId, '끝 이미지 ID')
  const extensionSourceId = imageId(value.extensionSourceId, '확장 원본 ID')
  if (value.mode === 'image' && !firstImageId && !extensionSourceId) throw new Error('이미지 영상에는 시작 이미지가 필요합니다.')
  if (lastImageId && !firstImageId && !extensionSourceId) throw new Error('끝 이미지를 사용하려면 시작 이미지가 필요합니다.')
  if (extensionSourceId && firstImageId) {
    throw new Error('영상 확장은 원본 영상의 끝부분에서 시작하므로 별도의 시작 이미지를 함께 사용할 수 없습니다.')
  }
  const originalPrompt = optionalString(value.originalPrompt, '원본 장면 설명', MAX_SOURCE_PROMPT_LENGTH)
  const promptLimit = originalPrompt ? MAX_GENERATION_PROMPT_LENGTH : MAX_SOURCE_PROMPT_LENGTH

  return {
    mode: value.mode as GenerationInput['mode'],
    prompt: requiredString(value.prompt, '장면 설명', promptLimit),
    duration: value.duration,
    resolution: value.resolution as GenerationInput['resolution'],
    aspectRatio: value.aspectRatio as AspectRatio,
    camera: value.camera as GenerationInput['camera'],
    profile: value.profile as PerformanceProfile,
    seed: value.seed as number,
    imageId: firstImageId,
    endImageId: lastImageId,
    extensionSourceId,
    originalPrompt,
    imageDescription: optionalString(value.imageDescription, '이미지 설명', 1_000),
    title: normalizeTitle(value.title),
    audio: optionalString(value.audio, '소리 설명', 1_000),
    optimize: value.optimize ?? true
  }
}

const extractUserScene = (prompt: string): string => {
  if (!prompt.startsWith(COMPILED_PREFIX)) return prompt.trim()
  const match = prompt.match(/\[User scene\]\n([\s\S]*?)(?:\n\n\[|$)/u)
  return match?.[1]?.trim() || prompt.trim()
}

const mentions = (text: string, expression: RegExp): boolean => expression.test(text)

const MUSIC_REQUEST = /(음악|노래|배경\s*음악|백그라운드\s*뮤직|뮤직|music|song|soundtrack|bgm)/iu
const SILENCE_REQUEST =
  /(무음|완전한\s*침묵|아무\s*소리(?:도)?\s*(?:없|금지)|소리\s*없음|(?:complete\s+)?silence(?:\s+only)?(?:[.!?,\n]|$)|(?:keep|remain|make\s+it|audio\s+is)\s+silent\b|no\s+audio|mute)/iu
const SUBTITLE_REQUEST = /(자막|subtitle|caption)/iu
const EXACT_SUBTITLE =
  /(?:자막|subtitle|caption)\s*(?::|：|내용(?:은|:)|문구(?:는|:))\s*["'“”]?[^\n.!?。！？]+/iu

export function speechRequested(input: GenerationInput): boolean {
  const source = [input.originalPrompt, input.prompt, input.audio].filter(Boolean).join('\n')
  const withoutFalseFriends = source
    .replace(/대사(?:원|찰|관)/gu, '')
    .replace(/(?:자막|subtitle|caption)\s*[:：][^.\n]*/giu, '')
  const withoutNegatives = withoutFalseFriends
    .replace(
      /(?:대사|내레이션|나레이션|목소리|음성|보컬)(?:가|는|을|를)?\s*(?:없(?:음|이)?|금지|제외|하지\s*않[^\s,.。]*)/gu,
      ''
    )
    .replace(/no\s+(?:speech|dialogue|narration|voice(?:over)?|vocals?)/giu, '')
  const koreanSpeech =
    /(?:(?:대사|내레이션|나레이션|목소리|음성|보컬)\s*[:：]|(?:대사|내레이션|나레이션|목소리|음성|보컬)(?:가|는|을|를)?[^.\n]{0,24}(?:넣|말|들리|읽|낭독|재생|발화)|(?:말한다|말했다|말하며|외친다|속삭인다|낭독한다|읽어\s*준다|노래를\s*부른다))/iu
  const englishSpeech =
    /(?:(?:dialogue|speech|narration|voiceover|voice-over)\s*:|\b(?:says?|speaks?|narrates?|voiceover|voice-over|singing|vocals?)\b)/iu
  return koreanSpeech.test(withoutNegatives) || englishSpeech.test(withoutNegatives)
}

const hasExplicitCameraDirection = (text: string): boolean => {
  const koreanCameraDirection = /(?:카메라(?:는|가|를)?[^.\n]{0,40}(?:팬(?:닝|한다|하여|하며)?|줌(?:인|아웃)?|고정|트래킹|오빗|이동|움직|회전|흔들|당겨|밀어|빠져)|(?:고정\s*샷|트래킹\s*샷|오빗\s*샷|달리\s*샷|팬(?:닝|한다|하여|하며)|줌(?:인|아웃)))/iu
  const englishCameraDirection = /\b(?:camera[^.\n]{0,35}(?:pans?|zooms?|moves?|orbits?|tracks?|pushes?|pulls?|remains|stays|locked)|(?:pan|zoom|dolly|orbit|tracking|locked-off|static|handheld)\s+(?:camera|shot))\b/iu
  return koreanCameraDirection.test(text) || englishCameraDirection.test(text)
}

const cameraGuidance = (
  scene: string,
  camera: GenerationInput['camera'],
  notes: string[]
): { text?: string; sourceHasCameraDirection: boolean; added: boolean } => {
  const sourceHasCameraDirection = hasExplicitCameraDirection(scene)
  const selected = CAMERA_PROMPTS[camera]
  if (sourceHasCameraDirection && selected) {
    notes.push('원문에 카메라 움직임이 있어 선택한 카메라 프리셋을 추가하지 않았습니다. 원문 연출을 우선합니다.')
    return { sourceHasCameraDirection, added: false }
  }
  return { text: selected || undefined, sourceHasCameraDirection, added: Boolean(selected) }
}

interface StructuredH3Prompt {
  integrated: string
  soundscape?: string
  music?: string
}

const parseRawStructuredH3Prompt = (prompt: string): StructuredH3Prompt | undefined => {
  const integrated = prompt.match(
    /(?:^|\n)integrated_multimodal_description:\s*([\s\S]*?)(?=\n\s*\noverall_soundscape:|$)/iu
  )?.[1]?.trim()
  if (!integrated) return undefined
  return {
    integrated,
    soundscape: prompt.match(
      /(?:^|\n)overall_soundscape:\s*([\s\S]*?)(?=\n\s*\nnon_diegetic_music:|$)/iu
    )?.[1]?.trim(),
    music: prompt.match(/(?:^|\n)non_diegetic_music:\s*([\s\S]*?)$/iu)?.[1]?.trim()
  }
}

const parseStructuredH3Prompt = (prompt: string): StructuredH3Prompt | undefined => {
  const structured = parseRawStructuredH3Prompt(prompt)
  if (!structured) return undefined
  return {
    ...structured,
    integrated: structured.integrated.replace(new RegExp(`\\s*${H3_GUIDANCE_PREFIX}[\\s\\S]*$`, 'iu'), '').trim()
  }
}

const extractMusicDirection = (source: string): string | undefined => {
  const sceneOnly = source.replace(new RegExp(`\\s*${H3_GUIDANCE_PREFIX}[\\s\\S]*$`, 'iu'), '').trim()
  const sentence = sceneOnly
    .split(/(?<=[.!?。！？])\s*/u)
    .find((part) => MUSIC_REQUEST.test(part) && !/(음악[^.\n]{0,12}(?:금지|없음|제외)|do\s+not\s+add\s+music|no\s+music)/iu.test(part))
  if (!sentence) return undefined
  return sentence
    .replace(/(?:과|와)\s*(?:하단|상단|화면|자막)[\s\S]*$/u, '')
    .trim()
}

const silenceRequested = (source: string): boolean => {
  const withoutNegatives = source
    .replace(/무음\s*(?:말고|아닌|이\s*아닌)/gu, '')
    .replace(/(?:not\s+(?:silent|silence)|no\s+silence)/giu, '')
  return SILENCE_REQUEST.test(withoutNegatives)
}

export function ensureAudioBoundaries(input: GenerationInput, prompt: string): string {
  const source = prompt.trim()
  if (!source) throw new Error('장면 설명을 입력해 주세요.')

  const structured = parseRawStructuredH3Prompt(source)
  const integrated = structured?.integrated ?? source
  const integratedWithBoundary = integrated.includes(VISUAL_ONLY_BOUNDARY)
    ? integrated
    : `${integrated} ${VISUAL_ONLY_BOUNDARY} Audio directions are specifications, not a script to read aloud.`
  const userScene = input.originalPrompt || input.prompt
  const userAudioSource = [userScene, input.audio].filter(Boolean).join('\n')
  const silent = silenceRequested(userAudioSource)
  const explicitSpeech = speechRequested({ ...input, prompt: userScene, originalPrompt: undefined })
  const priorSoundscape = structured?.soundscape
    ?.replace(new RegExp(`\\s*${AUDIO_BOUNDARY_PREFIX}[\\s\\S]*$`, 'iu'), '')
    .trim()
  const audioIsMusic = Boolean(input.audio && MUSIC_REQUEST.test(input.audio))
  const audioIsSilence = Boolean(input.audio && silenceRequested(input.audio))
  let soundscape = priorSoundscape
    ? input.audio && !audioIsMusic && !audioIsSilence
      ? `${priorSoundscape} Additional user direction: ${input.audio.trim()}`
      : priorSoundscape
    : input.audio && !audioIsMusic && !audioIsSilence
      ? input.audio.trim()
      : 'Subtle natural ambience that matches the described scene.'
  const existingMusic = structured?.music?.trim()
  const existingMusicIsEmpty = !existingMusic || /^(?:N\/?A|none|없음)\.?$/iu.test(existingMusic)
  let music = existingMusicIsEmpty
    ? extractMusicDirection(structured?.integrated ?? source) || existingMusic || 'N/A.'
    : existingMusic

  const speechBoundary = silent
    ? 'No speech, no narration, no vocals. Do not read the scene description aloud.'
    : explicitSpeech
      ? 'Only produce explicitly requested speech or vocals. Do not read the scene description aloud.'
      : 'No speech, no narration, no vocals. Do not read the scene description aloud.'
  if (silent) {
    soundscape = 'Silence. No environmental sound.'
    music = 'N/A.'
  } else if (audioIsMusic && existingMusicIsEmpty) {
    music = input.audio!.trim()
  }

  return [
    `integrated_multimodal_description: ${integratedWithBoundary}`,
    `overall_soundscape: ${soundscape} ${AUDIO_BOUNDARY_PREFIX} ${speechBoundary}`,
    `non_diegetic_music: ${music}`
  ].join('\n\n')
}

const optimizeStructuredH3Prompt = (
  original: string,
  structured: StructuredH3Prompt,
  input: GenerationInput,
  image?: ImageAsset,
  endImage?: ImageAsset
): PromptOptimization => {
  const guidance: string[] = []
  const notes = ['기존 H3 멀티모달 프롬프트 구역을 인식하고 같은 구조를 유지했습니다.']

  if (input.imageDescription?.trim()) {
    guidance.push(`User-provided image description: ${input.imageDescription.trim()}`)
    notes.push('이미지 내용은 사용자가 입력한 설명만 사용했습니다.')
  }
  if (image) {
    guidance.push(
      'Use the supplied start frame as the exact opening composition and preserve its geometry, colors, and visual identity.'
    )
    if (endImage) guidance.push('Transition toward the supplied end frame and preserve its final composition and geometry.')
    notes.push(`시작 이미지의 측정 크기 ${image.width}×${image.height}px을 화면 비율 계산에만 사용했습니다.`)
  }
  const camera = cameraGuidance(structured.integrated, input.camera, notes)
  if (camera.text) guidance.push(camera.text)
  guidance.push(
    'Maintain coherent subject shape and spatial continuity between frames; respect every requested speed, cut, transition, and direction.'
  )

  const hasTextRequest = mentions(
    structured.integrated,
    /(자막|텍스트|글자|문구|제목|로고|간판|caption|subtitle|text|title|logo|sign)/iu
  )
  const fullAudio = [structured.soundscape ?? '', structured.music ?? '', input.audio ?? ''].join(' ')
  const hasMusicRequest = mentions(fullAudio, MUSIC_REQUEST)
  if (!hasTextRequest) guidance.push('No unwanted visible text, subtitles, logos, or watermarks.')
  if (!hasMusicRequest) guidance.push('Do not add music.')

  const guided = [
    `integrated_multimodal_description: ${structured.integrated} ${H3_GUIDANCE_PREFIX} ${guidance.join(' ')}`,
    `overall_soundscape: ${structured.soundscape || 'Subtle natural ambience that matches the described scene.'}`,
    `non_diegetic_music: ${structured.music || 'N/A.'}`
  ].join('\n\n')
  const optimized = ensureAudioBoundaries(input, guided)

  const checks: PromptOptimization['checks'] = [
    {
      label: '입력 의도 보존',
      passed: optimized.includes(structured.integrated),
      detail: '기존 integrated_multimodal_description 내용을 그대로 포함함'
    },
    {
      label: 'H3 구역 보존',
      passed: ['integrated_multimodal_description:', 'overall_soundscape:', 'non_diegetic_music:']
        .every((label) => optimized.includes(label)),
      detail: '영상, 환경음, 배경 음악 구역을 각각 한 번만 구성함'
    },
    {
      label: '이미지 추측 방지',
      passed: true,
      detail: image ? '이미지 내용은 사용자 설명과 측정값만 사용함' : '이미지 입력 없음'
    },
    {
      label: '상충 규칙 방지',
      passed: (!camera.sourceHasCameraDirection || !camera.added) && optimized.includes('respect every requested speed'),
      detail: camera.sourceHasCameraDirection
        ? '원문의 카메라 지시를 감지하여 선택 프리셋을 추가하지 않고, 속도와 전환 지시를 보존함'
        : '추가 카메라 지시와 원문이 겹치지 않으며, 속도와 전환 지시를 보존함'
    }
  ]
  if (SUBTITLE_REQUEST.test(structured.integrated) && !EXACT_SUBTITLE.test(structured.integrated)) {
    notes.push('자막 요청은 확인했지만 정확한 문구가 없습니다. 표시할 자막 문구를 직접 입력해 주세요.')
  }
  notes.push('규칙 기반 개선은 결과 품질을 보장하지 않습니다. 같은 시드로 원문과 개선문을 비교할 수 있습니다.')

  return {
    original,
    optimized,
    method: 'local-rules',
    notes,
    checks,
    imageFacts: image
      ? {
          width: image.width,
          height: image.height,
          brightness: image.brightness,
          dominantColor: image.dominantColor
        }
      : undefined
  }
}

export function optimizePrompt(
  input: GenerationInput,
  image?: ImageAsset,
  endImage?: ImageAsset
): PromptOptimization {
  const submitted = extractUserScene(input.originalPrompt?.trim() || input.prompt.trim())
  if (!submitted) throw new Error('장면 설명을 입력해 주세요.')
  const structured = parseStructuredH3Prompt(submitted)
  const original = structured?.integrated ?? submitted
  if (structured) return optimizeStructuredH3Prompt(original, structured, input, image, endImage)

  const visualGuidance: string[] = []
  const notes = ['사용자가 입력한 장면을 그대로 보존하고 실행 조건만 덧붙였습니다.']
  const checks: PromptOptimization['checks'] = []

  if (input.imageDescription?.trim()) {
    visualGuidance.push(`User-provided image description: ${input.imageDescription.trim()}`)
    notes.push('이미지 내용은 사용자가 입력한 설명만 사용했습니다.')
  }

  if (image) {
    const endClause = endImage
      ? 'Use the supplied end frame as the final composition and transition toward it without changing its geometry.'
      : ''
    visualGuidance.push(
      `Use the supplied start frame as the exact opening composition. ` +
      `Preserve its geometry, colors, and visual identity while motion begins. ${endClause}`.trim()
    )
    notes.push(`시작 이미지의 측정 크기 ${image.width}×${image.height}px을 화면 비율 계산에만 사용했습니다.`)
    if (endImage) notes.push(`끝 이미지의 측정 크기 ${endImage.width}×${endImage.height}px만 확인했습니다.`)
  }

  const camera = cameraGuidance(original, input.camera, notes)
  if (camera.text) visualGuidance.push(camera.text)

  visualGuidance.push(
    'Maintain coherent subject shape and spatial continuity between frames. ' +
    'Respect every requested speed, cut, transition, and direction in the user scene.'
  )

  const audioSource = [original, input.audio ?? ''].join(' ')
  if (input.audio) {
    notes.push('사용자가 입력한 소리 설명을 환경음, 발화, 배경 음악 경계에 맞춰 분리했습니다.')
  }

  const hasTextRequest = mentions(original, /(자막|텍스트|글자|문구|제목|로고|간판|caption|subtitle|text|title|logo|sign)/iu)
  const hasMusicRequest = mentions(audioSource, MUSIC_REQUEST)
  const exclusions: string[] = []
  if (!hasTextRequest) exclusions.push('No unwanted visible text, subtitles, logos, or watermarks.')
  if (!hasMusicRequest) exclusions.push('Do not add music.')
  if (exclusions.length) visualGuidance.push(exclusions.join(' '))

  const guided = [
    `integrated_multimodal_description: ${original} ${H3_GUIDANCE_PREFIX} ${visualGuidance.join(' ')}`,
    'overall_soundscape: Subtle natural ambience that matches the described scene.',
    'non_diegetic_music: N/A.'
  ].join('\n\n')
  const optimized = ensureAudioBoundaries(input, guided)
  checks.push({
    label: '입력 의도 보존',
    passed: optimized.includes(original),
    detail: '원문을 다시 쓰지 않고 integrated_multimodal_description 구역에 그대로 포함함'
  })
  checks.push({
    label: '이미지 추측 방지',
    passed: !image || !input.imageDescription || optimized.includes(input.imageDescription),
    detail: image ? '이미지 내용은 사용자 설명과 측정값만 사용함' : '이미지 입력 없음'
  })
  checks.push({
    label: '상충 규칙 방지',
    passed: (!camera.sourceHasCameraDirection || !camera.added) && optimized.includes('Respect every requested speed'),
    detail: camera.sourceHasCameraDirection
      ? '원문의 카메라 지시를 감지하여 선택 프리셋을 추가하지 않고, 속도와 전환 지시를 보존함'
      : '추가 카메라 지시와 원문이 겹치지 않으며, 속도와 전환 지시를 보존함'
  })
  checks.push({
    label: '생성 조건 보강',
    passed: ['integrated_multimodal_description:', 'overall_soundscape:', 'non_diegetic_music:']
      .every((label) => optimized.includes(label)),
    detail: '카메라, 프레임 연속성, 소리 경계, 불필요한 출력 조건을 H3의 세 구역에 맞춰 추가함'
  })

  if (original.length < 20) {
    notes.push('장면 설명이 짧습니다. 피사체의 행동과 주변 환경을 직접 덧붙이면 의도를 더 분명하게 전달할 수 있습니다.')
  }
  if (SUBTITLE_REQUEST.test(original) && !EXACT_SUBTITLE.test(original)) {
    notes.push('자막 요청은 확인했지만 정확한 문구가 없습니다. 표시할 자막 문구를 직접 입력해 주세요.')
  }
  notes.push('규칙 기반 개선은 결과 품질을 보장하지 않습니다. 같은 시드로 원문과 개선문을 비교할 수 있습니다.')

  return {
    original,
    optimized,
    method: 'local-rules',
    notes,
    checks,
    imageFacts: image
      ? {
          width: image.width,
          height: image.height,
          brightness: image.brightness,
          dominantColor: image.dominantColor
        }
      : undefined
  }
}

const ratioValue = (aspectRatio: AspectRatio, image?: ImageAsset): number => {
  if (aspectRatio === 'auto') {
    return image && image.width > 0 && image.height > 0 ? image.width / image.height : 16 / 9
  }
  const [width, height] = aspectRatio.split(':').map(Number)
  return width / height
}

const floor32 = (value: number): number => Math.max(32, Math.floor(value / 32) * 32)

const canvasFor = (
  resolution: GenerationInput['resolution'],
  aspectRatio: AspectRatio,
  image?: ImageAsset
): { width: number; height: number } => {
  const landscape = resolution === 'preview' ? { width: 640, height: 352 } : { width: 864, height: 480 }
  const ratio = ratioValue(aspectRatio, image)
  const near16By9 = Math.abs(ratio - 16 / 9) < 0.04
  if (near16By9) return landscape
  if (Math.abs(ratio - 9 / 16) < 0.04) return { width: landscape.height, height: landscape.width }

  const areaCap = landscape.width * landscape.height
  let height = floor32(Math.sqrt(areaCap / ratio))
  let width = floor32(height * ratio)
  while (width * height > areaCap && (width > 32 || height > 32)) {
    if (width >= height) width -= 32
    else height -= 32
  }
  return { width, height }
}

const frameCount = (seconds: number): number => {
  const requested = seconds * 24
  let frames = 5
  while (frames < requested) frames += 17
  return frames
}

const extensionFrameCount = (seconds: number, guideFrames: number): number => {
  const requested = seconds * 24 + guideFrames
  const step = Math.max(0, Math.round((requested - 5) / 17))
  return 5 + step * 17
}

export function buildPlan(
  input: GenerationInput,
  engine: EngineStatus,
  image?: ImageAsset,
  extension?: ExtensionSource
): ExecutionPlan {
  // An extension keeps the source canvas so the new frames join the original without rescaling.
  const { width, height } = extension
    ? { width: extension.width, height: extension.height }
    : canvasFor(input.resolution, input.aspectRatio, image)
  const frames = extension ? extensionFrameCount(input.duration, extension.guideFrames) : frameCount(input.duration)
  const warnings: string[] = []
  let steps = 20
  let sampler = 'res_multistep'
  let turbo = false

  if (input.profile === 'fast') {
    if (engine.turboAvailable) {
      steps = 8
      sampler = 'euler'
      turbo = true
    } else {
      warnings.push('Turbo LoRA를 확인하지 못해 검증된 기본 20단계 경로를 사용합니다.')
    }
  } else if (input.profile === 'quality') {
    steps = 30
    warnings.push('30단계가 20단계보다 더 좋은 결과를 보장하지 않습니다. 같은 시드로 비교해 주세요.')
  }

  if (!engine.modelReady) warnings.push('로컬 H3 모델 준비 상태를 확인하지 못했습니다. 실행 전에 엔진 상태를 확인해 주세요.')
  if (extension && width * height > 640 * 352) {
    warnings.push(`원본 크기 ${width}×${height}를 유지합니다. 미리보기 크기보다 커서 생성 시간과 메모리 사용이 늘 수 있습니다.`)
  }
  if (!extension && input.resolution === 'standard') {
    warnings.push('표준 크기는 이 앱에서 아직 실측하지 않았으며 16GB VRAM에서 생성 시간이 크게 늘 수 있습니다.')
  }
  if (input.duration > 5) {
    warnings.push('5초를 넘는 영상은 이 앱에서 아직 실측하지 않았으며 메모리와 생성 시간이 크게 늘 수 있습니다.')
  }
  if (extension) {
    const addedDuration = (frames - extension.guideFrames) / 24
    warnings.push(
      `원본 끝 ${extension.guideFrames}프레임을 움직임 가이드로 사용하며 ` +
      `결과에는 약 ${addedDuration.toFixed(3)}초가 추가됩니다.`
    )
  }
  warnings.push('성능과 품질을 비교할 때는 시드와 다른 설정을 고정하고 한 항목만 바꿔 주세요.')

  return {
    width,
    height,
    frames,
    fps: 24,
    steps,
    sampler,
    turbo,
    actualDuration: Number((frames / 24).toFixed(3)),
    warnings
  }
}

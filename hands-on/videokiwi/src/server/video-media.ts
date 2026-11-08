import { execFile } from 'node:child_process'
import { constants } from 'node:fs'
import { access, copyFile, mkdir, stat, unlink } from 'node:fs/promises'
import { dirname, join, parse, resolve } from 'node:path'
import { randomUUID } from 'node:crypto'

export interface VideoInfo {
  width: number
  height: number
  fps: number
  duration: number
  frames?: number
  hasAudio: boolean
}

export interface MediaToolOptions {
  ffmpegPath?: string
  ffprobePath?: string
  timeoutMs?: number
}

export interface ExtensionGuideOptions extends MediaToolOptions {
  guideFrames: number
  fps: number
  width: number
  height: number
}

export interface ExtensionGuideResult {
  guidePath: string
  lastFramePath: string
  guideFrames: number
  duration: number
  source: VideoInfo
}

export interface ConcatenateOptions extends MediaToolOptions {
  overlapFrames: number
  fps: number
  width: number
  height: number
  audioFadeSeconds?: number
}

type ProbeStream = {
  codec_type?: string
  width?: number
  height?: number
  avg_frame_rate?: string
  r_frame_rate?: string
  duration?: string
  nb_frames?: string
}

type ProbeResult = {
  streams?: ProbeStream[]
  format?: { duration?: string }
}

const safeNumber = (value: unknown): number | undefined => {
  const result = Number(value)
  return Number.isFinite(result) && result > 0 ? result : undefined
}

function ratio(value: string | undefined): number | undefined {
  if (!value) return undefined
  const parts = value.split('/')
  const top = Number(parts[0])
  const bottom = Number(parts[1] ?? '1')
  if (!Number.isFinite(top) || !Number.isFinite(bottom) || bottom === 0) return undefined
  return top / bottom
}

function errorText(error: unknown, stderr: string): string {
  const detail = stderr.trim().slice(-1200)
  if (detail) return detail
  return error instanceof Error ? error.message : String(error)
}

function runFile(executable: string, args: string[], timeoutMs: number): Promise<string> {
  return new Promise((resolvePromise, rejectPromise) => {
    execFile(executable, args, {
      encoding: 'utf8', windowsHide: true, timeout: timeoutMs, maxBuffer: 2 * 1024 * 1024
    }, (error, stdout, stderr) => {
      if (error) rejectPromise(new Error(errorText(error, stderr)))
      else resolvePromise(stdout)
    })
  })
}

async function regularFile(path: string): Promise<void> {
  const value = await stat(path).catch(() => undefined)
  if (!value?.isFile()) throw new Error('영상 파일을 찾을 수 없습니다.')
}

async function mustNotExist(path: string): Promise<void> {
  try {
    await access(path)
    throw new Error('출력 파일이 이미 있습니다.')
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
  }
}

function validateGeometry(width: number, height: number, fps: number): void {
  if (![width, height, fps].every(Number.isFinite) || width < 32 || height < 32 || fps <= 0 ||
      !Number.isInteger(width) || !Number.isInteger(height) || width % 2 || height % 2) {
    throw new Error('영상 크기는 짝수 정수, 프레임 속도는 양수여야 합니다.')
  }
}

function videoFilter(width: number, height: number): string {
  return `scale=${width}:${height}:force_original_aspect_ratio=decrease,` +
    `pad=${width}:${height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,format=yuv420p`
}

function tempPath(destination: string, extension: string): string {
  return join(dirname(destination), `.videokiwi-${randomUUID()}${extension}`)
}

async function publish(temp: string, destination: string): Promise<void> {
  await copyFile(temp, destination, constants.COPYFILE_EXCL)
  await unlink(temp)
}

async function cleanup(paths: string[]): Promise<void> {
  await Promise.all(paths.map(path => unlink(path).catch(() => undefined)))
}

export async function probeVideo(path: string, options: MediaToolOptions = {}): Promise<VideoInfo> {
  await regularFile(path)
  const stdout = await runFile(options.ffprobePath ?? 'ffprobe', [
    '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path
  ], options.timeoutMs ?? 30_000)
  let result: ProbeResult
  try { result = JSON.parse(stdout) as ProbeResult }
  catch { throw new Error('영상 정보를 읽지 못했습니다.') }
  const streams = Array.isArray(result.streams) ? result.streams : []
  const video = streams.find(stream => stream.codec_type === 'video')
  const width = safeNumber(video?.width)
  const height = safeNumber(video?.height)
  const fps = ratio(video?.avg_frame_rate) ?? ratio(video?.r_frame_rate)
  const duration = safeNumber(video?.duration) ?? safeNumber(result.format?.duration)
  const frames = safeNumber(video?.nb_frames)
  if (!width || !height || !fps || !duration) throw new Error('유효한 영상 스트림을 찾지 못했습니다.')
  return {
    width: Math.round(width), height: Math.round(height), fps, duration,
    frames: frames ? Math.round(frames) : undefined,
    hasAudio: streams.some(stream => stream.codec_type === 'audio')
  }
}

export async function extractExtensionGuide(
  sourcePath: string,
  destination: string,
  options: ExtensionGuideOptions
): Promise<ExtensionGuideResult> {
  const source = resolve(sourcePath)
  const guidePath = resolve(destination)
  const parsed = parse(guidePath)
  const lastFramePath = join(parsed.dir, `${parsed.name}.last.png`)
  validateGeometry(options.width, options.height, options.fps)
  if (!Number.isInteger(options.guideFrames) || options.guideFrames < 5 || options.guideFrames % 17 !== 5) {
    throw new Error('H3 가이드 프레임은 5, 22, 39처럼 17k+5 규칙을 따라야 합니다.')
  }
  if (source === guidePath || source === resolve(lastFramePath)) throw new Error('원본과 출력 경로가 같을 수 없습니다.')
  await regularFile(source)
  await mkdir(dirname(guidePath), { recursive: true })
  await Promise.all([mustNotExist(guidePath), mustNotExist(lastFramePath)])
  const info = await probeVideo(source, options)
  const normalizedFrames = Math.abs(info.fps - options.fps) < 0.001 && info.frames
    ? info.frames : Math.floor(info.duration * options.fps + 0.001)
  if (normalizedFrames < options.guideFrames) {
    throw new Error(`원본 영상은 ${options.guideFrames}프레임 이상이어야 합니다.`)
  }

  const guideDuration = options.guideFrames / options.fps
  const audioStart = Math.max(0, info.duration - guideDuration)
  const firstFrame = Math.max(0, normalizedFrames - options.guideFrames)
  const guideTemp = tempPath(guidePath, '.mp4')
  const frameTemp = tempPath(lastFramePath, '.png')
  const timeout = options.timeoutMs ?? 120_000
  let publishedGuide = false
  let publishedFrame = false
  try {
    const args = ['-hide_banner', '-loglevel', 'error', '-y', '-i', source]
    let audioInput = '0:a:0'
    if (!info.hasAudio) {
      args.push('-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000')
      audioInput = '1:a:0'
    }
    const filter = [
      `[0:v:0]fps=${options.fps},trim=start_frame=${firstFrame}:end_frame=${normalizedFrames},` +
        `setpts=PTS-STARTPTS,${videoFilter(options.width, options.height)}[v]`,
      `[${audioInput}]atrim=start=${info.hasAudio ? audioStart : 0},asetpts=PTS-STARTPTS,` +
        'aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,' +
        `apad,atrim=duration=${guideDuration}[a]`
    ].join(';')
    args.push('-filter_complex', filter, '-map', '[v]', '-map', '[a]', '-frames:v', String(options.guideFrames),
      '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
      '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', guideTemp)
    await runFile(options.ffmpegPath ?? 'ffmpeg', args, timeout)
    await runFile(options.ffmpegPath ?? 'ffmpeg', [
      '-hide_banner', '-loglevel', 'error', '-y', '-i', guideTemp,
      '-vf', `select=eq(n\\,${options.guideFrames - 1})`, '-frames:v', '1', '-fps_mode', 'vfr', frameTemp
    ], timeout)
    const guideInfo = await probeVideo(guideTemp, options)
    if (guideInfo.frames !== undefined && guideInfo.frames !== options.guideFrames) {
      throw new Error('가이드 영상의 프레임 수가 요청과 다릅니다.')
    }
    await publish(guideTemp, guidePath)
    publishedGuide = true
    await publish(frameTemp, lastFramePath)
    publishedFrame = true
    return { guidePath, lastFramePath, guideFrames: options.guideFrames, duration: guideDuration, source: info }
  } catch (error) {
    await cleanup([
      guideTemp, frameTemp,
      ...(publishedGuide ? [guidePath] : []),
      ...(publishedFrame ? [lastFramePath] : [])
    ])
    throw error
  }
}

export async function concatenateExtendedVideo(
  sourcePath: string,
  generatedPath: string,
  destination: string,
  options: ConcatenateOptions
): Promise<VideoInfo> {
  const source = resolve(sourcePath)
  const generated = resolve(generatedPath)
  const output = resolve(destination)
  validateGeometry(options.width, options.height, options.fps)
  if (!Number.isInteger(options.overlapFrames) || options.overlapFrames < 0) {
    throw new Error('중복 프레임 수는 0 이상의 정수여야 합니다.')
  }
  if ([source, generated].includes(output)) throw new Error('원본과 출력 경로가 같을 수 없습니다.')
  await Promise.all([regularFile(source), regularFile(generated)])
  await mkdir(dirname(output), { recursive: true })
  await mustNotExist(output)
  const [sourceInfo, generatedInfo] = await Promise.all([probeVideo(source, options), probeVideo(generated, options)])
  const sourceFrames = Math.abs(sourceInfo.fps - options.fps) < 0.001 && sourceInfo.frames
    ? sourceInfo.frames : Math.floor(sourceInfo.duration * options.fps + 0.001)
  const generatedFrames = Math.abs(generatedInfo.fps - options.fps) < 0.001 && generatedInfo.frames
    ? generatedInfo.frames : Math.floor(generatedInfo.duration * options.fps + 0.001)
  if (generatedFrames <= options.overlapFrames) throw new Error('생성 영상이 제거할 중복 구간보다 짧습니다.')
  const sourceDuration = sourceFrames / options.fps
  const extensionFrames = generatedFrames - options.overlapFrames
  const extensionDuration = extensionFrames / options.fps
  const overlapDuration = options.overlapFrames / options.fps
  const fade = Math.max(0, Math.min(options.audioFadeSeconds ?? 0.04, sourceDuration / 2, extensionDuration / 2))
  const outputTemp = tempPath(output, '.mp4')
  const timeout = options.timeoutMs ?? 180_000
  try {
    const args = ['-hide_banner', '-loglevel', 'error', '-y', '-i', source, '-i', generated]
    let nextInput = 2
    let sourceAudio = '0:a:0'
    let generatedAudio = '1:a:0'
    if (!sourceInfo.hasAudio) {
      args.push('-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000')
      sourceAudio = `${nextInput++}:a:0`
    }
    if (!generatedInfo.hasAudio) {
      args.push('-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000')
      generatedAudio = `${nextInput}:a:0`
    }
    const formatAudio = 'aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo'
    const sourceFade = fade > 0 ? `,afade=t=out:st=${Math.max(0, sourceDuration - fade)}:d=${fade}` : ''
    const extensionFade = fade > 0 ? `,afade=t=in:st=0:d=${fade}` : ''
    const filter = [
      `[0:v:0]fps=${options.fps},trim=start_frame=0:end_frame=${sourceFrames},setpts=PTS-STARTPTS,` +
        `${videoFilter(options.width, options.height)}[v0]`,
      `[1:v:0]fps=${options.fps},trim=start_frame=${options.overlapFrames}:end_frame=${generatedFrames},` +
        `setpts=PTS-STARTPTS,${videoFilter(options.width, options.height)}[v1]`,
      '[v0][v1]concat=n=2:v=1:a=0[v]',
      `[${sourceAudio}]atrim=start=0,asetpts=PTS-STARTPTS,${formatAudio},apad,` +
        `atrim=duration=${sourceDuration}${sourceFade}[a0]`,
      `[${generatedAudio}]atrim=start=${generatedInfo.hasAudio ? overlapDuration : 0},` +
        `asetpts=PTS-STARTPTS,${formatAudio},apad,atrim=duration=${extensionDuration}${extensionFade}[a1]`,
      '[a0][a1]concat=n=2:v=0:a=1[a]'
    ].join(';')
    args.push('-filter_complex', filter, '-map', '[v]', '-map', '[a]',
      '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', String(options.fps),
      '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', outputTemp)
    await runFile(options.ffmpegPath ?? 'ffmpeg', args, timeout)
    const result = await probeVideo(outputTemp, options)
    const expectedFrames = sourceFrames + extensionFrames
    if (result.width !== options.width || result.height !== options.height || !result.hasAudio ||
        result.frames !== undefined && Math.abs(result.frames - expectedFrames) > 1) {
      throw new Error('연결 영상의 크기, 소리 또는 프레임 수가 계획과 다릅니다.')
    }
    await publish(outputTemp, output)
    return result
  } catch (error) {
    await cleanup([outputTemp])
    throw error
  }
}

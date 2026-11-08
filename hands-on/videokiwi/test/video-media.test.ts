import { execFileSync } from 'node:child_process'
import { mkdtemp, rm, stat } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { concatenateExtendedVideo, extractExtensionGuide, probeVideo } from '../src/server/video-media.js'

const directories: string[] = []

async function directory(): Promise<string> {
  const value = resolve(await mkdtemp(join(tmpdir(), 'videokiwi-media-')))
  directories.push(value)
  return value
}

function makeClip(path: string, color: string, seconds: number, audio = true, fps = 24): void {
  const args = ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
    `color=c=${color}:s=320x192:r=${fps}:d=${seconds}`]
  if (audio) args.push('-f', 'lavfi', '-i', `sine=frequency=${color === 'red' ? 440 : 660}:sample_rate=48000:d=${seconds}`)
  args.push('-c:v', 'libx264', '-pix_fmt', 'yuv420p')
  if (audio) args.push('-c:a', 'aac', '-shortest')
  args.push(path)
  execFileSync('ffmpeg', args, { windowsHide: true, timeout: 30_000 })
}

afterEach(async () => {
  while (directories.length) {
    const value = directories.pop()!
    if (value.startsWith(resolve(tmpdir()) + '\\') || value.startsWith(resolve(tmpdir()) + '/')) {
      await rm(value, { recursive: true, force: true })
    }
  }
})

describe('영상 확장 미디어 처리', () => {
  it('마지막 22프레임 가이드와 끝 프레임을 추출함', async () => {
    const root = await directory()
    const source = join(root, 'source.mp4')
    const guide = join(root, 'guide.mp4')
    makeClip(source, 'red', 2)

    const sourceInfo = await probeVideo(source)
    expect(sourceInfo).toMatchObject({ width: 320, height: 192, fps: 24, frames: 48, hasAudio: true })
    const result = await extractExtensionGuide(source, guide, {
      guideFrames: 22, fps: 24, width: 320, height: 192
    })
    expect(result).toMatchObject({ guidePath: guide, guideFrames: 22, duration: 22 / 24 })
    expect(result.lastFramePath).toBe(join(root, 'guide.last.png'))
    expect((await stat(result.lastFramePath)).size).toBeGreaterThan(100)
    await expect(probeVideo(guide)).resolves.toMatchObject({
      width: 320, height: 192, fps: 24, frames: 22, hasAudio: true
    })
  }, 30_000)

  it('가이드 중복을 제거하고 크기와 소리를 정규화해 이어 붙임', async () => {
    const root = await directory()
    const source = join(root, 'source.mp4')
    const generated = join(root, 'generated.mp4')
    const combined = join(root, 'combined.mp4')
    makeClip(source, 'red', 2, true, 30)
    makeClip(generated, 'blue', 2, false)

    await expect(probeVideo(source)).resolves.toMatchObject({ fps: 30, frames: 60 })

    const result = await concatenateExtendedVideo(source, generated, combined, {
      overlapFrames: 22, fps: 24, width: 320, height: 192
    })
    expect(result).toMatchObject({ width: 320, height: 192, fps: 24, frames: 74, hasAudio: true })
    expect(result.duration).toBeCloseTo(74 / 24, 1)
    await expect(concatenateExtendedVideo(source, generated, combined, {
      overlapFrames: 22, fps: 24, width: 320, height: 192
    })).rejects.toThrow('이미')
  }, 30_000)

  it('짧은 원본은 22프레임을 거부하고 H3 최소 5프레임 가이드는 허용함', async () => {
    const root = await directory()
    const source = join(root, 'short.mp4')
    makeClip(source, 'red', 0.5)
    await expect(extractExtensionGuide(source, join(root, 'guide22.mp4'), {
      guideFrames: 22, fps: 24, width: 320, height: 192
    })).rejects.toThrow('22프레임 이상')
    await expect(extractExtensionGuide(source, join(root, 'guide5.mp4'), {
      guideFrames: 5, fps: 24, width: 320, height: 192
    })).resolves.toMatchObject({ guideFrames: 5, duration: 5 / 24 })
  }, 30_000)
})

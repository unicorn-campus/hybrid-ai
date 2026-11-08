// Explicit GPU integration test. Never included in npm test or browser fixture tests.
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { resolve, join } from 'node:path'
import { homedir } from 'node:os'
import { spawnSync } from 'node:child_process'

const base = process.env.VIDEOKIWI_URL || 'http://127.0.0.1:3010'
const mode = process.argv.includes('--text') ? 'text' : 'image'
const verifyProgress = process.argv.includes('--progress')
const directory = resolve('test-results', `gpu-${mode}-${Date.now()}`)
await mkdir(directory, { recursive: true })
const record = { startedAt: new Date().toISOString(), mode, engine: undefined, jobId: undefined, verified: false }
const persist = () => writeFile(join(directory, 'verification.json'), JSON.stringify(record, null, 2))
async function json(path, init) {
  const response = await fetch(base + path, { ...init, signal: AbortSignal.timeout(45_000) })
  const data = await response.json()
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`)
  return data
}
try {
  const engine = await json('/api/engine')
  record.engine = engine
  if (!engine.connected || !engine.modelReady) throw new Error('로컬 H3 모델 준비가 필요합니다.')
  if (engine.queueRunning || engine.queuePending) throw new Error('기존 엔진 작업이 있어 새 시험을 제출하지 않았습니다.')
  let image
  if (mode === 'image') {
    const imagePath = process.env.VIDEOKIWI_TEST_IMAGE || join(homedir(), 'AI/H3-Local/generation-frame-000.png')
    const form = new FormData()
    form.append('image', new Blob([await readFile(imagePath)], { type: 'image/png' }), 'gpu-cat-reference.png')
    image = await json('/api/images', { method: 'POST', body: form })
  }
  const input = {
    mode, prompt: mode === 'image'
      ? 'The orange cat from the starting image slowly turns its head toward the camera and blinks once. Preserve the cat, windowsill, natural daylight and background. One continuous shot.'
      : 'A small orange cat sits beside a sunlit window and slowly turns its head toward the camera. Realistic fur, gentle daylight. One continuous shot.',
    imageId: image?.id, imageDescription: image ? 'An orange cat sits on a windowsill, facing right, with soft daylight and green foliage outside.' : undefined,
    audio: 'Quiet indoor ambience and one soft meow. No music or speech.',
    duration: 5, resolution: 'preview', aspectRatio: 'auto', camera: 'static', profile: 'fast', seed: 42, optimize: process.argv.includes('--suggest')
  }
  record.input = input
  const job = await json('/api/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) })
  record.jobId = job.id
  record.progressSamples = []
  await persist()
  console.log(`GPU ${mode} test submitted: ${job.id}\nEvidence: ${directory}`)
  for (let attempt = 0; attempt < 300; attempt++) {
    const current = (await json('/api/jobs')).find(item => item.id === job.id)
    record.job = current
    if (current.progress != null || current.progressNode) {
      const sample = { at: current.progressUpdatedAt, stage: current.stage, node: current.progressNode,
        kind: current.progressKind, percent: current.progress, value: current.progressValue, max: current.progressMax,
        connected: current.progressConnected }
      if (JSON.stringify(sample) !== JSON.stringify(record.progressSamples.at(-1))) record.progressSamples.push(sample)
    }
    await persist()
    if (attempt % 6 === 0) console.log(`${current.status}: ${current.stage}; ${current.elapsedSeconds ?? 0}s`)
    if (current.status === 'completed') {
      const response = await fetch(base + current.videoUrl, { signal: AbortSignal.timeout(120_000) })
      if (!response.ok) throw new Error(`영상 다운로드 실패 (${response.status})`)
      const videoPath = join(directory, 'generated.mp4')
      await writeFile(videoPath, new Uint8Array(await response.arrayBuffer()))
      const probe = spawnSync('ffprobe', ['-v', 'error', '-show_streams', '-show_format', '-of', 'json', videoPath],
        { encoding: 'utf8', windowsHide: true, timeout: 30_000 })
      if (probe.status !== 0) throw new Error(`ffprobe 실패: ${probe.stderr}`)
      record.media = JSON.parse(probe.stdout)
      const stream = record.media.streams.find(item => item.codec_type === 'video')
      const audio = record.media.streams.find(item => item.codec_type === 'audio')
      if (!stream || !audio || stream.width !== current.plan.width || stream.height !== current.plan.height) {
        throw new Error('출력 영상의 해상도 또는 음성 스트림이 실행 계획과 다릅니다.')
      }
      const duration = Number(record.media.format.duration)
      if (Math.abs(duration - current.plan.actualDuration) > 0.15) throw new Error('실제 영상 길이가 계획과 다릅니다.')
      for (const [name, seconds] of [['first', 0], ['middle', duration / 2], ['last', duration - 0.15]]) {
        const extract = spawnSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-ss', String(seconds), '-i', videoPath,
          '-frames:v', '1', join(directory, `${name}.png`)], { encoding: 'utf8', windowsHide: true, timeout: 30_000 })
        if (extract.status !== 0) throw new Error(`프레임 추출 실패: ${extract.stderr}`)
      }
      if (verifyProgress && !record.progressSamples.some(sample => sample.kind === 'sampling' && sample.value > 0 && sample.max === 8)) {
        throw new Error('실제 샘플링 단계의 진행률을 수신하지 못했습니다.')
      }
      record.verified = true
      record.finishedAt = new Date().toISOString()
      await persist()
      console.log(`VERIFIED: ${stream.width}x${stream.height}, ${duration}s, ${stream.codec_name} + ${audio.codec_name}, ${current.elapsedSeconds}s elapsed`)
      break
    }
    if (['failed', 'interrupted', 'canceled'].includes(current.status)) throw new Error(current.error || current.status)
    if (attempt === 299) throw new Error('20분 대기 상한에 도달했습니다. 엔진 작업은 유지하고 자동 재제출하지 않습니다.')
    await new Promise(resolve => setTimeout(resolve, 4000))
  }
} catch (error) {
  record.error = error.message
  await persist()
  console.error(error.message)
  process.exitCode = 1
}

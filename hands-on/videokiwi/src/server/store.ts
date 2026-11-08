import { mkdir, readFile, rename, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import type { ExtensionSource, ImageAsset, VideoJob } from '../shared/types.js'

export interface StoredAsset extends ImageAsset { file: string }
export interface StoredExtensionSource extends ExtensionSource { file: string; guideFile: string; hasAudio: boolean }
interface State { version: 1; jobs: VideoJob[]; assets: StoredAsset[]; extensionSources: StoredExtensionSource[] }

export function displayImageName(name: string): string {
  if (!/[\u0080-\u00ff]/u.test(name) || [...name].some(char => char.charCodeAt(0) > 255)) return name
  try { return new TextDecoder('utf-8', { fatal: true }).decode(Buffer.from(name, 'latin1')) }
  catch { return name }
}

export class Store {
  state: State = { version: 1, jobs: [], assets: [], extensionSources: [] }
  private pending: Promise<void> = Promise.resolve()
  constructor(readonly directory: string) {}
  async open() {
    await mkdir(join(this.directory, 'images'), { recursive: true })
    await mkdir(join(this.directory, 'videos'), { recursive: true })
    try {
      const parsed = JSON.parse(await readFile(join(this.directory, 'state.json'), 'utf8'))
      if (parsed.version !== 1 || !Array.isArray(parsed.jobs) || !Array.isArray(parsed.assets)) {
        throw new Error('저장된 작업 기록 형식을 확인해 주세요.')
      }
      this.state = { ...parsed, extensionSources: Array.isArray(parsed.extensionSources) ? parsed.extensionSources : [] }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
    }
  }
  save(): Promise<void> {
    const contents = JSON.stringify(this.state, null, 2)
    this.pending = this.pending.catch(() => {}).then(async () => {
      const target = join(this.directory, 'state.json')
      await writeFile(`${target}.tmp`, contents, { encoding: 'utf8', mode: 0o600 })
      for (let attempt = 0; ; attempt++) {
        try { await rename(`${target}.tmp`, target); break }
        catch (error) {
          if (attempt >= 3 || !['EPERM', 'EBUSY'].includes((error as NodeJS.ErrnoException).code || '')) throw error
          await new Promise(resolve => setTimeout(resolve, 40 * (attempt + 1)))
        }
      }
    })
    return this.pending
  }
  asset(id: string | undefined): StoredAsset | undefined {
    return id ? this.state.assets.find(asset => asset.id === id) : undefined
  }
  extensionSource(id: string | undefined): StoredExtensionSource | undefined {
    return id ? this.state.extensionSources.find(source => source.id === id) : undefined
  }
  job(id: string): VideoJob {
    const job = this.state.jobs.find(item => item.id === id)
    if (!job) throw Object.assign(new Error('작업을 찾을 수 없습니다.'), { status: 404 })
    return job
  }
  jobs(): VideoJob[] {
    return [...this.state.jobs].reverse().map(job => ({ ...job,
      image: job.image && { ...job.image, name: displayImageName(job.image.name) },
      endImage: job.endImage && { ...job.endImage, name: displayImageName(job.endImage.name) }
    }))
  }
}

import type { VideoKiwiAPI, VideoJob, ImageAsset } from '../../shared/types'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const controller = new AbortController()
  const suggestionRequest = path === '/api/prompt/optimize' || path === '/api/jobs' && options?.method === 'POST'
    || path === '/api/videos' || path.endsWith('/extension')
  const timeout = window.setTimeout(() => controller.abort(), suggestionRequest ? 160_000 : 40_000)
  try {
    const response = await fetch(path, { ...options, signal: controller.signal })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new Error(body.error || `요청 실패 (${response.status})`)
    }
    return response.status === 204 ? undefined as T : await response.json()
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw new Error('서버 응답을 기다리는 시간이 초과되었습니다. 제출한 작업은 기록에서 확인해 주세요.')
    throw error
  } finally { window.clearTimeout(timeout) }
}
const post = <T>(path: string, value?: unknown) => request<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value || {}) })
async function importImage(file: { name: string; bytes: ArrayBuffer }): Promise<ImageAsset> {
  const form = new FormData()
  form.append('image', new Blob([file.bytes]), file.name)
  return request('/api/images', { method: 'POST', body: form })
}
function download(path: string) {
  const link = document.createElement('a')
  link.href = path
  link.download = ''
  document.body.append(link)
  link.click()
  link.remove()
}
export const api: VideoKiwiAPI = {
  bootstrap: () => request('/api/bootstrap'),
  engineStatus: () => request('/api/engine'),
  chooseImage: () => new Promise((resolve, reject) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/png,image/jpeg,image/webp'
    input.oncancel = () => resolve(null)
    input.onchange = async () => {
      const file = input.files?.[0]
      if (!file) { resolve(null); return }
      // The UI uses its own file input so upload failures remain visible to the caller.
      try { resolve(await importImage({ name: file.name, bytes: await file.arrayBuffer() })) }
      catch (error) { reject(error) }
    }
    input.click()
  }),
  importImage,
  prepareExtension: id => post(`/api/jobs/${encodeURIComponent(id)}/extension`),
  importVideo: file => {
    const form = new FormData()
    form.append('video', new Blob([file.bytes]), file.name)
    return request('/api/videos', { method: 'POST', body: form })
  },
  createJob: input => post('/api/jobs', input),
  optimizePrompt: input => post('/api/prompt/optimize', input),
  refreshJob: id => post(`/api/jobs/${encodeURIComponent(id)}/refresh`),
  cancelJob: id => post(`/api/jobs/${encodeURIComponent(id)}/cancel`),
  deleteJob: id => request(`/api/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  renameJob: (id, title) => request(`/api/jobs/${encodeURIComponent(id)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title })
  }),
  saveVideo: async id => { download(`/api/jobs/${encodeURIComponent(id)}/video?download=1`); return '브라우저 다운로드' },
  exportRecipe: async id => { download(`/api/jobs/${encodeURIComponent(id)}/recipe`) },
  onJobsChanged: callback => {
    let stopped = false
    const source = new EventSource('/api/events')
    source.onmessage = event => { try { callback(JSON.parse(event.data) as VideoJob[]) } catch { /* reconnect supplies next snapshot */ } }
    const fallback = window.setInterval(() => {
      if (source.readyState !== EventSource.OPEN) void request<VideoJob[]>('/api/jobs')
        .then(jobs => { if (!stopped) callback(jobs) }).catch(() => {})
    }, 5000)
    return () => { stopped = true; source.close(); window.clearInterval(fallback) }
  }
}

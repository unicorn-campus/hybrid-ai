export type GenerationMode = 'text' | 'image'
export type JobStatus = 'uploading' | 'queued' | 'in_progress' | 'completed' | 'failed' | 'canceled' | 'interrupted'
export type AspectRatio = 'auto' | '16:9' | '9:16' | '1:1' | '4:3' | '3:4' | '21:9'
export type PerformanceProfile = 'fast' | 'balanced' | 'quality'
export interface ImageAsset {
  id: string
  name: string
  previewUrl: string
  size: number
  mime: string
  width: number
  height: number
  brightness?: number
  dominantColor?: string
}
export interface GenerationInput {
  mode: GenerationMode
  prompt: string
  duration: number
  resolution: 'preview' | 'standard'
  aspectRatio: AspectRatio
  imageId?: string
  endImageId?: string
  camera: 'none' | 'push-in' | 'pull-out' | 'orbit' | 'pan-left' | 'static'
  profile: PerformanceProfile
  seed: number
  originalPrompt?: string
  imageDescription?: string
  audio?: string
  optimize?: boolean
  extensionSourceId?: string
}
export interface ExtensionSource {
  id: string
  name: string
  videoUrl: string
  image: ImageAsset
  width: number
  height: number
  duration: number
  fps: number
  guideFrames: number
  sourceJobId?: string
}
export interface ExecutionPlan {
  width: number; height: number; frames: number; fps: number; steps: number
  sampler: string; turbo: boolean; actualDuration: number; warnings: string[]
}
export interface PromptOptimization {
  original: string
  optimized: string
  method: 'local-rules' | 'claude-agent-sdk'
  model?: string
  authentication?: 'claude-subscription'
  notes: string[]
  checks: { label: string; passed: boolean; detail: string }[]
  imageFacts?: { width: number; height: number; brightness?: number; dominantColor?: string }
}
export interface EngineStatus {
  connected: boolean
  endpoint: string
  modelReady: boolean
  turboAvailable: boolean
  extensionAvailable?: boolean
  gpu?: string
  vramTotalMB?: number
  vramFreeMB?: number
  queueRunning: number
  queuePending: number
  error?: string
}
export interface VideoJob {
  id: string
  requestId?: string
  createdAt: string
  updatedAt: string
  status: JobStatus
  input: GenerationInput
  image?: ImageAsset
  endImage?: ImageAsset
  videoUrl?: string
  localPath?: string
  error?: string
  plan?: ExecutionPlan
  optimization?: PromptOptimization
  elapsedSeconds?: number
  submittedAt?: string
  completedAt?: string
  progress?: number
  progressKind?: 'sampling' | 'decode' | 'node'
  progressNode?: string
  progressValue?: number
  progressMax?: number
  progressUpdatedAt?: string
  progressConnected?: boolean
  stage?: string
  warnings?: string[]
  extension?: {
    sourceId: string
    sourceJobId?: string
    sourceDuration: number
    overlapFrames: number
    addedDuration?: number
    totalDuration?: number
  }
}
export interface EngineProgress {
  promptId: string
  stage: string
  node?: string
  kind: 'sampling' | 'decode' | 'node' | 'complete' | 'disconnected'
  percent?: number
  value?: number
  max?: number
  connected: boolean
  updatedAt: string
}
export interface AppSettings {
  engine: EngineStatus
  dataDirectory: string
  promptAssistant?: PromptAssistantStatus
}
export interface PromptAssistantStatus {
  provider: 'claude-agent-sdk'
  model: string
  authentication: 'claude-subscription'
  available: boolean
  error?: string
}
export interface BootstrapData { settings: AppSettings; jobs: VideoJob[] }
export interface VideoKiwiAPI {
  bootstrap(): Promise<BootstrapData>
  chooseImage(): Promise<ImageAsset | null>
  importImage(file: { name: string; bytes: ArrayBuffer }): Promise<ImageAsset>
  prepareExtension(id: string): Promise<ExtensionSource>
  importVideo(file: { name: string; bytes: ArrayBuffer }): Promise<ExtensionSource>
  createJob(input: GenerationInput): Promise<VideoJob>
  optimizePrompt(input: GenerationInput): Promise<PromptOptimization>
  engineStatus(): Promise<EngineStatus>
  refreshJob(id: string): Promise<VideoJob>
  cancelJob(id: string): Promise<VideoJob>
  deleteJob(id: string): Promise<void>
  saveVideo(id: string): Promise<string | null>
  exportRecipe(id: string): Promise<void>
  onJobsChanged(callback: (jobs: VideoJob[]) => void): () => void
}
export const CAMERA_PROMPTS: Record<GenerationInput['camera'], string> = {
  none: '',
  'push-in': 'Slow cinematic camera push-in toward the subject.',
  'pull-out': 'Slow camera pull-out revealing the environment.',
  orbit: 'Smooth cinematic camera orbit around the subject.',
  'pan-left': 'Slow cinematic camera pan to the left.',
  static: 'Locked-off static camera. Only the subject moves.'
}
export const TERMINAL_STATUSES: JobStatus[] = ['completed', 'failed', 'canceled', 'interrupted']

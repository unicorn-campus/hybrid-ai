import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Aperture, ArrowDownToLine, BookOpen, Check, ChevronDown, CircleAlert, CircleStop,
  Clapperboard, Clock3, Download, FileJson2, Film, Gauge, ImagePlus, Images, Info,
  Library, LoaderCircle, Menu, MonitorCog, MoreHorizontal, Play, Plus, RefreshCw,
  RotateCcw, Search, Settings2, Sparkles, Trash2, Upload, WandSparkles, X, Zap
} from 'lucide-react'
import { api } from './api'
import type {
  AppSettings, AspectRatio, EngineStatus, ExtensionSource, GenerationInput, ImageAsset, JobStatus,
  PerformanceProfile, PromptOptimization, VideoJob
} from '../../shared/types'

type View = 'create' | 'library' | 'engine'
type ComposeMode = 'create' | 'extend'
type Toast = { id: number; kind: 'success' | 'error' | 'info'; message: string }

const DEFAULT_INPUT: GenerationInput = {
  mode: 'image', prompt: '', duration: 5, resolution: 'preview', aspectRatio: 'auto',
  camera: 'none', profile: 'balanced', seed: 42, optimize: false
}
const CAMERA_OPTIONS: Array<{ value: GenerationInput['camera']; label: string }> = [
  { value: 'none', label: '직접 설명' }, { value: 'push-in', label: '천천히 접근' },
  { value: 'pull-out', label: '공간 드러내기' }, { value: 'orbit', label: '피사체 회전' },
  { value: 'pan-left', label: '왼쪽 패닝' }, { value: 'static', label: '고정 카메라' }
]
const PROFILE_META: Record<PerformanceProfile, { label: string; note: string }> = {
  fast: { label: '빠르게', note: '낮은 반복 수로 초안 확인' },
  balanced: { label: '균형', note: '속도와 세부 표현의 균형' },
  quality: { label: '고품질', note: '더 많은 반복으로 품질 비교' }
}
const STATUS_META: Record<JobStatus, { label: string; tone: string }> = {
  uploading: { label: '준비 중', tone: 'muted' }, queued: { label: '대기 중', tone: 'waiting' },
  in_progress: { label: '생성 중', tone: 'active' }, completed: { label: '완료', tone: 'success' },
  failed: { label: '실패', tone: 'danger' }, canceled: { label: '취소됨', tone: 'muted' },
  interrupted: { label: '확인 필요', tone: 'danger' }
}
const EXAMPLES = [
  '창가에 선 인물이 천천히 고개를 돌립니다. 머리카락이 바람에 가볍게 흔들립니다.',
  '제품은 제자리에 고정되고, 부드러운 빛이 왼쪽에서 오른쪽으로 지나갑니다.',
  '잔잔한 호수의 물결이 움직이고 카메라는 풍경 안으로 천천히 다가갑니다.'
]

function errorText(error: unknown) { return error instanceof Error ? error.message : '알 수 없는 오류가 발생했습니다.' }
function formatDate(value: string) {
  return new Intl.DateTimeFormat('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}
function formatDuration(seconds?: number) {
  if (seconds == null) return '—'
  if (seconds < 60) return `${Math.round(seconds)}초`
  return `${Math.floor(seconds / 60)}분 ${Math.round(seconds % 60)}초`
}
function modelLabel(model?: string) {
  const value = model || 'claude-opus-5-5'
  if (/opus[-_ .]?5[-_ .]?5/i.test(value)) return 'Opus 5.5'
  return value
}
function progressSnapshot(job: VideoJob) {
  const connected = job.progressConnected !== false
  const hasProgress = connected && Number.isFinite(job.progress)
  const percent = hasProgress ? Math.max(0, Math.min(100, Number(job.progress))) : undefined
  const stage = job.stage || (job.status === 'queued' ? '실행 대기' : '영상 생성')
  const hasCount = Number.isFinite(job.progressValue) && Number.isFinite(job.progressMax) && Number(job.progressMax) > 0
  let detail: string
  if (!connected) detail = '실시간 연결 대기, 작업 상태는 확인 중'
  else if (hasCount && job.progressKind === 'sampling') detail = `샘플링 ${job.progressValue} / ${job.progressMax} 단계${percent == null ? '' : ` · ${Math.round(percent)}%`}`
  else if (hasCount) detail = `${job.progressValue} / ${job.progressMax}${percent == null ? '' : ` · ${Math.round(percent)}%`}`
  else if (percent != null) detail = `현재 단계 ${Math.round(percent)}%`
  else if (job.status === 'queued') detail = '실행 순서를 기다리는 중'
  else if (job.elapsedSeconds != null) detail = `${formatDuration(job.elapsedSeconds)} 경과`
  else detail = stage
  return { stage, detail, percent, connected }
}
function imageAccepts(file: File) { return ['image/png', 'image/jpeg', 'image/webp'].includes(file.type) && file.size <= 10 * 1024 * 1024 }
function videoAccepts(file: File) {
  return file.size <= 250 * 1024 * 1024 &&
    (['video/mp4', 'video/quicktime', 'video/webm'].includes(file.type) || /\.(mp4|mov|webm)$/i.test(file.name))
}

function Logo() {
  return <div className="logo-mark" aria-hidden="true"><span>V</span><i /></div>
}

function EnginePill({ engine }: { engine?: EngineStatus }) {
  const ready = Boolean(engine?.connected && engine.modelReady)
  return (
    <div className={`engine-pill ${ready ? 'ready' : ''}`} title={engine?.error || engine?.endpoint || '연결 확인 중'}>
      <span className="status-dot" />
      <span>{ready ? 'H3 준비됨' : engine?.connected ? '모델 준비 중' : '엔진 연결 안 됨'}</span>
    </div>
  )
}

function EmptyScene() {
  return (
    <div className="empty-scene" aria-label="생성할 영상을 기다리는 빈 미리보기">
      <div className="scene-grid" />
      <div className="orb orb-one" /><div className="orb orb-two" />
      <div className="scene-frame">
        <div className="scene-kicker"><Sparkles size={13} /> LOCAL CREATION</div>
        <h2>첫 장면을<br />움직여 보세요.</h2>
        <p>이미지와 움직임을 정하면<br />MiniMax H3가 로컬에서 영상을 만듭니다.</p>
      </div>
      <div className="frame-corner corner-a" /><div className="frame-corner corner-b" />
    </div>
  )
}

function AssetSlot({ title, optional, asset, onPick, onClear, onDrop, disabled }: {
  title: string; optional?: boolean; asset?: ImageAsset; onPick(): void; onClear(): void;
  onDrop(file: File): void; disabled?: boolean
}) {
  const [dragging, setDragging] = useState(false)
  return (
    <div className={`asset-slot ${asset ? 'has-image' : ''} ${dragging ? 'dragging' : ''}`}
      onDragOver={event => { event.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={event => {
        event.preventDefault(); setDragging(false)
        const file = event.dataTransfer.files[0]; if (file) onDrop(file)
      }}>
      {asset ? <img src={asset.previewUrl} alt={`${title}: ${asset.name}`} /> : <ImagePlus size={22} aria-hidden="true" />}
      <button type="button" className="asset-click" onClick={onPick} disabled={disabled} aria-label={`${title} 선택`} />
      <div className="asset-label"><b>{title}</b><span>{asset ? `${asset.width} × ${asset.height}` : optional ? '선택 사항' : '이미지 선택'}</span></div>
      {asset && <button className="asset-remove" onClick={event => { event.stopPropagation(); onClear() }} aria-label={`${title} 제거`}><X size={14} /></button>}
    </div>
  )
}

function Segment<T extends string | number>({ value, options, onChange, label }: {
  value: T; options: Array<{ value: T; label: string }>; onChange(value: T): void; label: string
}) {
  return <div className="segment" role="group" aria-label={label}>{options.map(option => (
    <button type="button" key={option.value} className={value === option.value ? 'active' : ''}
      onClick={() => onChange(option.value)}>{option.label}</button>
  ))}</div>
}

function PromptReview({ result, value, onChange, onClose }: {
  result: PromptOptimization; value: string; onChange(value: string): void; onClose(): void
}) {
  const claude = result.method === 'claude-agent-sdk'
  const provider = claude
    ? `Claude Agent SDK · ${modelLabel(result.model)} · Claude 구독`
    : '로컬 규칙 기반 제안'
  return (
    <section className="prompt-review" aria-labelledby="review-title">
      <header><div><span className="eyebrow">{provider}</span><h3 id="review-title">제안 프롬프트 검토</h3></div>
        <button className="icon-button" onClick={onClose} aria-label="검토 영역 닫기"><X size={17} /></button></header>
      <textarea value={value} onChange={event => onChange(event.target.value)} rows={7} aria-label="다듬은 프롬프트" />
      <div className="review-note"><Info size={14} /><span>다음 영상 만들기에 이 제안문이 적용됩니다. 직접 수정할 수 있습니다. 제안만 요청하면 영상은 생성되지 않습니다.</span></div>
      {result.notes.length > 0 && <ul className="suggestion-notes">{result.notes.map(note => <li key={note}>{note}</li>)}</ul>}
      <button className="restore-prompt" type="button" onClick={() => onChange(result.original)}><RotateCcw size={12} />원문으로 되돌리기</button>
      <div className="check-row">{result.checks.map(check => <span key={check.label} className={check.passed ? 'passed' : ''} title={check.detail}>
        {check.passed ? <Check size={12} /> : <CircleAlert size={12} />}{check.label}
      </span>)}</div>
    </section>
  )
}

function ComposePanel({ composeMode, input, setInput, image, endImage, extensionSource, completedJobs,
  onComposeMode, onSelectExtension, onVideo, onImage, onEndImage, onClearImage, onClearEndImage,
  onOptimize, optimization, optimizedText, setOptimizedText, clearOptimization, onCreate, submitting, optimizing, engineReady,
  uploadBusy, extensionBusy, extensionAvailable, promptAssistant }: {
  composeMode: ComposeMode; extensionSource?: ExtensionSource; completedJobs: VideoJob[];
  input: GenerationInput; setInput(value: GenerationInput): void; image?: ImageAsset; endImage?: ImageAsset;
  onComposeMode(value: ComposeMode): void; onSelectExtension(jobId: string): void; onVideo(file: File): void;
  onImage(file: File): void; onEndImage(file: File): void; onClearImage(): void; onClearEndImage(): void;
  onOptimize(): void; optimization?: PromptOptimization; optimizedText: string; setOptimizedText(value: string): void;
  clearOptimization(): void; onCreate(): void; submitting: boolean; optimizing: boolean; engineReady: boolean; uploadBusy: boolean;
  extensionBusy: boolean; extensionAvailable: boolean;
  promptAssistant?: AppSettings['promptAssistant']
}) {
  const fileRef = useRef<HTMLInputElement>(null), endFileRef = useRef<HTMLInputElement>(null), videoRef = useRef<HTMLInputElement>(null)
  const promptValue = input.prompt
  const sourceReady = composeMode === 'create' ? input.mode === 'text' || Boolean(image) : Boolean(extensionSource)
  const canGenerate = promptValue.trim().length > 0 && sourceReady && engineReady && !submitting && !uploadBusy && !extensionBusy && !optimizing
  const change = (patch: Partial<GenerationInput>, invalidate = false) => {
    setInput({ ...input, ...patch })
    if (invalidate) clearOptimization()
  }
  const receive = (event: React.ChangeEvent<HTMLInputElement>, handler: (file: File) => void) => {
    const file = event.target.files?.[0]; if (file) handler(file); event.target.value = ''
  }
  return (
    <aside className="compose-panel">
      <div className="compose-scroll">
        <div className="panel-heading"><div><span className="eyebrow">MINIMAX H3 LOCAL</span><h2>{composeMode === 'extend' ? '영상 이어 만들기' : '새 영상'}</h2></div><Clapperboard size={19} /></div>
        <Segment label="작업 방식" value={composeMode} onChange={onComposeMode}
          options={[{ value: 'create', label: '새 영상' }, { value: 'extend', label: '영상 이어 만들기' }]} />
        {composeMode === 'extend' ? <section className="extension-source" aria-label="이어 만들 원본 영상">
          <input ref={videoRef} hidden type="file" accept="video/mp4,video/quicktime,video/webm,.mov"
            onChange={event => receive(event, onVideo)} />
          <label className="field-label" htmlFor="extension-job">원본 영상</label>
          <select id="extension-job" value={extensionSource?.sourceJobId || ''}
            onChange={event => event.target.value && onSelectExtension(event.target.value)} disabled={extensionBusy}>
            <option value="">완료 영상에서 선택</option>
            {completedJobs.map(job => <option value={job.id} key={job.id}>{formatDate(job.createdAt)} · {(job.input.originalPrompt || job.input.prompt).slice(0, 38)}</option>)}
          </select>
          <div className="or-divider"><span>또는</span></div>
          <button type="button" className="video-upload-button" onClick={() => videoRef.current?.click()}
            disabled={extensionBusy || !extensionAvailable}>
            {extensionBusy ? <LoaderCircle className="spin" size={16} /> : <Upload size={16} />}
            {extensionBusy ? '영상을 준비하고 있어요' : '내 영상 불러오기'}
          </button>
          <p className="field-hint">MP4, MOV, WebM, 최대 250MB와 5분</p>
          {extensionSource ? <div className="extension-preview">
            <video src={extensionSource.videoUrl} controls preload="metadata" />
            <div><b>{extensionSource.name}</b><span>{extensionSource.width} × {extensionSource.height} · {formatDuration(extensionSource.duration)}</span></div>
          </div> : <div className="extension-empty"><Film /><b>뒤에 이어 만들 영상을 선택해 주세요.</b><span>완료된 영상이나 내 컴퓨터의 영상을 사용할 수 있습니다.</span></div>}
          {extensionSource && <div className="extension-timeline" aria-label="예상 영상 길이">
            <div><span>원본</span><b>{formatDuration(extensionSource.duration)}</b></div><i />
            <div><span>추가</span><b>약 {input.duration}초</b></div><i />
            <div><span>예상 합본</span><b>약 {formatDuration(extensionSource.duration + input.duration)}</b></div>
          </div>}
          {!extensionAvailable && <div className="inline-warning"><CircleAlert size={14} />현재 H3 엔진에서 영상 가이드 기능을 찾을 수 없습니다.</div>}
          <p className="extension-note"><Info size={13} />원본 끝부분의 움직임을 참고해 다음 장면을 만들고, 겹치는 구간을 제거해 하나의 영상으로 합칩니다.</p>
        </section> : <>
          <Segment label="생성 방식" value={input.mode} onChange={mode => change({ mode, extensionSourceId: undefined }, true)}
            options={[{ value: 'image', label: '이미지에서' }, { value: 'text', label: '텍스트에서' }]} />
        {input.mode === 'image' && <>
          <input ref={fileRef} hidden type="file" accept="image/png,image/jpeg,image/webp" onChange={e => receive(e, onImage)} />
          <div className="asset-grid">
            <AssetSlot title="시작 장면" asset={image} onPick={() => fileRef.current?.click()} onDrop={onImage}
              onClear={onClearImage} disabled={uploadBusy} />
            <AssetSlot title="끝 장면" optional asset={endImage} onPick={() => endFileRef.current?.click()} onDrop={onEndImage}
              onClear={onClearEndImage} disabled={uploadBusy} />
          </div>
          <p className="field-hint"><Upload size={13} /> PNG, JPG, WebP, 최대 10MB</p>
          <label className="field-label" htmlFor="image-description">이미지 내용 <span>선택 사항</span></label>
          <input id="image-description" className="text-input" value={input.imageDescription || ''}
            onChange={e => change({ imageDescription: e.target.value }, true)}
            placeholder="예: 노을 아래 서 있는 인물" />
        </>}</>}
        <input ref={endFileRef} hidden type="file" accept="image/png,image/jpeg,image/webp" onChange={e => receive(e, onEndImage)} />
        {composeMode === 'extend' && extensionSource && <><label className="field-label">마지막 장면 <span>선택 사항</span></label>
          <AssetSlot title="마지막 장면" optional asset={endImage} onPick={() => endFileRef.current?.click()} onDrop={onEndImage}
            onClear={onClearEndImage} disabled={uploadBusy} /></>}
        <label className="field-label" htmlFor="prompt">{composeMode === 'extend' ? '다음 장면에서 무엇이 이어질까요?' : '어떻게 움직일까요?'}</label>
        <div className="prompt-field">
          <textarea id="prompt" value={promptValue} onChange={event => change({ prompt: event.target.value }, true)}
            rows={5} maxLength={3000} placeholder={composeMode === 'extend' ? '직전 움직임을 이어서 다음 장면을 설명해 주세요.' : '피사체의 움직임, 카메라, 빛과 분위기를 설명해 주세요.'} />
          <span>{promptValue.length}/3000</span>
        </div>
        {!promptValue && composeMode === 'create' && <div className="example-prompts">{EXAMPLES.map((example, index) => <button key={example} onClick={() => change({ prompt: example }, true)}>
          <span>0{index + 1}</span>{example}
        </button>)}</div>}
        <button type="button" className="optimize-button" onClick={onOptimize}
          disabled={optimizing || !promptValue.trim() || promptAssistant?.available === false}>
          {optimizing ? <LoaderCircle className="spin" size={17} /> : <WandSparkles size={17} />}
          {optimizing ? 'Claude가 제안문을 만들고 있어요' : `Claude ${modelLabel(promptAssistant?.model)}로 프롬프트 제안`}<span>구독 사용</span>
        </button>
        <div className="prompt-flow-note"><Sparkles size={13} /><span>{composeMode === 'extend' ? '원본 끝 장면과 설명을 Claude가 제안문으로 정리하고, 로컬 H3가 뒤 장면을 생성합니다.' : '이미지와 설명은 Claude가 제안문으로 정리하고, 영상은 로컬 MiniMax H3가 생성합니다.'}</span></div>
        {promptAssistant?.available === false && <div className="inline-warning"><CircleAlert size={14} />{promptAssistant.error || 'Claude 구독 로그인을 확인해 주세요.'}</div>}
        {optimization && <PromptReview result={optimization} value={optimizedText} onChange={setOptimizedText} onClose={clearOptimization} />}
        <div className="field-group"><div className="field-label">카메라 움직임</div><div className="chip-list">
          {CAMERA_OPTIONS.map(option => <button key={option.value} className={input.camera === option.value ? 'active' : ''}
            onClick={() => change({ camera: option.value }, true)}>{option.label}</button>)}
        </div></div>
        <label className="field-label" htmlFor="audio-description">소리와 대사 <span>선택 사항</span></label>
        <input id="audio-description" className="text-input" value={input.audio || ''}
          onChange={event => change({ audio: event.target.value }, true)}
          placeholder="예: 웅장한 기악 음악, 대사와 내레이션 없음" />
        <div className="field-group"><div className="field-label">실행 프로파일</div><div className="profile-grid">
          {(Object.keys(PROFILE_META) as PerformanceProfile[]).map(profile => <button key={profile}
            className={input.profile === profile ? 'active' : ''} onClick={() => setInput({ ...input, profile })}>
            {profile === 'fast' ? <Zap size={16} /> : profile === 'balanced' ? <Gauge size={16} /> : <Sparkles size={16} />}
            <b>{PROFILE_META[profile].label}</b><small>{PROFILE_META[profile].note}</small>
          </button>)}
        </div><p className="field-hint">프로파일은 처리량과 반복 수를 바꾸며, 품질 향상을 보장하지 않습니다.</p></div>
        <div className="two-fields"><div><div className="field-label">{composeMode === 'extend' ? '추가 길이' : '길이'}</div><Segment label={composeMode === 'extend' ? '추가 영상 길이' : '영상 길이'} value={input.duration}
          onChange={duration => setInput({ ...input, duration })} options={[5, 10, 15].map(value => ({ value, label: `${value}초` }))} /></div>
          <div><label className="field-label" htmlFor="ratio">화면비</label><select id="ratio" value={input.aspectRatio} disabled={composeMode === 'extend'}
            onChange={e => setInput({ ...input, aspectRatio: e.target.value as AspectRatio })}>
            {(['auto', '16:9', '9:16', '1:1', '4:3', '3:4', '21:9'] as AspectRatio[]).map(value => <option key={value} value={value}>{value === 'auto' ? '이미지에 맞춤' : value}</option>)}
          </select></div></div>
        <div className="two-fields"><div><div className="field-label">출력 크기</div>{composeMode === 'extend' ? <div className="locked-field"><Film />원본 크기 유지</div> : <Segment label="출력 크기" value={input.resolution}
          onChange={resolution => setInput({ ...input, resolution })} options={[{ value: 'preview', label: '미리보기' }, { value: 'standard', label: '표준' }]} />}</div>
          <div><label className="field-label" htmlFor="seed">시드</label><div className="seed-control"><input id="seed" type="number" min="0" max="2147483647" value={input.seed}
            onChange={e => setInput({ ...input, seed: Math.max(0, Math.min(2147483647, Number(e.target.value) || 0)) })} />
            <button onClick={() => setInput({ ...input, seed: Math.floor(Math.random() * 2_000_000_000) })} aria-label="시드 무작위 선택"><RotateCcw size={14} /></button></div></div></div>
        {!optimization && <label className="toggle-row"><input type="checkbox" checked={Boolean(input.optimize)}
          onChange={e => setInput({ ...input, optimize: e.target.checked })} disabled={promptAssistant?.available === false} /><span className="toggle" /><span><b>생성 전에 Claude로 제안받기</b><small>{modelLabel(promptAssistant?.model)} 모델과 Claude 구독 사용 한도가 적용됩니다.</small></span></label>}
      </div>
      <div className="compose-footer">
        {!engineReady && <div className="inline-warning"><CircleAlert size={15} />로컬 H3 엔진 연결 후 생성할 수 있습니다.</div>}
        <button className="generate-button" onClick={onCreate} disabled={!canGenerate}>
          {submitting ? <LoaderCircle className="spin" size={18} /> : <Sparkles size={18} />}
          {submitting ? '작업을 준비하고 있어요' : composeMode === 'extend' ? '이어서 만들기' : '영상 만들기'}
        </button>
      </div>
    </aside>
  )
}

function JobVisual({ job, large = false }: { job: VideoJob; large?: boolean }) {
  if (job.status === 'completed' && job.videoUrl) return <video src={job.videoUrl} controls={large} muted={!large} loop={!large} preload="metadata" />
  const progress = progressSnapshot(job)
  return <div className={`job-placeholder ${job.status}`} style={job.image ? { backgroundImage: `linear-gradient(180deg, transparent, rgba(0,0,0,.72)), url(${job.image.previewUrl})` } : undefined}>
    {(job.status === 'in_progress' || job.status === 'queued') && <div className="render-pulse"><LoaderCircle className="spin" /><b>{progress.stage}</b><span>{progress.detail}</span></div>}
    {['failed', 'interrupted'].includes(job.status) && <div className="render-pulse error"><CircleAlert /><b>{STATUS_META[job.status].label}</b></div>}
    {job.status === 'canceled' && <div className="render-pulse"><CircleStop /><b>취소됨</b></div>}
  </div>
}

function JobDetail({ job, onCancel, onDelete, onDownload, onRecipe, onRefresh, onReuse, onExtend, busy, extensionAvailable }: {
  job: VideoJob; onCancel(): void; onDelete(): void; onDownload(): void; onRecipe(): void;
  onRefresh(): void; onReuse(): void; onExtend(): void; busy: boolean; extensionAvailable: boolean
}) {
  const active = job.status === 'queued' || job.status === 'in_progress'
  const preparing = job.status === 'uploading'
  const progress = progressSnapshot(job)
  return (
    <div className="job-detail">
      <div className="preview-stage"><JobVisual job={job} large />
        <div className="preview-top"><span className={`status-badge ${STATUS_META[job.status].tone}`}><i />{STATUS_META[job.status].label}</span><span>MiniMax H3 Local</span></div>
        {active && progress.percent != null && <div className="progress-track" role="progressbar"
          aria-label={`${progress.stage}, ${progress.detail}. 현재 노드 진행률이며 전체 작업률이 아닙니다.`}
          aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress.percent)}>
          <i style={{ width: `${progress.percent}%` }} /></div>}
      </div>
      <div className="detail-content">
        <div className="detail-title"><div><span className="eyebrow">{formatDate(job.createdAt)}</span><h2>{job.input.originalPrompt || job.input.prompt}</h2></div>
          <div className="detail-actions">
            {active && <button className="secondary-button danger" onClick={onCancel} disabled={busy}><CircleStop size={15} />취소</button>}
            {job.status === 'interrupted' && <button className="secondary-button" onClick={onRefresh} disabled={busy}><RefreshCw size={15} />상태 다시 확인</button>}
            {job.status === 'completed' && <button className="secondary-button" onClick={onDownload}><Download size={15} />영상 저장</button>}
            {job.status === 'completed' && <button className="secondary-button extend-button" onClick={onExtend}
              disabled={busy || !extensionAvailable} title={extensionAvailable ? '이 영상의 뒤 장면을 만듭니다.' : '현재 H3 엔진이 영상 가이드를 지원하지 않습니다.'}>
              <Film size={15} />이어서 생성</button>}
            <button className="secondary-button" onClick={onReuse}><RotateCcw size={15} />설정 불러오기</button>
            <button className="icon-button" onClick={onDelete} disabled={active || preparing || busy} aria-label="작업 삭제"><Trash2 size={17} /></button>
          </div></div>
        {job.error && <div className="error-box"><CircleAlert size={16} /><span>{job.error}</span></div>}
        {active && <section className={`live-progress ${progress.connected ? '' : 'disconnected'}`} aria-live="polite">
          <div><LoaderCircle className="spin" /><span><b>{progress.stage}</b><small>{progress.detail}</small></span></div>
          {progress.percent != null && <strong>{Math.round(progress.percent)}%</strong>}
          <p><Info size={12} />표시 수치는 현재 실행 노드의 진행 상황이며 전체 예상 시간이나 전체 작업률이 아닙니다.</p>
        </section>}
        <div className="stat-grid">
          <div><Clock3 /><span>처리 시간</span><b>{formatDuration(job.elapsedSeconds)}</b></div>
          <div><Film /><span>계획</span><b>{job.plan ? `${job.plan.width}×${job.plan.height} · ${job.plan.frames}프레임` : '준비 중'}</b></div>
          <div><Gauge /><span>프로파일</span><b>{PROFILE_META[job.input.profile].label}</b></div>
          <div><Aperture /><span>시드</span><b>{job.input.seed}</b></div>
        </div>
        {job.extension && <section className="extension-result-card">
          <header><div><Film size={17} /><b>이어 만든 영상</b></div><span>원본과 새 구간을 합친 결과</span></header>
          <div><span><small>원본</small><b>{formatDuration(job.extension.sourceDuration)}</b></span><i />
            <span><small>추가</small><b>{formatDuration(job.extension.addedDuration)}</b></span><i />
            <span><small>합본</small><b>{formatDuration(job.extension.totalDuration)}</b></span></div>
          <p><Info size={13} />원본 끝부분을 움직임 가이드로 사용한 뒤, 겹치는 구간을 제거해 연결했습니다.</p>
        </section>}
        {job.plan && <section className="recipe-card"><header><div><FileJson2 size={17} /><b>실행 레시피</b></div><button onClick={onRecipe}><ArrowDownToLine size={14} />JSON 저장</button></header>
          <dl><div><dt>샘플러</dt><dd>{job.plan.sampler}</dd></div><div><dt>반복</dt><dd>{job.plan.steps} steps</dd></div>
            <div><dt>프레임 속도</dt><dd>{job.plan.fps} fps</dd></div><div><dt>Turbo</dt><dd>{job.plan.turbo ? '사용' : '미사용'}</dd></div></dl>
          {job.plan.warnings.length > 0 && <div className="recipe-warnings">{job.plan.warnings.map(item => <span key={item}><Info size={13} />{item}</span>)}</div>}
          {job.input.originalPrompt && <details className="submitted-prompt"><summary>엔진에 제출한 최종 프롬프트</summary><p>{job.input.prompt}</p></details>}
        </section>}
        {job.optimization && <section className="optimization-card"><div className="eyebrow">프롬프트 제안 기록 · {job.optimization.method === 'claude-agent-sdk' ? `Claude Agent SDK · ${modelLabel(job.optimization.model)}` : '로컬 규칙'}</div>
          <p>{job.optimization.optimized}</p>{job.optimization.notes.length > 0 && <ul>{job.optimization.notes.map(note => <li key={note}>{note}</li>)}</ul>}</section>}
      </div>
    </div>
  )
}

function LibraryView({ jobs, selectedId, onSelect }: { jobs: VideoJob[]; selectedId?: string; onSelect(id: string): void }) {
  const [query, setQuery] = useState(''), [filter, setFilter] = useState<'all' | JobStatus>('all')
  const filtered = useMemo(() => jobs.filter(job => (filter === 'all' || job.status === filter) &&
    `${job.input.originalPrompt || ''} ${job.input.prompt}`.toLowerCase().includes(query.toLowerCase())), [jobs, query, filter])
  return <div className="library-view"><header className="view-header"><div><span className="eyebrow">LOCAL LIBRARY</span><h1>생성 기록</h1><p>로컬에서 만든 영상과 실행 설정을 다시 확인합니다.</p></div><span>{jobs.length}개 작업</span></header>
    <div className="library-tools"><label className="search-field"><Search size={16} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="프롬프트 검색" /></label>
      <select value={filter} onChange={e => setFilter(e.target.value as 'all' | JobStatus)} aria-label="상태 필터"><option value="all">모든 상태</option>
        {(Object.keys(STATUS_META) as JobStatus[]).map(status => <option key={status} value={status}>{STATUS_META[status].label}</option>)}</select></div>
    {filtered.length ? <div className="library-grid">{filtered.map(job => <button className={`library-card ${selectedId === job.id ? 'selected' : ''}`} key={job.id} onClick={() => onSelect(job.id)}>
      <div className="card-visual"><JobVisual job={job} /><span className={`status-badge ${STATUS_META[job.status].tone}`}><i />{STATUS_META[job.status].label}</span></div>
      <div className="card-copy"><b>{job.input.originalPrompt || job.input.prompt}</b><span>{formatDate(job.createdAt)}<i />{job.input.duration}초<i />{PROFILE_META[job.input.profile].label}</span></div>
    </button>)}</div> : <div className="empty-list"><Images /><h2>조건에 맞는 작업이 없습니다.</h2><p>검색어 또는 상태 필터를 바꿔 보세요.</p></div>}</div>
}

function EngineView({ settings, onRefresh, refreshing }: { settings?: AppSettings; onRefresh(): void; refreshing: boolean }) {
  const engine = settings?.engine, ready = Boolean(engine?.connected && engine?.modelReady)
  const assistant = settings?.promptAssistant
  const vramPercent = engine?.vramTotalMB ? Math.max(0, Math.min(100, ((engine.vramTotalMB - (engine.vramFreeMB || 0)) / engine.vramTotalMB) * 100)) : 0
  return <div className="engine-view"><header className="view-header"><div><span className="eyebrow">LOCAL ENGINE</span><h1>엔진 상태</h1><p>현재 연결된 MiniMax H3 실행 환경을 확인합니다.</p></div><button className="secondary-button" onClick={onRefresh} disabled={refreshing}>{refreshing ? <LoaderCircle className="spin" /> : <RefreshCw />}연결 재확인</button></header>
    <div className={`engine-hero ${ready ? 'ready' : ''}`}><div className="engine-rings"><div><MonitorCog /></div></div><div><span className="eyebrow">MINIMAX H3</span><h2>{ready ? '영상을 만들 준비가 됐어요.' : engine?.connected ? '모델을 준비하고 있어요.' : '로컬 엔진에 연결할 수 없습니다.'}</h2>
      <p>{engine?.error || (ready ? '모델과 실행 큐가 정상적으로 응답하고 있습니다.' : '로컬 엔진을 실행한 뒤 다시 연결해 주세요.')}</p></div><span className={`large-status ${ready ? 'success' : ''}`}><i />{ready ? 'READY' : 'OFFLINE'}</span></div>
    <div className="engine-grid"><section><header><b>연결 정보</b><Settings2 /></header><dl><div><dt>엔드포인트</dt><dd>{engine?.endpoint || '확인되지 않음'}</dd></div><div><dt>GPU</dt><dd>{engine?.gpu || '확인되지 않음'}</dd></div><div><dt>Turbo</dt><dd>{engine?.turboAvailable ? '사용 가능' : '사용 불가'}</dd></div><div><dt>영상 이어 만들기</dt><dd>{engine?.extensionAvailable ? '사용 가능' : '사용 불가'}</dd></div><div><dt>데이터 저장소</dt><dd>{settings?.dataDirectory || '확인되지 않음'}</dd></div></dl></section>
      <section><header><b>그래픽 메모리</b><Gauge /></header>{engine?.vramTotalMB ? <><div className="memory-value"><strong>{Math.round((engine.vramFreeMB || 0) / 1024 * 10) / 10}</strong><span>GB 사용 가능</span></div><div className="memory-bar"><i style={{ width: `${vramPercent}%` }} /></div><p>전체 {Math.round(engine.vramTotalMB / 1024 * 10) / 10}GB 중 {Math.round(vramPercent)}% 사용 중</p></> : <p className="unavailable">메모리 정보를 제공하지 않는 엔진입니다.</p>}</section>
      <section><header><b>작업 큐</b><Library /></header><div className="queue-values"><div><strong>{engine?.queueRunning ?? 0}</strong><span>실행 중</span></div><div><strong>{engine?.queuePending ?? 0}</strong><span>대기 중</span></div></div><p>작업은 로컬 큐에 순서대로 들어갑니다.</p></section>
      <section className="assistant-card"><header><b>프롬프트 제안</b><WandSparkles /></header><div className={`assistant-status ${assistant?.available ? 'available' : ''}`}><i />{assistant?.available ? 'Claude 구독 연결됨' : 'Claude 연결 확인 필요'}</div>
        <dl><div><dt>제공자</dt><dd>Claude Agent SDK</dd></div><div><dt>모델</dt><dd>{modelLabel(assistant?.model)}</dd></div><div><dt>인증</dt><dd>Claude 구독</dd></div></dl>
        {assistant?.error && <p className="assistant-error">{assistant.error}</p>}</section></div>
    <div className="honesty-note"><Info /><div><b>처리 기준</b><p>Claude는 입력 이미지의 기본 사실과 설명을 참고해 프롬프트를 제안합니다. 제안 요청에는 Claude 구독 한도가 적용됩니다. 영상 생성은 로컬 MiniMax H3가 수행하며, 실행 프로파일이 특정 품질 향상을 보장하지는 않습니다.</p></div></div>
  </div>
}

export default function App() {
  const restored = (() => { try { return JSON.parse(localStorage.getItem('videokiwi:draft') || 'null') as Partial<GenerationInput> | null } catch { return null } })()
  const [view, setView] = useState<View>('create'), [mobileNav, setMobileNav] = useState(false)
  const [composeMode, setComposeMode] = useState<ComposeMode>('create')
  const [input, setInput] = useState<GenerationInput>({ ...DEFAULT_INPUT, ...restored, extensionSourceId: undefined })
  const [settings, setSettings] = useState<AppSettings>(), [jobs, setJobs] = useState<VideoJob[]>([])
  const [image, setImage] = useState<ImageAsset>(), [endImage, setEndImage] = useState<ImageAsset>()
  const [extensionSource, setExtensionSource] = useState<ExtensionSource>()
  const latestProposalInput = useRef('')
  latestProposalInput.current = JSON.stringify({ ...input, imageId: image?.id, endImageId: endImage?.id })
  const [selectedId, setSelectedId] = useState<string>(), [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false), [uploadBusy, setUploadBusy] = useState(false)
  const [extensionBusy, setExtensionBusy] = useState(false)
  const [optimizing, setOptimizing] = useState(false), [optimization, setOptimization] = useState<PromptOptimization>()
  const [optimizedText, setOptimizedText] = useState(''), [actionBusy, setActionBusy] = useState(false)
  const [refreshing, setRefreshing] = useState(false), [toasts, setToasts] = useState<Toast[]>([])
  const selectedJob = jobs.find(job => job.id === selectedId)
  const engineReady = Boolean(settings?.engine.connected && settings.engine.modelReady)
  const extensionAvailable = Boolean(settings?.engine.extensionAvailable)
  const completedJobs = jobs.filter(job => job.status === 'completed' && Boolean(job.videoUrl))
  const toast = (message: string, kind: Toast['kind'] = 'info') => {
    const id = Date.now() + Math.random(); setToasts(current => [...current, { id, kind, message }])
    window.setTimeout(() => setToasts(current => current.filter(item => item.id !== id)), 4500)
  }

  useEffect(() => {
    let active = true
    api.bootstrap().then(data => {
      if (!active) return; setSettings(data.settings); setJobs(data.jobs); setSelectedId(data.jobs[0]?.id)
    }).catch(error => toast(errorText(error), 'error')).finally(() => { if (active) setLoading(false) })
    const unsubscribe = api.onJobsChanged(nextJobs => {
      if (!active) return
      setJobs(nextJobs); setSelectedId(current => nextJobs.some(job => job.id === current) ? current : undefined)
    })
    return () => { active = false; unsubscribe() }
  }, [])
  useEffect(() => { localStorage.setItem('videokiwi:draft', JSON.stringify(input)) }, [input])

  const upload = async (file: File, position: 'start' | 'end') => {
    if (!imageAccepts(file)) { toast('PNG, JPG, WebP 형식의 10MB 이하 이미지를 선택해 주세요.', 'error'); return }
    setUploadBusy(true)
    try {
      const asset = await api.importImage({ name: file.name, bytes: await file.arrayBuffer() })
      if (position === 'start') { setImage(asset); setInput(value => ({ ...value, imageId: asset.id, mode: 'image' })) }
      else { setEndImage(asset); setInput(value => ({ ...value, endImageId: asset.id, mode: 'image' })) }
      setOptimization(undefined); toast(`${position === 'start' ? '시작' : '끝'} 장면을 불러왔습니다.`, 'success')
    } catch (error) { toast(errorText(error), 'error') } finally { setUploadBusy(false) }
  }
  const applyExtensionSource = (source: ExtensionSource) => {
    setExtensionSource(source)
    setImage(source.image)
    setEndImage(undefined)
    setOptimization(undefined)
    setOptimizedText('')
    setInput(value => ({ ...value, mode: 'image', extensionSourceId: source.id, imageId: source.image.id,
      endImageId: undefined, prompt: '', originalPrompt: undefined, imageDescription: `원본 영상의 마지막 장면: ${source.name}`, optimize: false }))
    setComposeMode('extend')
    setSelectedId(undefined)
    setView('create')
  }
  const prepareExtension = async (jobId: string) => {
    setExtensionBusy(true)
    try { applyExtensionSource(await api.prepareExtension(jobId)); toast('원본 영상의 끝부분을 이어 만들 준비가 됐습니다.', 'success') }
    catch (error) { toast(errorText(error), 'error') }
    finally { setExtensionBusy(false) }
  }
  const uploadVideo = async (file: File) => {
    if (!videoAccepts(file)) { toast('MP4, MOV, WebM 형식의 250MB 이하 영상을 선택해 주세요.', 'error'); return }
    setExtensionBusy(true)
    try { applyExtensionSource(await api.importVideo({ name: file.name, bytes: await file.arrayBuffer() })); toast('이어 만들 원본 영상을 불러왔습니다.', 'success') }
    catch (error) { toast(errorText(error), 'error') }
    finally { setExtensionBusy(false) }
  }
  const changeComposeMode = (mode: ComposeMode) => {
    setComposeMode(mode)
    setExtensionSource(undefined); setImage(undefined); setEndImage(undefined)
    setOptimization(undefined); setOptimizedText('')
    setInput(value => ({ ...DEFAULT_INPUT, duration: value.duration, resolution: value.resolution,
      profile: value.profile, seed: value.seed, extensionSourceId: undefined }))
    setSelectedId(undefined); setView('create')
  }
  const optimize = async () => {
    setOptimizing(true)
    const requestedInput = latestProposalInput.current
    const extending = composeMode === 'extend'
    try { const result = await api.optimizePrompt({ ...input,
      extensionSourceId: extending ? extensionSource?.id : undefined,
      imageId: !extending && input.mode === 'image' ? image?.id : undefined,
      endImageId: extending || input.mode === 'image' ? endImage?.id : undefined })
      if (latestProposalInput.current !== requestedInput) { toast('입력이 바뀌어 이전 요청의 제안은 적용하지 않았습니다. 다시 제안받아 주세요.'); return }
      setOptimization(result); setOptimizedText(result.optimized) }
    catch (error) { toast(errorText(error), 'error') } finally { setOptimizing(false) }
  }
  const create = async () => {
    if (!engineReady) { setView('engine'); toast('로컬 H3 엔진 연결을 먼저 확인해 주세요.', 'error'); return }
    setSubmitting(true)
    try {
      const manual = Boolean(optimization)
      const extending = composeMode === 'extend'
      if (extending && !extensionSource) { toast('이어 만들 원본 영상을 먼저 선택해 주세요.', 'error'); return }
      const jobInput: GenerationInput = { ...input,
        // In extend mode the source video supplies the opening frames, so no separate start image is sent.
        mode: extending ? 'image' : input.mode,
        extensionSourceId: extending ? extensionSource?.id : undefined,
        imageId: !extending && input.mode === 'image' ? image?.id : undefined,
        endImageId: extending || input.mode === 'image' ? endImage?.id : undefined,
        originalPrompt: manual ? input.prompt : undefined, prompt: manual ? optimizedText : input.prompt, optimize: manual ? false : input.optimize }
      const job = await api.createJob(jobInput)
      setJobs(current => [job, ...current.filter(item => item.id !== job.id)]); setSelectedId(job.id); setView('create')
      toast('작업을 로컬 생성 큐에 넣었습니다.', 'success')
    } catch (error) { toast(errorText(error), 'error') } finally { setSubmitting(false) }
  }
  const refreshEngine = async () => {
    setRefreshing(true); try { const engine = await api.engineStatus(); setSettings(current => current ? { ...current, engine } : { engine, dataDirectory: '' }); toast('엔진 상태를 새로 확인했습니다.', 'success') }
    catch (error) { toast(errorText(error), 'error') } finally { setRefreshing(false) }
  }
  const jobAction = async (action: () => Promise<unknown>, success?: string) => {
    setActionBusy(true); try { await action(); if (success) toast(success, 'success') } catch (error) { toast(errorText(error), 'error') } finally { setActionBusy(false) }
  }
  const selectJob = (id: string) => { setSelectedId(id); setView('create') }
  const reuseJob = (job: VideoJob) => {
    setComposeMode('create'); setExtensionSource(undefined)
    setInput({ ...job.input, prompt: job.input.originalPrompt || job.input.prompt, optimize: false, extensionSourceId: undefined })
    setImage(job.image); setEndImage(job.endImage)
    if (job.optimization || job.input.originalPrompt && job.input.originalPrompt !== job.input.prompt) {
      setOptimization(job.optimization || {
        original: job.input.originalPrompt || job.input.prompt, optimized: job.input.prompt, method: 'local-rules',
        notes: ['이전 작업에서 실제 제출한 최종 문장을 불러왔습니다. 새 최적화는 실행하지 않았습니다.'], checks: []
      })
      setOptimizedText(job.input.prompt)
    }
    else { setOptimization(undefined); setOptimizedText('') }
    setSelectedId(undefined); setView('create'); toast('이전 설정을 작업 공간에 불러왔습니다.', 'success')
  }
  return (
    <div className="app-shell">
      <nav className={`side-nav ${mobileNav ? 'open' : ''}`} aria-label="주요 메뉴">
        <div className="brand"><Logo /><span>VideoKiwi</span></div>
        <div className="nav-items">
          <button className={view === 'create' ? 'active' : ''} onClick={() => { setView('create'); setMobileNav(false) }}><Plus /><span>새 영상</span></button>
          <button className={view === 'library' ? 'active' : ''} onClick={() => { setView('library'); setMobileNav(false) }}><Library /><span>라이브러리</span></button>
          <button className={view === 'engine' ? 'active' : ''} onClick={() => { setView('engine'); setMobileNav(false) }}><MonitorCog /><span>엔진</span></button>
        </div>
        <div className="nav-bottom"><EnginePill engine={settings?.engine} /></div>
      </nav>
      <div className="main-shell">
        <header className="top-bar"><div className="top-left"><button className="mobile-menu" onClick={() => setMobileNav(value => !value)} aria-label="메뉴 열기"><Menu /></button>
          <div><span className="top-project">로컬 스튜디오</span><h1>{view === 'create' ? '영상 만들기' : view === 'library' ? '라이브러리' : '엔진 상태'}</h1></div></div>
          <div className="top-actions"><EnginePill engine={settings?.engine} /><div className="local-badge"><Zap size={14} />내 컴퓨터에서 실행</div></div></header>
        {loading ? <div className="page-loader"><Logo /><LoaderCircle className="spin" /><span>로컬 스튜디오를 준비하고 있어요.</span></div> : view === 'create' ?
          <div className="studio-layout">
            <ComposePanel composeMode={composeMode} extensionSource={extensionSource} completedJobs={completedJobs}
              onComposeMode={changeComposeMode} onSelectExtension={jobId => void prepareExtension(jobId)}
              onVideo={file => void uploadVideo(file)} extensionBusy={extensionBusy} extensionAvailable={extensionAvailable}
              input={input} setInput={setInput} image={image} endImage={endImage}
              onImage={file => void upload(file, 'start')} onEndImage={file => void upload(file, 'end')}
              onClearImage={() => { setImage(undefined); setInput({ ...input, imageId: undefined }); setOptimization(undefined) }}
              onClearEndImage={() => { setEndImage(undefined); setInput({ ...input, endImageId: undefined }); setOptimization(undefined) }}
              onOptimize={() => void optimize()} optimization={optimization} optimizedText={optimizedText}
              setOptimizedText={setOptimizedText} clearOptimization={() => { setOptimization(undefined); setOptimizedText('') }}
              onCreate={() => void create()} submitting={submitting} optimizing={optimizing} engineReady={engineReady}
              uploadBusy={uploadBusy} promptAssistant={settings?.promptAssistant} />
            <main className="workspace">
              <div className="workspace-tabs"><div><button className={!selectedJob ? 'active' : ''} onClick={() => setSelectedId(undefined)}><Clapperboard />작업 공간</button>
                <button className={selectedJob ? 'active' : ''} onClick={() => jobs[0] && setSelectedId(jobs[0].id)}><Clock3 />최근 생성 <span>{jobs.length}</span></button></div>
                </div>
              {selectedJob ? <JobDetail job={selectedJob} busy={actionBusy}
                onCancel={() => void jobAction(async () => { const next = await api.cancelJob(selectedJob.id); setJobs(current => current.map(item => item.id === next.id ? next : item)) }, '작업 취소를 요청했습니다.')}
                onDelete={() => void jobAction(async () => { await api.deleteJob(selectedJob.id); setJobs(current => current.filter(item => item.id !== selectedJob.id)); setSelectedId(undefined) }, '작업 기록을 삭제했습니다.')}
                onDownload={() => void jobAction(() => api.saveVideo(selectedJob.id), '영상 다운로드를 시작했습니다.')}
                onRecipe={() => void jobAction(() => api.exportRecipe(selectedJob.id), '실행 레시피 다운로드를 시작했습니다.')}
                onRefresh={() => void jobAction(async () => { const next = await api.refreshJob(selectedJob.id); setJobs(current => current.map(item => item.id === next.id ? next : item)) }, '작업 상태를 다시 확인했습니다.')}
                onReuse={() => reuseJob(selectedJob)} onExtend={() => void prepareExtension(selectedJob.id)}
                extensionAvailable={extensionAvailable && !extensionBusy} /> : <div className="blank-workspace"><EmptyScene />
                {jobs.length > 0 && <section className="recent-strip"><header><div><span className="eyebrow">RECENT</span><h3>최근 생성</h3></div><button onClick={() => setView('library')}>전체 보기</button></header>
                  <div>{jobs.slice(0, 4).map(job => <button key={job.id} onClick={() => setSelectedId(job.id)}><JobVisual job={job} /><span>{job.input.originalPrompt || job.input.prompt}</span></button>)}</div></section>}</div>}
            </main>
          </div> : view === 'library' ? <LibraryView jobs={jobs} selectedId={selectedId} onSelect={selectJob} /> :
            <EngineView settings={settings} onRefresh={() => void refreshEngine()} refreshing={refreshing} />}
      </div>
      <div className="toast-stack" aria-live="polite">{toasts.map(item => <div className={`toast ${item.kind}`} key={item.id}>
        {item.kind === 'success' ? <Check /> : item.kind === 'error' ? <CircleAlert /> : <Info />}<span>{item.message}</span><button onClick={() => setToasts(current => current.filter(toastItem => toastItem.id !== item.id))} aria-label="알림 닫기"><X /></button>
      </div>)}</div>
    </div>
  )
}

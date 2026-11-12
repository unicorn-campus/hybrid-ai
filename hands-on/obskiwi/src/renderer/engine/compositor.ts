import type { Collection, Scene, SceneItem, Source } from '../../shared/types';
import type { MediaManager } from './capture';

/** 캡처, 영상 장치처럼 <video>로 그리는 소스인지 */
export function isMediaKind(kind: Source['kind']): boolean {
  return kind === 'display' || kind === 'window' || kind === 'camera';
}

// ---------- 소스별 원래 크기 ----------

const imageCache = new Map<string, { url: string; img: HTMLImageElement }>();

/** 이미지 소스의 <img>를 돌려줌. 아직 다 안 읽었으면 null */
function getImage(source: Source): HTMLImageElement | null {
  const url = source.settings.filePath ?? '';
  if (!url) return null;
  let entry = imageCache.get(source.id);
  if (!entry || entry.url !== url) {
    const img = new Image();
    img.src = url;
    entry = { url, img };
    imageCache.set(source.id, entry);
  }
  return entry.img.complete && entry.img.naturalWidth > 0 ? entry.img : null;
}

const scratchCtx = document.createElement('canvas').getContext('2d')!;

function fontOf(source: Source): string {
  const size = source.settings.fontSize ?? 96;
  return `700 ${size}px "Pretendard", "Malgun Gothic", "Segoe UI", sans-serif`;
}

function textLines(source: Source): string[] {
  return (source.settings.text ?? '').split('\n');
}

function textMetrics(source: Source): { width: number; height: number; lineHeight: number } {
  const size = source.settings.fontSize ?? 96;
  const lineHeight = Math.round(size * 1.25);
  scratchCtx.font = fontOf(source);
  let width = 1;
  for (const line of textLines(source)) {
    width = Math.max(width, scratchCtx.measureText(line).width);
  }
  return { width: Math.ceil(width), height: lineHeight * textLines(source).length, lineHeight };
}

/** 소스의 원래 크기(배율 1일 때). 아직 알 수 없으면 null */
export function sourceSize(source: Source, media: MediaManager): { w: number; h: number } | null {
  switch (source.kind) {
    case 'display':
    case 'window':
    case 'camera': {
      const v = media.getVideo(source.id);
      return v ? { w: v.videoWidth, h: v.videoHeight } : null;
    }
    case 'image': {
      const img = getImage(source);
      return img ? { w: img.naturalWidth, h: img.naturalHeight } : null;
    }
    case 'text': {
      const m = textMetrics(source);
      return { w: m.width, h: m.height };
    }
    case 'color':
      return { w: source.settings.width ?? 1920, h: source.settings.height ?? 1080 };
  }
}

// ---------- 합성기 ----------

interface ActiveTransition {
  from: Scene;
  start: number;
  duration: number;
}

/**
 * 장면을 캔버스에 그리는 합성기.
 * 창이 가려져도 멈추지 않도록 requestAnimationFrame 대신 setInterval을 씀.
 */
export class Compositor {
  private ctx: CanvasRenderingContext2D;
  private scratch = document.createElement('canvas');
  private timer: number | null = null;
  private fps = 30;
  private transition: ActiveTransition | null = null;
  private frames = 0;
  private lastStat = performance.now();
  onFps: ((fps: number) => void) | null = null;

  constructor(
    private canvas: HTMLCanvasElement,
    private getCollection: () => Collection,
    private media: MediaManager,
  ) {
    this.ctx = canvas.getContext('2d')!;
  }

  start(fps: number): void {
    this.stop();
    this.fps = fps;
    this.frames = 0;
    this.lastStat = performance.now();
    this.timer = window.setInterval(() => this.tick(), 1000 / fps);
  }

  stop(): void {
    if (this.timer !== null) window.clearInterval(this.timer);
    this.timer = null;
  }

  getFps(): number {
    return this.fps;
  }

  /** 장면이 바뀔 때 이전 장면을 넘겨 주면 fade일 때 섞어 그림 */
  startTransition(from: Scene, kind: 'cut' | 'fade', durationMs: number): void {
    if (kind === 'fade' && durationMs > 0) {
      this.transition = { from, start: performance.now(), duration: durationMs };
    } else {
      this.transition = null;
    }
  }

  private tick(): void {
    const c = this.getCollection();
    const scene = c.scenes.find((s) => s.id === c.currentSceneId);
    const sourceMap = new Map(c.sources.map((s) => [s.id, s]));

    // 보이는 미디어 소스는 처음 한 번만 열도록 요청함(이미 열려 있으면 바로 돌아옴)
    if (scene) {
      for (const item of scene.items) {
        const src = sourceMap.get(item.sourceId);
        if (item.visible && src && isMediaKind(src.kind)) this.media.ensure(src);
      }
    }

    const now = performance.now();
    let progress = 1;
    if (this.transition) {
      progress = (now - this.transition.start) / this.transition.duration;
      if (progress >= 1) this.transition = null;
    }

    this.drawScene(this.ctx, scene, sourceMap);
    if (this.transition) {
      // 이전 장면을 따로 그린 뒤 (1 - 진행률) 투명도로 위에 겹침 → 결과는 두 장면의 섞임
      const s = this.scratch;
      if (s.width !== this.canvas.width || s.height !== this.canvas.height) {
        s.width = this.canvas.width;
        s.height = this.canvas.height;
      }
      this.drawScene(s.getContext('2d')!, this.transition.from, sourceMap);
      this.ctx.globalAlpha = Math.max(0, 1 - progress);
      this.ctx.drawImage(s, 0, 0);
      this.ctx.globalAlpha = 1;
    }

    this.frames++;
    if (now - this.lastStat >= 1000) {
      this.onFps?.(Math.round((this.frames * 1000) / (now - this.lastStat)));
      this.frames = 0;
      this.lastStat = now;
    }
  }

  private drawScene(
    ctx: CanvasRenderingContext2D,
    scene: Scene | undefined,
    sources: Map<string, Source>,
  ): void {
    ctx.globalAlpha = 1;
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    if (!scene) return;
    for (const item of scene.items) {
      if (!item.visible) continue; // 앞쪽이 아래이므로 순서대로 그리면 뒤쪽이 위에 놓임
      const src = sources.get(item.sourceId);
      if (src) this.drawItem(ctx, item, src);
    }
  }

  private drawItem(ctx: CanvasRenderingContext2D, item: SceneItem, source: Source): void {
    ctx.save();
    ctx.translate(item.x, item.y);
    ctx.scale(item.scaleX, item.scaleY);
    switch (source.kind) {
      case 'display':
      case 'window':
      case 'camera': {
        const v = this.media.getVideo(source.id);
        if (v) ctx.drawImage(v, 0, 0, v.videoWidth, v.videoHeight);
        break;
      }
      case 'image': {
        const img = getImage(source);
        if (img) ctx.drawImage(img, 0, 0);
        break;
      }
      case 'text': {
        const m = textMetrics(source);
        ctx.font = fontOf(source);
        ctx.fillStyle = source.settings.color ?? '#ffffff';
        ctx.textBaseline = 'top';
        textLines(source).forEach((line, i) => ctx.fillText(line, 0, i * m.lineHeight));
        break;
      }
      case 'color': {
        ctx.fillStyle = source.settings.color ?? '#7cc242';
        ctx.fillRect(0, 0, source.settings.width ?? 1920, source.settings.height ?? 1080);
        break;
      }
    }
    ctx.restore();
  }
}

/** 원래 크기(w x h)를 캔버스(cw x ch)에 비율 유지로 꽉 차게 넣고 가운데 맞춤하는 값 */
export function fitRect(w: number, h: number, cw: number, ch: number) {
  const s = Math.min(cw / w, ch / h);
  return { x: (cw - w * s) / 2, y: (ch - h * s) / 2, scaleX: s, scaleY: s };
}

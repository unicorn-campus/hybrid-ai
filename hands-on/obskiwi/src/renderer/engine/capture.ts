import type { Source } from '../../shared/types';
import type { AudioEngine } from './audio';

interface Entry {
  signature: string; // 소스 설정이 바뀌면 달라져 다시 여는 기준이 됨
  stream: MediaStream | null;
  video: HTMLVideoElement | null;
  error: string;
}

function signatureOf(source: Source): string {
  return `${source.kind}|${source.settings.sourceId ?? ''}|${source.settings.deviceId ?? ''}`;
}

/**
 * 캡처 스트림 관리자. 소스 하나당 숨긴 <video> 하나를 두고 합성기가 거기서 그림을 가져감.
 * 화면과 창 캡처는 main의 선택 목록과 getDisplayMedia 호출이 짝이므로 한 줄로 세워 차례대로 처리함.
 */
export class MediaManager {
  private entries = new Map<string, Entry>();
  private queue: Promise<unknown> = Promise.resolve();
  private listeners = new Set<() => void>();
  /** 첫 영상 크기를 알게 됐을 때 불림(화면에 맞추기용) */
  onReady: ((sourceId: string, width: number, height: number) => void) | null = null;

  constructor(private audio: AudioEngine) {}

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private notify(): void {
    this.listeners.forEach((fn) => fn());
  }

  /** 그릴 수 있는 상태의 <video>만 돌려줌 */
  getVideo(sourceId: string): HTMLVideoElement | null {
    const v = this.entries.get(sourceId)?.video;
    return v && v.readyState >= 2 && v.videoWidth > 0 ? v : null;
  }

  getError(sourceId: string): string {
    return this.entries.get(sourceId)?.error ?? '';
  }

  /** 열려 있지 않으면 열기 시작함. 여러 번 불러도 한 번만 엶 */
  ensure(source: Source): void {
    const sig = signatureOf(source);
    const existing = this.entries.get(source.id);
    if (existing && existing.signature === sig) return;
    if (existing) this.dispose(source.id);

    const entry: Entry = { signature: sig, stream: null, video: null, error: '' };
    this.entries.set(source.id, entry);
    void this.open(source, entry);
  }

  /** 열기에 실패한 소스를 다시 시도하게 함 */
  retry(sourceId: string): void {
    this.dispose(sourceId);
    this.notify();
  }

  private async open(source: Source, entry: Entry): Promise<void> {
    try {
      let stream: MediaStream;
      if (source.kind === 'camera') {
        const id = source.settings.deviceId;
        stream = await navigator.mediaDevices.getUserMedia({
          video: id ? { deviceId: { exact: id } } : true,
          audio: false,
        });
      } else {
        const sourceId = source.settings.sourceId;
        if (!sourceId) throw new Error('캡처할 화면이나 창이 정해지지 않음');
        // 화면 캡처는 데스크톱 소리도 함께 받아 보고, 창 캡처는 영상만 받음
        stream = await this.openCapture(sourceId, source.kind === 'display');
      }

      // 열리는 동안 소스가 지워졌거나 설정이 바뀌었으면 바로 닫음
      if (this.entries.get(source.id) !== entry) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }

      // 소리 트랙은 믹서가 쓰거나, 안 쓰면 닫음
      if (stream.getAudioTracks().length > 0) {
        if (this.audio.getDesktopOwner() === null) {
          this.audio.attachDesktop(stream, source.id);
        } else {
          stream.getAudioTracks().forEach((t) => {
            stream.removeTrack(t);
            t.stop();
          });
        }
      }

      const video = document.createElement('video');
      video.muted = true; // 화면 소리는 믹서로만 처리하므로 여기서는 소리를 내지 않음
      video.playsInline = true;
      video.style.cssText = 'position:fixed;left:0;top:0;width:2px;height:2px;opacity:0;pointer-events:none';
      video.srcObject = stream;
      document.body.appendChild(video);
      video.addEventListener(
        'loadedmetadata',
        () => this.onReady?.(source.id, video.videoWidth, video.videoHeight),
        { once: true },
      );
      stream.getVideoTracks()[0]?.addEventListener('ended', () => {
        if (this.entries.get(source.id) === entry) {
          entry.error = '캡처가 끝남(창이 닫혔거나 장치가 빠짐)';
          this.notify();
        }
      });
      entry.stream = stream;
      entry.video = video;
      await video.play().catch(() => undefined);
      this.notify();
    } catch (err) {
      entry.error = err instanceof Error ? err.message : '열 수 없음';
      this.notify();
    }
  }

  /** main에 원본을 알린 뒤 getDisplayMedia를 부름. 한 줄로 세워 순서를 지킴 */
  private openCapture(sourceId: string, withAudio: boolean): Promise<MediaStream> {
    const job = this.queue.then(async () => {
      await window.obskiwi.selectCaptureSource(sourceId, withAudio);
      return navigator.mediaDevices.getDisplayMedia({ video: true, audio: withAudio });
    });
    this.queue = job.catch(() => undefined);
    return job;
  }

  /** 「데스크톱 소리 켜기」용. 화면 하나를 소리와 함께 열고 영상 트랙은 바로 버림 */
  async openDesktopAudio(): Promise<void> {
    const screens = await window.obskiwi.listCaptureSources('screen');
    if (screens.length === 0) throw new Error('화면을 찾을 수 없음');
    const stream = await this.openCapture(screens[0].id, true);
    stream.getVideoTracks().forEach((t) => t.stop());
    if (stream.getAudioTracks().length === 0) throw new Error('데스크톱 소리를 받지 못함');
    this.audio.attachDesktop(stream, 'manual');
  }

  private dispose(sourceId: string): void {
    const e = this.entries.get(sourceId);
    if (!e) return;
    this.audio.releaseDesktop(sourceId);
    e.stream?.getTracks().forEach((t) => t.stop());
    if (e.video) {
      e.video.srcObject = null;
      e.video.remove();
    }
    this.entries.delete(sourceId);
  }

  /** 어떤 장면에서도 쓰지 않는 소스의 스트림을 닫음 */
  releaseUnused(usedSourceIds: Set<string>): void {
    let changed = false;
    for (const id of [...this.entries.keys()]) {
      if (!usedSourceIds.has(id)) {
        this.dispose(id);
        changed = true;
      }
    }
    if (changed) this.notify();
  }
}

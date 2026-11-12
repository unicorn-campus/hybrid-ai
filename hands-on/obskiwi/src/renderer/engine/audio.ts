export type ChannelId = 'desktop' | 'mic';

interface Channel {
  gain: GainNode;
  analyser: AnalyserNode;
  buffer: Float32Array<ArrayBuffer>;
  node: MediaStreamAudioSourceNode | null;
  stream: MediaStream | null;
  owner: string | null; // 이 소리를 붙인 곳(캡처 소스 ID 또는 'manual')
  volume: number;
  muted: boolean;
  error: string;
}

/**
 * 오디오 믹서. AudioContext 하나에 데스크톱 소리와 마이크 두 채널을 두고
 * 합쳐서 녹화용 트랙 하나로 내보냄. 스피커(ctx.destination)에는 연결하지 않아 울림이 없음.
 */
export class AudioEngine {
  private ctx = new AudioContext();
  private dest = this.ctx.createMediaStreamDestination();
  private channels: Record<ChannelId, Channel>;
  private listeners = new Set<() => void>();

  constructor() {
    this.channels = { desktop: this.makeChannel(), mic: this.makeChannel() };
  }

  private makeChannel(): Channel {
    const gain = this.ctx.createGain();
    const analyser = this.ctx.createAnalyser();
    analyser.fftSize = 1024;
    gain.connect(analyser);
    analyser.connect(this.dest);
    return {
      gain,
      analyser,
      buffer: new Float32Array(analyser.fftSize),
      node: null,
      stream: null,
      owner: null,
      volume: 1,
      muted: false,
      error: '',
    };
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private notify(): void {
    this.listeners.forEach((fn) => fn());
  }

  /** 사용자 동작 뒤에 불러서 AudioContext를 깨움 */
  async resume(): Promise<void> {
    if (this.ctx.state !== 'running') await this.ctx.resume();
  }

  /** 녹화에 쓸 합쳐진 오디오 트랙 */
  getMixedTrack(): MediaStreamTrack | undefined {
    return this.dest.stream.getAudioTracks()[0];
  }

  setVolume(id: ChannelId, volume: number): void {
    const ch = this.channels[id];
    ch.volume = Math.min(1, Math.max(0, volume));
    ch.gain.gain.value = ch.muted ? 0 : ch.volume;
  }

  setMuted(id: ChannelId, muted: boolean): void {
    const ch = this.channels[id];
    ch.muted = muted;
    ch.gain.gain.value = muted ? 0 : ch.volume;
  }

  /** 0 ~ 1. -60dB를 0, 0dB를 1로 봄 */
  getLevel(id: ChannelId): number {
    const ch = this.channels[id];
    if (!ch.node) return 0;
    ch.analyser.getFloatTimeDomainData(ch.buffer);
    let peak = 0;
    for (let i = 0; i < ch.buffer.length; i++) peak = Math.max(peak, Math.abs(ch.buffer[i]));
    if (peak <= 0.000001) return 0;
    return Math.min(1, Math.max(0, (20 * Math.log10(peak) + 60) / 60));
  }

  isActive(id: ChannelId): boolean {
    return this.channels[id].node !== null;
  }

  getError(id: ChannelId): string {
    return this.channels[id].error;
  }

  getDesktopOwner(): string | null {
    return this.channels.desktop.owner;
  }

  // ---------- 채널에 소리 붙이기와 떼기 ----------

  private attach(id: ChannelId, stream: MediaStream, owner: string): void {
    this.detach(id);
    const audioTracks = stream.getAudioTracks();
    if (audioTracks.length === 0) return;
    const ch = this.channels[id];
    ch.stream = new MediaStream(audioTracks);
    ch.node = this.ctx.createMediaStreamSource(ch.stream);
    ch.node.connect(ch.gain);
    ch.owner = owner;
    ch.error = '';
    // 소리가 끊기면(캡처 종료 등) 채널을 비움
    audioTracks[0].addEventListener('ended', () => {
      if (this.channels[id].stream === ch.stream) {
        this.detach(id);
        this.notify();
      }
    });
    this.notify();
  }

  private detach(id: ChannelId): void {
    const ch = this.channels[id];
    ch.node?.disconnect();
    ch.stream?.getTracks().forEach((t) => t.stop());
    ch.node = null;
    ch.stream = null;
    ch.owner = null;
  }

  /** 캡처 스트림에 소리가 들어 있을 때 데스크톱 채널로 씀 */
  attachDesktop(stream: MediaStream, owner: string): void {
    this.attach('desktop', stream, owner);
  }

  /** 그 소스가 붙여 둔 데스크톱 소리라면 뗌 */
  releaseDesktop(owner: string): void {
    if (this.channels.desktop.owner === owner) {
      this.detach('desktop');
      this.notify();
    }
  }

  /** 마이크 켜기. deviceId가 비어 있으면 기본 장치 */
  async enableMic(deviceId: string): Promise<void> {
    const ch = this.channels.mic;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          deviceId: deviceId && deviceId !== 'default' ? { exact: deviceId } : undefined,
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
      });
      this.attach('mic', stream, 'mic');
    } catch (err) {
      this.detach('mic');
      ch.error = err instanceof Error ? err.message : '마이크를 열 수 없음';
      this.notify();
    }
  }

  disableMic(): void {
    this.detach('mic');
    this.notify();
  }
}

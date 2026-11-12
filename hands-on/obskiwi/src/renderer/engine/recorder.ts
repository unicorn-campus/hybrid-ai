/** 녹화기. 캔버스 영상 + 믹서 소리를 MediaRecorder로 담아 1초마다 main에 보내 파일에 이어 씀 */

function pickMimeType(): string {
  const candidates = ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm'];
  return candidates.find((m) => MediaRecorder.isTypeSupported(m)) ?? 'video/webm';
}

export class Recorder {
  private recorder: MediaRecorder | null = null;
  private videoStream: MediaStream | null = null;
  private sending: Promise<void> = Promise.resolve();

  isRecording(): boolean {
    return this.recorder !== null;
  }

  /** 녹화 시작. 저장될 파일 경로를 돌려줌 */
  async start(
    canvas: HTMLCanvasElement,
    fps: number,
    audioTrack: MediaStreamTrack | undefined,
    outputDir: string,
    onError: (message: string) => void,
  ): Promise<string> {
    if (this.recorder) throw new Error('이미 녹화 중임');
    const path = await window.obskiwi.startRecording(outputDir);

    this.videoStream = canvas.captureStream(fps);
    const stream = new MediaStream(this.videoStream.getVideoTracks());
    if (audioTrack) stream.addTrack(audioTrack);

    const recorder = new MediaRecorder(stream, {
      mimeType: pickMimeType(),
      videoBitsPerSecond: 8_000_000,
    });
    recorder.ondataavailable = (e) => {
      if (e.data.size === 0) return;
      // 조각이 순서대로 파일에 쓰이도록 이전 전송이 끝난 뒤에 보냄
      this.sending = this.sending
        .then(async () => window.obskiwi.writeRecordingChunk(await e.data.arrayBuffer()))
        .catch((err: unknown) => onError(err instanceof Error ? err.message : '녹화 조각 저장 실패'));
    };
    recorder.onerror = () => onError('녹화 중 오류가 발생함');
    recorder.start(1000);
    this.recorder = recorder;
    return path;
  }

  /** 녹화 중지. 마지막 조각까지 저장한 뒤 파일 경로를 돌려줌 */
  async stop(): Promise<string> {
    const recorder = this.recorder;
    if (!recorder) throw new Error('녹화 중이 아님');
    const stopped = new Promise<void>((resolve) => {
      recorder.onstop = () => resolve();
    });
    if (recorder.state !== 'inactive') recorder.stop();
    await stopped;
    await this.sending;
    // 합성 캔버스의 영상 트랙만 닫음(믹서 소리 트랙은 다음 녹화에도 쓰므로 닫지 않음)
    this.videoStream?.getTracks().forEach((t) => t.stop());
    this.videoStream = null;
    this.recorder = null;
    return window.obskiwi.stopRecording();
  }
}

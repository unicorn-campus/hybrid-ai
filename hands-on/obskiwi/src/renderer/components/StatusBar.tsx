interface Props {
  recordingStartedAt: number | null;
  now: number;
  renderFps: number;
  targetFps: number;
  width: number;
  height: number;
}

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = String(Math.floor(total / 3600)).padStart(2, '0');
  const m = String(Math.floor((total % 3600) / 60)).padStart(2, '0');
  const s = String(total % 60).padStart(2, '0');
  return `${h}:${m}:${s}`;
}

/** 맨 아래 상태 표시줄: 녹화 상태(빨간 점 + 경과 시간)와 실제 렌더 FPS */
export function StatusBar(props: Props) {
  const recording = props.recordingStartedAt !== null;
  return (
    <footer className="statusbar">
      <span className="status-item">
        <span className={`dot${recording ? ' live' : ''}`} />
        {recording ? `녹화 중 ${formatElapsed(props.now - (props.recordingStartedAt ?? props.now))}` : '대기 중'}
      </span>
      <span className="status-item">
        FPS {props.renderFps} / {props.targetFps}
      </span>
      <span className="status-item">
        {props.width}x{props.height}
      </span>
    </footer>
  );
}

import { Circle, FolderOpen, Settings, Square } from 'lucide-react';

interface Props {
  recording: boolean;
  busy: boolean;
  outputDir: string;
  onToggleRecord: () => void;
  onOpenSettings: () => void;
  onOpenFolder: () => void;
}

/** 제어: 녹화 시작/중지, 설정, 녹화 폴더 열기 */
export function ControlsDock(props: Props) {
  return (
    <div className="dock-content controls">
      <button
        className={`big-btn${props.recording ? ' recording' : ' primary'}`}
        disabled={props.busy}
        onClick={props.onToggleRecord}
      >
        {props.recording ? <Square size={16} /> : <Circle size={16} />}
        {props.recording ? '녹화 중지' : '녹화 시작'}
      </button>
      <button className="big-btn" onClick={props.onOpenSettings}>
        <Settings size={16} /> 설정
      </button>
      <button className="big-btn" onClick={props.onOpenFolder}>
        <FolderOpen size={16} /> 녹화 폴더 열기
      </button>
      <p className="hint path" title={props.outputDir}>
        {props.outputDir}
      </p>
    </div>
  );
}

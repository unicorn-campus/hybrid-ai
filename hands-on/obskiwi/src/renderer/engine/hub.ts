import { AudioEngine } from './audio';
import { MediaManager } from './capture';
import { Recorder } from './recorder';
import type { Compositor } from './compositor';

/** 화면 바깥에서 돌아가는 엔진 객체들을 한곳에 모아 둔 것(앱 전체에서 하나씩만 씀) */
const audio = new AudioEngine();
const media = new MediaManager(audio);
const recorder = new Recorder();

export const hub = {
  audio,
  media,
  recorder,
  /** 미리보기 컴포넌트가 만든 뒤 등록함 */
  canvas: null as HTMLCanvasElement | null,
  compositor: null as Compositor | null,
  /** 새로 추가한 미디어 소스(소스 ID → 항목 ID). 첫 영상 크기를 알게 되면 화면에 맞춤 */
  pendingFit: new Map<string, string>(),
};

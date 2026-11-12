// main, preload, 렌더러가 함께 쓰는 타입 모음. 코드(실행문)는 넣지 않고 타입만 둠.

export type SourceKind = 'display' | 'window' | 'camera' | 'image' | 'text' | 'color';

/** 소스 종류마다 쓰는 값이 달라서 선택 항목으로 둠 */
export interface SourceSettings {
  sourceId?: string; // display, window: 캡처할 화면 또는 창 ID
  deviceId?: string; // camera: 영상 장치 ID
  filePath?: string; // image: 읽어 둔 data URL
  fileName?: string; // image: 화면에 보여 줄 파일 이름
  text?: string; // text
  fontSize?: number; // text
  color?: string; // text 글자색 또는 color 채움색
  width?: number; // color
  height?: number; // color
}

export interface Source {
  id: string;
  name: string;
  kind: SourceKind;
  settings: SourceSettings;
}

export interface SceneItem {
  id: string;
  sourceId: string;
  x: number;
  y: number;
  scaleX: number;
  scaleY: number;
  visible: boolean;
  locked: boolean;
}

/** items 배열 앞쪽이 아래, 뒤쪽이 위 */
export interface Scene {
  id: string;
  name: string;
  items: SceneItem[];
}

export type TransitionKind = 'cut' | 'fade';

export interface TransitionSettings {
  kind: TransitionKind;
  durationMs: number;
}

export interface AudioChannelSettings {
  volume: number; // 0 ~ 1
  muted: boolean;
}

export interface MicSettings extends AudioChannelSettings {
  deviceId: string;
}

export interface OutputSettings {
  width: number;
  height: number;
  fps: number;
  outputDir: string;
}

export interface Collection {
  name: string;
  sources: Source[];
  scenes: Scene[];
  sceneOrder: string[];
  currentSceneId: string;
  transition: TransitionSettings;
  audio: { desktop: AudioChannelSettings; mic: MicSettings };
  settings: OutputSettings;
}

export type CaptureType = 'screen' | 'window';

export interface CaptureSourceInfo {
  id: string;
  name: string;
  thumbnail: string; // data URL
}

export interface ImagePickResult {
  name: string;
  dataUrl: string;
}

/** preload가 window.obskiwi로 노출하는 함수 목록 (main의 ipcMain 핸들러와 1:1) */
export interface ObskiwiApi {
  loadCollection(): Promise<Collection | null>;
  saveCollection(collection: Collection): Promise<void>;
  listCaptureSources(type: CaptureType): Promise<CaptureSourceInfo[]>;
  selectCaptureSource(sourceId: string, withAudio: boolean): Promise<void>;
  openImage(): Promise<ImagePickResult | null>;
  chooseFolder(): Promise<string | null>;
  getDefaultOutputDir(): Promise<string>;
  startRecording(outputDir: string): Promise<string>;
  writeRecordingChunk(data: ArrayBuffer): Promise<void>;
  stopRecording(): Promise<string>;
  openFolder(dir: string): Promise<void>;
}

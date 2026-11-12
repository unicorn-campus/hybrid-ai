import { contextBridge, ipcRenderer } from 'electron';
// 샌드박스 preload는 상대 경로 require가 안 되므로 타입만 가져옴(컴파일 시 지워짐)
import type { ObskiwiApi } from '../shared/types';

// 렌더러에 꼭 필요한 함수만 골라 노출함. ipcRenderer 자체는 노출하지 않음.
const api: ObskiwiApi = {
  loadCollection: () => ipcRenderer.invoke('collection:load'),
  saveCollection: (collection) => ipcRenderer.invoke('collection:save', collection),
  listCaptureSources: (type) => ipcRenderer.invoke('capture:list-sources', type),
  selectCaptureSource: (sourceId, withAudio) =>
    ipcRenderer.invoke('capture:select', sourceId, withAudio),
  openImage: () => ipcRenderer.invoke('dialog:open-image'),
  chooseFolder: () => ipcRenderer.invoke('dialog:choose-folder'),
  getDefaultOutputDir: () => ipcRenderer.invoke('app:default-output-dir'),
  startRecording: (outputDir) => ipcRenderer.invoke('recording:start', outputDir),
  writeRecordingChunk: (data) => ipcRenderer.invoke('recording:chunk', data),
  stopRecording: () => ipcRenderer.invoke('recording:stop'),
  openFolder: (dir) => ipcRenderer.invoke('shell:open-folder', dir),
};

contextBridge.exposeInMainWorld('obskiwi', api);

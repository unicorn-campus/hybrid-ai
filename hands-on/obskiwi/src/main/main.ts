import {
  app,
  BrowserWindow,
  desktopCapturer,
  dialog,
  ipcMain,
  Menu,
  session,
  shell,
  type IpcMainInvokeEvent,
} from 'electron';
import { createWriteStream, type WriteStream } from 'node:fs';
import { mkdir, readFile, rename, stat, writeFile } from 'node:fs/promises';
import { isAbsolute, join, extname, basename } from 'node:path';
import type { CaptureSourceInfo, CaptureType, Collection, ImagePickResult } from '../shared/types';

let mainWindow: BrowserWindow | null = null;

// ---------- 입력 검사 도구 ----------

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** 저장할 장면 모음이 최소한의 모양을 갖췄는지 확인함 */
function isCollectionShape(v: unknown): v is Collection {
  if (!isRecord(v)) return false;
  return (
    typeof v.name === 'string' &&
    Array.isArray(v.sources) &&
    Array.isArray(v.scenes) &&
    Array.isArray(v.sceneOrder) &&
    typeof v.currentSceneId === 'string' &&
    isRecord(v.transition) &&
    isRecord(v.audio) &&
    isRecord(v.settings)
  );
}

/** 우리 앱 화면(file://)에서 온 요청만 받음 */
function assertTrusted(event: IpcMainInvokeEvent): void {
  const url = event.senderFrame?.url ?? '';
  if (!url.startsWith('file://')) {
    throw new Error('허용되지 않은 요청 위치임');
  }
}

function assertString(v: unknown, label: string): string {
  if (typeof v !== 'string' || v.length === 0 || v.length > 4096) {
    throw new Error(`${label} 값이 올바르지 않음`);
  }
  return v;
}

// ---------- 장면 모음 저장과 읽기 ----------

function collectionPath(): string {
  return join(app.getPath('userData'), 'scenes', 'default.json');
}

async function loadCollection(): Promise<Collection | null> {
  try {
    const text = await readFile(collectionPath(), 'utf-8');
    const parsed: unknown = JSON.parse(text);
    return isCollectionShape(parsed) ? parsed : null;
  } catch {
    return null; // 파일이 없거나 깨졌으면 렌더러가 기본 장면을 만듦
  }
}

async function saveCollection(collection: Collection): Promise<void> {
  const file = collectionPath();
  await mkdir(join(app.getPath('userData'), 'scenes'), { recursive: true });
  // 임시 파일에 쓴 뒤 바꿔치기해서 저장 도중 꺼져도 기존 파일이 깨지지 않게 함
  const tmp = `${file}.tmp`;
  await writeFile(tmp, JSON.stringify(collection, null, 2), 'utf-8');
  await rename(tmp, file);
}

// ---------- 화면 캡처 ----------

/** 렌더러가 "이 원본을 열 거야"라고 알려 둔 순서대로 쌓아 두는 줄 */
const pendingCaptures: { sourceId: string; withAudio: boolean }[] = [];

function setupDisplayMediaHandler(): void {
  session.defaultSession.setDisplayMediaRequestHandler(
    async (_request, callback) => {
      const pending = pendingCaptures.shift();
      if (!pending) {
        callback({});
        return;
      }
      try {
        // 원본 ID 앞부분(screen: 또는 window:)으로 종류를 골라 한 종류만 찾고,
        // 썸네일은 만들지 않아(0x0) 캡처가 빨리 열리게 함
        const type = pending.sourceId.startsWith('screen:') ? 'screen' : 'window';
        const sources = await desktopCapturer.getSources({
          types: [type],
          thumbnailSize: { width: 0, height: 0 },
        });
        const found = sources.find((s) => s.id === pending.sourceId);
        if (!found) {
          callback({});
          return;
        }
        // loopback은 Windows에서 데스크톱 소리를 잡음
        callback({ video: found, audio: pending.withAudio ? 'loopback' : undefined });
      } catch {
        callback({});
      }
    },
    { useSystemPicker: false },
  );
}

async function listCaptureSources(type: CaptureType): Promise<CaptureSourceInfo[]> {
  const sources = await desktopCapturer.getSources({
    types: [type],
    thumbnailSize: { width: 320, height: 180 },
    fetchWindowIcons: false,
  });
  return sources.map((s) => ({ id: s.id, name: s.name, thumbnail: s.thumbnail.toDataURL() }));
}

// ---------- 이미지 고르기 ----------

const IMAGE_MIME: Record<string, string> = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.bmp': 'image/bmp',
};
const MAX_IMAGE_BYTES = 20 * 1024 * 1024;

async function openImage(): Promise<ImagePickResult | null> {
  const result = await dialog.showOpenDialog(mainWindow!, {
    title: '이미지 고르기',
    properties: ['openFile'],
    filters: [{ name: '이미지', extensions: ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'] }],
  });
  if (result.canceled || result.filePaths.length === 0) return null;
  const file = result.filePaths[0];
  const mime = IMAGE_MIME[extname(file).toLowerCase()];
  if (!mime) throw new Error('지원하지 않는 이미지 형식임');
  if ((await stat(file)).size > MAX_IMAGE_BYTES) throw new Error('이미지가 20MB보다 큼');
  const buf = await readFile(file);
  return { name: basename(file), dataUrl: `data:${mime};base64,${buf.toString('base64')}` };
}

// ---------- 녹화 파일 ----------

let recordingStream: WriteStream | null = null;
let recordingPath = '';

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

function recordingFileName(): string {
  const d = new Date();
  const date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const time = `${pad(d.getHours())}-${pad(d.getMinutes())}-${pad(d.getSeconds())}`;
  return `obskiwi_${date}_${time}.webm`;
}

function defaultOutputDir(): string {
  return join(app.getPath('videos'), 'obskiwi');
}

async function startRecording(outputDir: string): Promise<string> {
  if (recordingStream) throw new Error('이미 녹화 중임');
  if (!isAbsolute(outputDir)) throw new Error('출력 폴더는 절대 경로여야 함');
  await mkdir(outputDir, { recursive: true });
  recordingPath = join(outputDir, recordingFileName());
  recordingStream = createWriteStream(recordingPath);
  recordingStream.on('error', (err) => console.error('녹화 파일 쓰기 오류', err));
  return recordingPath;
}

async function writeChunk(data: unknown): Promise<void> {
  if (!recordingStream) throw new Error('녹화 중이 아님');
  let buf: Buffer;
  if (data instanceof ArrayBuffer) buf = Buffer.from(data);
  else if (ArrayBuffer.isView(data)) buf = Buffer.from(data.buffer, data.byteOffset, data.byteLength);
  else throw new Error('조각 형식이 올바르지 않음');
  recordingStream.write(buf);
}

async function stopRecording(): Promise<string> {
  const stream = recordingStream;
  if (!stream) throw new Error('녹화 중이 아님');
  recordingStream = null;
  await new Promise<void>((resolve) => stream.end(() => resolve()));
  return recordingPath;
}

// ---------- IPC 등록 ----------

function registerIpc(): void {
  ipcMain.handle('collection:load', (e) => {
    assertTrusted(e);
    return loadCollection();
  });
  ipcMain.handle('collection:save', (e, collection: unknown) => {
    assertTrusted(e);
    if (!isCollectionShape(collection)) throw new Error('장면 모음 모양이 올바르지 않음');
    return saveCollection(collection);
  });
  ipcMain.handle('capture:list-sources', (e, type: unknown) => {
    assertTrusted(e);
    if (type !== 'screen' && type !== 'window') throw new Error('캡처 종류가 올바르지 않음');
    return listCaptureSources(type);
  });
  ipcMain.handle('capture:select', (e, sourceId: unknown, withAudio: unknown) => {
    assertTrusted(e);
    pendingCaptures.push({
      sourceId: assertString(sourceId, 'sourceId'),
      withAudio: withAudio === true,
    });
  });
  ipcMain.handle('dialog:open-image', (e) => {
    assertTrusted(e);
    return openImage();
  });
  ipcMain.handle('dialog:choose-folder', async (e) => {
    assertTrusted(e);
    const r = await dialog.showOpenDialog(mainWindow!, {
      title: '녹화 폴더 고르기',
      properties: ['openDirectory', 'createDirectory'],
    });
    return r.canceled || r.filePaths.length === 0 ? null : r.filePaths[0];
  });
  ipcMain.handle('app:default-output-dir', (e) => {
    assertTrusted(e);
    return defaultOutputDir();
  });
  ipcMain.handle('recording:start', (e, outputDir: unknown) => {
    assertTrusted(e);
    return startRecording(assertString(outputDir, 'outputDir'));
  });
  ipcMain.handle('recording:chunk', (e, data: unknown) => {
    assertTrusted(e);
    return writeChunk(data);
  });
  ipcMain.handle('recording:stop', (e) => {
    assertTrusted(e);
    return stopRecording();
  });
  ipcMain.handle('shell:open-folder', async (e, dir: unknown) => {
    assertTrusted(e);
    const target = assertString(dir, 'dir');
    if (!isAbsolute(target)) throw new Error('폴더는 절대 경로여야 함');
    await mkdir(target, { recursive: true });
    const err = await shell.openPath(target);
    if (err) throw new Error(err);
  });
}

// ---------- 창 ----------

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: '#14171a',
    title: 'obskiwi',
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      // 창이 가려지거나 최소화돼도 합성 타이머가 느려지지 않게 함(녹화 유지)
      backgroundThrottling: false,
      autoplayPolicy: 'no-user-gesture-required',
    },
  });

  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  mainWindow.webContents.on('will-navigate', (e) => e.preventDefault());
  void mainWindow.loadFile(join(__dirname, '..', 'renderer', 'index.html'));
  if (process.env.OBSKIWI_DEVTOOLS === '1') mainWindow.webContents.openDevTools({ mode: 'detach' });
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  Menu.setApplicationMenu(null);
  // 카메라와 마이크(media)만 허용하고 나머지 권한 요청은 거절함
  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => {
    callback(permission === 'media' || permission === 'display-capture');
  });
  session.defaultSession.setPermissionCheckHandler(
    (_wc, permission) => permission === 'media' || permission === 'display-capture',
  );
  setupDisplayMediaHandler();
  registerIpc();
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  recordingStream?.end();
  app.quit();
});

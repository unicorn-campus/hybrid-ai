// sqlkiwi 메인 프로세스: 창을 만들고, 화면 요청(IPC)을 연결 세션과 저장소로 넘김
import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron'
import { join } from 'node:path'
import type { ConnectionInput, NavNode, Reply } from '@shared/types'
import * as sessions from './session'
import * as store from './store/connections'

// 시험할 때 사용자 설정과 섞이지 않게 데이터 폴더를 바꿀 수 있게 함
if (process.env.SQLKIWI_USER_DATA) app.setPath('userData', process.env.SQLKIWI_USER_DATA)

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    title: 'sqlkiwi',
    backgroundColor: '#f7f8f5',
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  })
  win.once('ready-to-show', () => win.show())
  // 화면 안 링크는 앱 창이 아니라 기본 브라우저로 엶
  win.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url)
    return { action: 'deny' }
  })
  if (process.env.ELECTRON_RENDERER_URL) void win.loadURL(process.env.ELECTRON_RENDERER_URL)
  else void win.loadFile(join(__dirname, '../renderer/index.html'))
}

/** IPC 처리기: 예외를 { ok: false, error } 응답으로 바꿔 화면이 다루기 쉽게 함 */
function handle<A extends unknown[], T>(channel: string, fn: (...args: A) => T | Promise<T>): void {
  ipcMain.handle(channel, async (_e, ...args: unknown[]): Promise<Reply<T>> => {
    try {
      return { ok: true, value: await fn(...(args as A)) }
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) }
    }
  })
}

function registerIpc(): void {
  handle('connections:list', () => store.listConnections())
  handle('connections:save', async (input: ConnectionInput) => {
    // 설정이 바뀌면 열려 있던 세션을 닫아 새 설정으로 다시 연결하게 함
    await sessions.disconnect(input.id)
    return store.saveConnection(input)
  })
  handle('connections:delete', async (id: string) => {
    await sessions.disconnect(id)
    store.deleteConnection(id)
  })
  handle('connections:test', (input: ConnectionInput) => sessions.testConnection(input))
  handle('connections:canStorePasswords', () => store.canStorePasswords())

  handle('session:connect', (id: string, password?: string) => sessions.connect(id, password))
  handle('session:disconnect', (id: string) => sessions.disconnect(id))
  handle('session:isConnected', (id: string) => sessions.isConnected(id))

  handle('meta:children', (id: string, parent: NavNode | null) => sessions.children(id, parent))
  handle('meta:completion', (id: string) => sessions.completionSchema(id))
  handle('meta:quote', (id: string, name: string) => sessions.quoteIdent(id, name))

  handle('query:execute', (id: string, sql: string, keepCursor: boolean) => sessions.execute(id, sql, keepCursor))
  handle('query:fetchMore', (resultId: string, all: boolean) => sessions.fetchMore(resultId, all))
  handle('query:close', (resultId: string) => sessions.closeResult(resultId))
  handle('query:cancel', (id: string) => sessions.cancel(id))

  handle('dialog:openSqlite', async () => {
    const r = await dialog.showOpenDialog({
      title: 'SQLite DB 파일 열기',
      properties: ['openFile'],
      filters: [
        { name: 'SQLite DB', extensions: ['db', 'sqlite', 'sqlite3', 'db3'] },
        { name: '모든 파일', extensions: ['*'] }
      ]
    })
    return r.canceled ? null : r.filePaths[0]
  })
  handle('dialog:newSqlite', async () => {
    const r = await dialog.showSaveDialog({
      title: '새 SQLite DB 파일',
      filters: [{ name: 'SQLite DB', extensions: ['db', 'sqlite'] }]
    })
    return r.canceled ? null : (r.filePath ?? null)
  })
}

app.whenReady().then(() => {
  registerIpc()
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  void sessions.disconnectAll().finally(() => {
    if (process.platform !== 'darwin') app.quit()
  })
})

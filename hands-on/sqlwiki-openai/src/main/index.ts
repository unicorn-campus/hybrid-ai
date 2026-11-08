import { app, BrowserWindow, dialog, ipcMain, safeStorage } from 'electron'
import { basename, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { readFile, stat, writeFile } from 'node:fs/promises'
import { createService } from './service'
import { toCsv } from './csv'
import type { Cell } from '../shared/types'

app.setName('sqlkiwi')
if (process.env.SQLKIWI_DATA_DIR) app.setPath('userData', resolve(process.env.SQLKIWI_DATA_DIR))

let window: BrowserWindow | null = null
let service: Awaited<ReturnType<typeof createService>>
const rendererFile = join(__dirname, '../renderer/index.html')
const devUrl = process.env.ELECTRON_RENDERER_URL

function trusted(event: Electron.IpcMainInvokeEvent): void {
  const frame = event.senderFrame
  if (!window || event.sender !== window.webContents || frame !== window.webContents.mainFrame) {
    throw new Error('허용되지 않은 요청입니다.')
  }
  const url = frame.url
  if (devUrl ? new URL(url).origin !== new URL(devUrl).origin : fileURLToPath(url) !== rendererFile) {
    throw new Error('허용되지 않은 화면입니다.')
  }
}

function handle(name: string, callback: (...args: any[]) => unknown) {
  ipcMain.handle(`sqlkiwi:${name}`, async (event, ...args: unknown[]) => {
    trusted(event)
    if (JSON.stringify(args).length > 16_000_000) throw new Error('요청 크기가 너무 큽니다.')
    return callback(...args)
  })
}

function createWindow() {
  window = new BrowserWindow({
    title: 'sqlkiwi', width: 1480, height: 960, minWidth: 1080, minHeight: 720,
    backgroundColor: '#12161d', autoHideMenuBar: true, show: false,
    webPreferences: { preload: join(__dirname, '../preload/index.js'), sandbox: true,
      contextIsolation: true, nodeIntegration: false, webSecurity: true }
  })
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  window.webContents.on('will-navigate', event => event.preventDefault())
  window.webContents.session.setPermissionRequestHandler((_webContents, _permission, callback) => callback(false))
  window.once('ready-to-show', () => window?.show())
  window.on('closed', () => { window = null })
  if (devUrl) void window.loadURL(devUrl)
  else void window.loadFile(rendererFile)
}

void app.whenReady().then(async () => {
  service = await createService(app.getPath('userData'), {
    encrypt: (value: string) => {
      if (!safeStorage.isEncryptionAvailable()) throw new Error('운영체제 암호 저장소를 사용할 수 없습니다.')
      return safeStorage.encryptString(value).toString('base64')
    },
    decrypt: (value: string) => safeStorage.decryptString(Buffer.from(value, 'base64'))
  })
  const methods = ['bootstrap', 'saveConnection', 'deleteConnection', 'testConnection', 'connect', 'disconnect',
    'schema', 'tableDetails', 'query', 'cancel', 'history', 'clearHistory', 'saveWorkspace'] as const
  for (const name of methods) handle(name, (...args: unknown[]) => (service[name] as Function).apply(service, args))
  handle('openDatabase', async () => {
    const result = await dialog.showOpenDialog(window!, { title: 'SQLite 데이터베이스 열기',
      filters: [{ name: 'SQLite', extensions: ['db', 'sqlite', 'sqlite3'] }, { name: '모든 파일', extensions: ['*'] }],
      properties: ['openFile'] })
    return result.canceled ? null : result.filePaths[0]
  })
  handle('openSql', async () => {
    const result = await dialog.showOpenDialog(window!, { title: 'SQL 파일 열기',
      filters: [{ name: 'SQL', extensions: ['sql'] }], properties: ['openFile'] })
    if (result.canceled) return null
    const path = result.filePaths[0]
    if ((await stat(path)).size > 2_000_000) throw new Error('SQL 파일은 2MB까지 열 수 있습니다.')
    return { name: basename(path), sql: await readFile(path, 'utf8') }
  })
  handle('saveSql', async (sql: string, name?: string) => {
    if (typeof sql !== 'string' || sql.length > 2_000_000) throw new Error('저장할 SQL을 확인해 주세요.')
    const result = await dialog.showSaveDialog(window!, { title: 'SQL 파일 저장',
      defaultPath: basename(typeof name === 'string' ? name : 'query.sql'), filters: [{ name: 'SQL', extensions: ['sql'] }] })
    if (result.canceled || !result.filePath) return false
    await writeFile(result.filePath, sql, 'utf8')
    return true
  })
  handle('exportCsv', async (columns: string[], rows: Cell[][]) => {
    if (!Array.isArray(columns) || !columns.every(value => typeof value === 'string') || !Array.isArray(rows)
      || !rows.every(row => Array.isArray(row) && row.every(value => value === null || ['string', 'number', 'boolean'].includes(typeof value)))) {
      throw new Error('내보낼 표를 확인해 주세요.')
    }
    const result = await dialog.showSaveDialog(window!, { title: 'CSV로 내보내기', defaultPath: 'sqlkiwi-results.csv',
      filters: [{ name: 'CSV', extensions: ['csv'] }] })
    if (result.canceled || !result.filePath) return false
    await writeFile(result.filePath, toCsv(columns, rows), 'utf8')
    return true
  })
  createWindow()
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow() })
}).catch(error => {
  dialog.showErrorBox('sqlkiwi 시작 오류', error instanceof Error ? error.message : String(error))
  app.exit(1)
})

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
let shuttingDown = false
app.on('before-quit', event => {
  if (!service || shuttingDown) return
  event.preventDefault()
  shuttingDown = true
  void Promise.resolve(service.dispose()).finally(() => app.quit())
})

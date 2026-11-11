import { contextBridge, ipcRenderer } from 'electron'
import type { SqlkiwiAPI } from '../shared/types'

const invoke = (name: string, ...args: unknown[]) => ipcRenderer.invoke(`sqlkiwi:${name}`, ...args)
const api: SqlkiwiAPI = {
  bootstrap: () => invoke('bootstrap'),
  saveConnection: value => invoke('saveConnection', value),
  deleteConnection: id => invoke('deleteConnection', id),
  testConnection: value => invoke('testConnection', value),
  connect: id => invoke('connect', id),
  disconnect: id => invoke('disconnect', id),
  schema: id => invoke('schema', id),
  tableDetails: (id, table) => invoke('tableDetails', id, table),
  query: value => invoke('query', value),
  cancel: id => invoke('cancel', id),
  history: () => invoke('history'),
  clearHistory: () => invoke('clearHistory'),
  saveWorkspace: value => invoke('saveWorkspace', value),
  openDatabase: () => invoke('openDatabase'),
  openSql: () => invoke('openSql'),
  saveSql: (sql, name) => invoke('saveSql', sql, name),
  exportCsv: (columns, rows) => invoke('exportCsv', columns, rows)
}
contextBridge.exposeInMainWorld('sqlkiwi', api)

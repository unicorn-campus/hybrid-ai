// 화면(renderer)에 열어 주는 API. Node 기능은 직접 주지 않고 정해진 IPC 통로만 엶
import { contextBridge, ipcRenderer } from 'electron'
import type { KiwiApi } from './api'

const call = (channel: string, ...args: unknown[]) => ipcRenderer.invoke(channel, ...args)

const api: KiwiApi = {
  connections: {
    list: () => call('connections:list'),
    save: (input) => call('connections:save', input),
    remove: (id) => call('connections:delete', id),
    test: (input) => call('connections:test', input),
    canStorePasswords: () => call('connections:canStorePasswords')
  },
  session: {
    connect: (id, password) => call('session:connect', id, password),
    disconnect: (id) => call('session:disconnect', id),
    isConnected: (id) => call('session:isConnected', id)
  },
  meta: {
    children: (id, parent) => call('meta:children', id, parent),
    completion: (id) => call('meta:completion', id),
    quote: (id, name) => call('meta:quote', id, name)
  },
  query: {
    execute: (id, sql, keepCursor) => call('query:execute', id, sql, keepCursor),
    fetchMore: (resultId, all) => call('query:fetchMore', resultId, all),
    close: (resultId) => call('query:close', resultId),
    cancel: (id) => call('query:cancel', id)
  },
  dialog: {
    openSqlite: () => call('dialog:openSqlite'),
    newSqlite: () => call('dialog:newSqlite')
  }
}

contextBridge.exposeInMainWorld('kiwi', api)

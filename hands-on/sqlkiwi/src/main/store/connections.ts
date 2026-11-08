// 연결 설정 저장소
// - 설정은 사용자 데이터 폴더의 connections.json에 저장함(DBeaver의 data-sources.json에 해당)
// - 비밀번호는 설정과 다른 파일(credentials.json)에 OS 보안 저장소(safeStorage)로 암호화해 저장함
//   DBeaver는 자체 키로 credentials-config.json을 암호화하지만,
//   sqlkiwi는 키를 앱에 넣지 않으려고 Windows DPAPI, macOS Keychain 등을 쓰는 safeStorage를 씀
import { app, safeStorage } from 'electron'
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type { ConnectionConfig, ConnectionInput } from '@shared/types'

interface StoreFile {
  version: 1
  connections: ConnectionConfig[]
}

function dataDir(): string {
  const dir = join(app.getPath('userData'), 'sqlkiwi')
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
  return dir
}

const configPath = (): string => join(dataDir(), 'connections.json')
const credentialPath = (): string => join(dataDir(), 'credentials.json')

/** 쓰다가 앱이 꺼져도 파일이 깨지지 않게 임시 파일에 쓴 뒤 바꿔 끼움 */
function writeJsonAtomic(path: string, value: unknown): void {
  const tmp = `${path}.tmp`
  writeFileSync(tmp, JSON.stringify(value, null, 2), 'utf8')
  renameSync(tmp, path)
}

function readJson<T>(path: string, fallback: T): T {
  if (!existsSync(path)) return fallback
  try {
    return JSON.parse(readFileSync(path, 'utf8')) as T
  } catch {
    return fallback
  }
}

export function listConnections(): ConnectionConfig[] {
  return readJson<StoreFile>(configPath(), { version: 1, connections: [] }).connections
}

export function getConnection(id: string): ConnectionConfig | undefined {
  return listConnections().find((c) => c.id === id)
}

/** password 칸을 떼어 내고 설정만 남김 */
export function stripPassword(input: ConnectionInput): ConnectionConfig {
  const { password: _ignored, ...config } = input
  return config
}

export function saveConnection(input: ConnectionInput): ConnectionConfig {
  const config = stripPassword(input)
  const all = listConnections().filter((c) => c.id !== config.id)
  all.push(config)
  writeJsonAtomic(configPath(), { version: 1, connections: all } satisfies StoreFile)

  if (config.savePassword && input.password !== undefined) {
    setPassword(config.id, input.password)
  } else if (!config.savePassword) {
    deletePassword(config.id)
  }
  return config
}

export function deleteConnection(id: string): void {
  const all = listConnections().filter((c) => c.id !== id)
  writeJsonAtomic(configPath(), { version: 1, connections: all } satisfies StoreFile)
  deletePassword(id)
}

// ---- 비밀번호 ----

type CredentialFile = Record<string, string> // id -> base64 암호문

export function canStorePasswords(): boolean {
  return safeStorage.isEncryptionAvailable()
}

function setPassword(id: string, password: string): void {
  if (!canStorePasswords()) {
    throw new Error('이 PC에서는 OS 보안 저장소를 쓸 수 없어 비밀번호를 저장하지 못함')
  }
  const creds = readJson<CredentialFile>(credentialPath(), {})
  creds[id] = safeStorage.encryptString(password).toString('base64')
  writeJsonAtomic(credentialPath(), creds)
}

export function getPassword(id: string): string | undefined {
  const creds = readJson<CredentialFile>(credentialPath(), {})
  const cipher = creds[id]
  if (!cipher || !canStorePasswords()) return undefined
  try {
    return safeStorage.decryptString(Buffer.from(cipher, 'base64'))
  } catch {
    return undefined
  }
}

function deletePassword(id: string): void {
  const creds = readJson<CredentialFile>(credentialPath(), {})
  if (id in creds) {
    delete creds[id]
    writeJsonAtomic(credentialPath(), creds)
  }
}

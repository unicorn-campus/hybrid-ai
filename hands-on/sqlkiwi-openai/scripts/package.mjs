import { cp, mkdir, rename, rm } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { dirname, resolve } from 'node:path'
import { spawnSync } from 'node:child_process'

if (process.platform !== 'win32') throw new Error('이 패키징 명령은 Windows용입니다.')
const require = createRequire(import.meta.url)
const runtime = dirname(require('electron'))
const destination = resolve('release/sqlkiwi-win32-x64')
if (dirname(destination) !== resolve('release')) throw new Error('패키지 출력 경로를 확인해 주세요.')
const appDir = resolve(destination, 'resources/app')
await rm(destination, { recursive: true, force: true })
await mkdir(appDir, { recursive: true })
await cp(runtime, destination, { recursive: true })
await rename(resolve(destination, 'electron.exe'), resolve(destination, 'sqlkiwi.exe'))
await cp(resolve('out'), resolve(appDir, 'out'), { recursive: true })
await cp(resolve('package.json'), resolve(appDir, 'package.json'))
await cp(resolve('package-lock.json'), resolve(appDir, 'package-lock.json'))
const npm = spawnSync('npm.cmd', ['ci', '--omit=dev', '--ignore-scripts', '--no-audit', '--no-fund'], {
  cwd: appDir, stdio: 'inherit', windowsHide: true, shell: true
})
if (npm.status !== 0) throw new Error('런타임 의존성 설치에 실패했습니다.')
console.log(`Windows 앱 생성: ${destination}/sqlkiwi.exe`)

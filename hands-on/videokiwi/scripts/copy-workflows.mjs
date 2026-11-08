import { cp, mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'

const destination = resolve('dist/server/workflows')
await mkdir(destination, { recursive: true })
await cp(resolve('src/server/workflows'), destination, { recursive: true })
console.log('로컬 H3 워크플로를 빌드 결과에 복사했습니다.')

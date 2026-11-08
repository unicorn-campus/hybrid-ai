import { resolve } from 'node:path'
import { defineConfig } from 'electron-vite'
import react from '@vitejs/plugin-react'

// 기본 폴더 규칙(src/main, src/preload, src/renderer)을 그대로 씀.
// main과 preload의 node_modules 의존성은 기본값(externalizeDeps: true)으로 번들에서 빠짐.
// better-sqlite3 같은 네이티브 모듈이 번들 안에 들어가지 않게 하려는 목적임.
export default defineConfig({
  main: {
    resolve: { alias: { '@shared': resolve(__dirname, 'src/shared') } }
  },
  preload: {
    resolve: { alias: { '@shared': resolve(__dirname, 'src/shared') } }
  },
  renderer: {
    resolve: { alias: { '@shared': resolve(__dirname, 'src/shared') } },
    plugins: [react()]
  }
})

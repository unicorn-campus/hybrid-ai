import { resolve } from 'node:path'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  resolve: { alias: { '@shared': resolve(__dirname, 'src/shared') } },
  test: {
    include: ['test/**/*.test.ts'],
    // DB 드라이버 시험은 Electron 안(ELECTRON_RUN_AS_NODE)에서만 돌림. npm run test:db 참고
    exclude: process.env.SQLKIWI_DB_TEST ? [] : ['test/**/*.db.test.ts'],
    testTimeout: 30000
  }
})

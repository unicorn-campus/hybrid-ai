/// <reference types="vite/client" />

import type { SqlkiwiAPI } from '../../shared/types'

declare global {
  interface Window { sqlkiwi: SqlkiwiAPI }
}

export {}

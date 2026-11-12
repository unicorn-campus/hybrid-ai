import type { ObskiwiApi } from '../shared/types';

declare global {
  interface Window {
    /** preload가 contextBridge로 노출한 main 연결 함수들 */
    obskiwi: ObskiwiApi;
  }
}

export {};

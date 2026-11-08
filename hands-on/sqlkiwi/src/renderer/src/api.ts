// preload API 응답({ ok, value } 또는 { ok: false, error })을 값 또는 예외로 바꿈
import type { Reply } from '@shared/types'

export const kiwi = window.kiwi

export async function unwrap<T>(p: Promise<Reply<T>>): Promise<T> {
  const r = await p
  if (!r.ok) throw new Error(r.error)
  return r.value
}

export const errorText = (e: unknown): string => (e instanceof Error ? e.message : String(e))

/** 연결 ID: DBeaver처럼 <종류>-<시각16진>-<난수16진> 형식 */
export function newConnectionId(kind: string): string {
  const rand = Math.floor(Math.random() * 0xffffffff).toString(16)
  return `${kind}-${Date.now().toString(16)}-${rand}`
}

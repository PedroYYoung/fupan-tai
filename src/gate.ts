// 前端口令：VITE_GATE_HASH 为空则整体关闭；非空则需 SHA-256 比对通过，
// 解锁态写入 sessionStorage，24 小时内免重输。
export const GATE_HASH: string = (import.meta.env.VITE_GATE_HASH as string | undefined ?? '').trim().toLowerCase()
const KEY = 'fupan_gate_until'
const TWENTY_FOUR_H = 24 * 60 * 60 * 1000

export function gateEnabled(): boolean {
  return GATE_HASH.length === 64
}

export function isUnlocked(): boolean {
  if (!gateEnabled()) return true
  const v = sessionStorage.getItem(KEY)
  if (!v) return false
  const until = Number(v)
  return Number.isFinite(until) && Date.now() < until
}

async function sha256Hex(input: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input))
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

export async function unlock(passwd: string): Promise<boolean> {
  if (!gateEnabled()) return true
  const hex = await sha256Hex(passwd.trim())
  if (hex === GATE_HASH) {
    sessionStorage.setItem(KEY, String(Date.now() + TWENTY_FOUR_H))
    return true
  }
  return false
}

export function lock(): void {
  sessionStorage.removeItem(KEY)
}

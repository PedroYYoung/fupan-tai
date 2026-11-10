// 交易日志（IndexedDB 本地存储，不上服务器）+ 报告页备注（notes store）
import { openDb, STORE_NOTES, STORE_LOGS } from './idb'

export interface TradeLog {
  date: string          // YYYYMMDD
  actions: string       // 操作记录
  tags: string[]        // 标签（多选）
  text: string          // 备注
  updated_at: string
}

// ===== 报告页备注（keyed by 日期）=====
export async function getNote(date: string): Promise<string> {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const req = db.transaction(STORE_NOTES, 'readonly').objectStore(STORE_NOTES).get(date)
    req.onsuccess = () => resolve(typeof req.result === 'string' ? req.result : '')
    req.onerror = () => reject(req.error)
  })
}

export async function setNote(date: string, text: string): Promise<void> {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NOTES, 'readwrite')
    tx.objectStore(STORE_NOTES).put(text, date)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

// ===== 交易日志 =====
export async function saveLog(log: TradeLog): Promise<void> {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_LOGS, 'readwrite')
    tx.objectStore(STORE_LOGS).put(log)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

export async function deleteLog(date: string): Promise<void> {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_LOGS, 'readwrite')
    tx.objectStore(STORE_LOGS).delete(date)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

export async function getAllLogs(): Promise<TradeLog[]> {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const req = db.transaction(STORE_LOGS, 'readonly').objectStore(STORE_LOGS).getAll()
    req.onsuccess = () => {
      const list = (req.result ?? []) as TradeLog[]
      resolve(list.sort((a, b) => (a.date < b.date ? 1 : -1)))
    }
    req.onerror = () => reject(req.error)
  })
}

export async function exportLogs(): Promise<void> {
  const logs = await getAllLogs()
  const blob = new Blob([JSON.stringify({ exported_at: new Date().toISOString(), logs }, null, 2)],
    { type: 'application/json' })
  const a = document.createElement('a')
  a.download = `交易日志备份_${new Date().toISOString().slice(0, 10)}.json`
  a.href = URL.createObjectURL(blob)
  a.click()
  URL.revokeObjectURL(a.href)
}

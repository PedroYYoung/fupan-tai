// 每日市场观察：人工编辑稿本地存储（IndexedDB，不上服务器）
// 编辑稿与原始生成数据（daily_observation/*.json）分离保存，按交易日期 keyed。
import { openDb, STORE_OBS } from './idb'

export interface ObservationEdit {
  date: string           // YYYYMMDD
  market_summary?: string   // 模块03 今日市场概况
  sector_text?: string      // 模块04 板块表现说明
  announcement_text?: string // 模块06 公司公告说明
  hidden?: string[]         // 隐藏的模块 id
  updated_at: string
}

export async function getObservationEdit(date: string): Promise<ObservationEdit | null> {
  try {
    const db = await openDb()
    return await new Promise((resolve, reject) => {
      const req = db.transaction(STORE_OBS, 'readonly').objectStore(STORE_OBS).get(date)
      req.onsuccess = () => resolve((req.result as ObservationEdit) ?? null)
      req.onerror = () => reject(req.error)
    })
  } catch {
    return null
  }
}

export async function saveObservationEdit(edit: ObservationEdit): Promise<void> {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_OBS, 'readwrite')
    tx.objectStore(STORE_OBS).put(edit)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

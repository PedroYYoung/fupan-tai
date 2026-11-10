// 共享 IndexedDB 打开逻辑（复盘台统一数据库「fupantai」）
// 统一版本号为 3，onupgradeneeded 幂等创建全部三个 object store：
//   notes     报告页备注（keyed by 日期）
//   logs      交易日志（keyPath: date）
//   obs_edits 每日市场观察编辑稿（keyPath: date）
//
// 健壮性约定（修复此前 IndexedDB 打开永不回调导致的页面卡死）：
// - 处理 onblocked（版本升级被旧连接阻塞时不再永久挂起，改为降级返回失败）
// - 增加超时（默认 2500ms），超时拒绝，调用方可降级为「无编辑稿」
// - onerror 正确 reject
export const DB_NAME = 'fupantai'
export const DB_VERSION = 3
export const STORE_NOTES = 'notes'
export const STORE_LOGS = 'logs'
export const STORE_OBS = 'obs_edits'

const DEFAULT_TIMEOUT = 2500

export function openDb(timeoutMs: number = DEFAULT_TIMEOUT): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    let settled = false
    const finish = (fn: () => void) => {
      if (settled) return
      settled = true
      fn()
    }

    let req: IDBOpenDBRequest
    try {
      req = indexedDB.open(DB_NAME, DB_VERSION)
    } catch (e) {
      reject(e)
      return
    }

    // 超时兜底：IndexedDB 无响应（如 headless 环境 / 版本升级被阻塞）时不再永久挂起
    const timer = setTimeout(() => {
      finish(() => reject(new Error('IndexedDB 打开超时')))
    }, timeoutMs)

    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE_NOTES)) db.createObjectStore(STORE_NOTES)
      if (!db.objectStoreNames.contains(STORE_LOGS)) db.createObjectStore(STORE_LOGS, { keyPath: 'date' })
      if (!db.objectStoreNames.contains(STORE_OBS)) db.createObjectStore(STORE_OBS, { keyPath: 'date' })
    }
    req.onsuccess = () => {
      clearTimeout(timer)
      finish(() => resolve(req.result))
    }
    req.onerror = () => {
      clearTimeout(timer)
      finish(() => reject(req.error ?? new Error('IndexedDB 打开失败')))
    }
    // 版本升级被其他打开的旧版本连接阻塞：不永久等待，直接失败降级
    req.onblocked = () => {
      clearTimeout(timer)
      finish(() => reject(new Error('IndexedDB 升级被阻塞')))
    }
  })
}

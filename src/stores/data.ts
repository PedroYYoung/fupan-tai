import { defineStore } from 'pinia'
import { ref } from 'vue'
import { router } from '@/router'
import type { DailyData, LatestPointer, SeriesFile, TradingDaysMeta } from '@/types'

const MIN_SAMPLE = 30

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: 'no-cache' })
  if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`)
  return res.json() as Promise<T>
}

export function formatDay(d: string): string {
  if (!/^\d{8}$/.test(d)) return d
  return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`
}

export const useDataStore = defineStore('data', () => {
  const loading = ref(true)
  const warnMsg = ref('')
  const meta = ref<TradingDaysMeta | null>(null)
  const latest = ref<LatestPointer | null>(null)
  const daily = ref<DailyData | null>(null)
  const currentDate = ref('')
  const isFallback = ref(false)

  let metaLoaded = false
  const seriesCache = new Map<string, SeriesFile | null>()

  /** 序列文件按需加载 + 内存缓存（供各模块页复用） */
  async function getSeries(key: string): Promise<SeriesFile | null> {
    if (seriesCache.has(key)) return seriesCache.get(key) ?? null
    try {
      const s = await getJson<SeriesFile>(`/data/series/${key}.json`)
      seriesCache.set(key, s)
      return s
    } catch {
      seriesCache.set(key, null)
      return null
    }
  }

  /** 日历回溯：全局切日期并同步 URL（可分享链接） */
  function gotoDate(date: string): void {
    router.push({ query: { ...router.currentRoute.value.query, date } })
  }

  // ===== 样本量计算（交易日窗口口径）=====
  function yearSampleN(): number {
    if (!meta.value || !currentDate.value) return 0
    const y = currentDate.value.slice(0, 4)
    return meta.value.list.filter((d) => d.startsWith(y) && d <= currentDate.value).length
  }
  function allSampleN(): number {
    if (!meta.value || !currentDate.value) return 0
    return meta.value.list.filter((d) => d <= currentDate.value).length
  }
  function oneYearSampleN(): number {
    return Math.min(allSampleN(), 244)
  }
  /** N<30 显示「样本不足」且不画折线 */
  function insufficient(n: number | null): boolean {
    return n == null || n < MIN_SAMPLE
  }

  async function loadDaily(date: string): Promise<boolean> {
    try {
      daily.value = await getJson<DailyData>(`/data/daily/${date}.json`)
      currentDate.value = date
      return true
    } catch {
      daily.value = null
      return false
    }
  }

  function syncUrl(date: string) {
    const route = router.currentRoute.value
    if (route.query.date !== date) {
      router.replace({ query: { ...route.query, date } })
    }
  }

  /**
   * 启动流程：读 meta + latest → 解析 ?date= → 缺省回退 latest →
   * 非法日期 / 缺失文件时自动回退最新交易日并弹黄色提示条
   */
  async function boot(): Promise<void> {
    loading.value = true
    warnMsg.value = ''
    try {
      if (!metaLoaded) {
        const [m, l] = await Promise.all([
          getJson<TradingDaysMeta>('/data/meta/trading_days.json'),
          getJson<LatestPointer>('/data/latest.json')
        ])
        meta.value = m
        latest.value = l
        metaLoaded = true
      }
      const m = meta.value!
      const l = latest.value!

      const q = typeof router.currentRoute.value.query.date === 'string'
        ? (router.currentRoute.value.query.date as string)
        : ''
      const lastUpdate = m.updated_at ?? ''

      if (q && q !== l.latest) {
        if (!/^\d{8}$/.test(q) || !m.list.includes(q)) {
          warnMsg.value = `日期 ${q} 不是有效交易日（最后更新：${lastUpdate}），已展示最近一个有效交易日 ${formatDay(l.latest)}`
        } else {
          const ok = await loadDaily(q)
          if (ok) {
            isFallback.value = false
            syncUrl(q)
            loading.value = false
            return
          }
          warnMsg.value = `该日期暂无数据（最后更新：${lastUpdate}），已展示最近一个有效交易日 ${formatDay(l.latest)}`
        }
        isFallback.value = true
      }

      // 回退到 latest
      const okLatest = await loadDaily(l.latest)
      if (!okLatest) {
        warnMsg.value = '数据文件缺失，站点暂无法展示（最后更新：' + lastUpdate + '）'
      }
      syncUrl(l.latest)
    } catch (e) {
      warnMsg.value = '数据加载失败：' + (e instanceof Error ? e.message : String(e))
    } finally {
      loading.value = false
    }
  }

  return {
    loading, warnMsg, meta, latest, daily, currentDate, isFallback,
    boot, getSeries, gotoDate, yearSampleN, allSampleN, oneYearSampleN, insufficient, formatDay
  }
})

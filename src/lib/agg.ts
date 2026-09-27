// 「本日/本月/本年/历史」四档聚合口径（只改聚合口径，不改指标定义）
import type { SeriesPoint } from '@/types'

export type Period = 'day' | 'month' | 'year' | 'all'

export const PERIODS: { key: Period; label: string }[] = [
  { key: 'day', label: '本日' },
  { key: 'month', label: '本月' },
  { key: 'year', label: '本年' },
  { key: 'all', label: '历史' }
]

export interface Agg {
  value: number | null
  /** 聚合值在对应样本中的降序排位（1=最大） */
  rank: number | null
  /** 年内窗口排位（仅本日档有） */
  rankYear: number | null
  /** 样本量 */
  sampleN: number
  /** 样本说明（如「历史月均值样本 N=81 个月」） */
  note: string
}

function mean(a: number[]): number | null {
  return a.length ? a.reduce((s, x) => s + x, 0) / a.length : null
}

function pctileOf(rank: number, n: number): number | null {
  return n > 1 ? Math.round(((n - rank) / (n - 1)) * 1000) / 10 : null
}

/** 与 series point 的 rank_year 同口径（降序排位） */
function rankIn(sample: number[], v: number): number | null {
  if (!sample.length) return null
  return sample.filter((x) => x > v).length + 1
}

export function aggregate(points: SeriesPoint[], date: string, period: Period): Agg {
  const valid = points.filter((p) => p.value != null)
  if (period === 'day') {
    const cur = valid.find((p) => p.date === date) ?? valid[valid.length - 1]
    if (!cur) return { value: null, rank: null, rankYear: null, sampleN: 0, note: '无当日数据' }
    const yearSample = valid.filter((p) => p.date.startsWith(date.slice(0, 4))).map((p) => p.value)
    const allSample = valid.map((p) => p.value)
    return {
      value: cur.value,
      rank: cur.rank_all ?? rankIn(allSample, cur.value),
      rankYear: cur.rank_year ?? rankIn(yearSample, cur.value),
      sampleN: allSample.length,
      note: `历史交易日样本 N=${allSample.length}`
    }
  }
  if (period === 'month') {
    const groups = new Map<string, number[]>()
    for (const p of valid) {
      const k = p.date.slice(0, 6)
      if (!groups.has(k)) groups.set(k, [])
      groups.get(k)!.push(p.value)
    }
    const months = [...groups.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1))
    const means = months.map(([, vals]) => mean(vals) ?? 0)
    const curIdx = months.findIndex(([k]) => k === date.slice(0, 6))
    const curMean = curIdx >= 0 ? means[curIdx] : means[means.length - 1]
    const rank = rankIn(means, curMean ?? 0)
    return {
      value: curMean,
      rank,
      rankYear: null,
      sampleN: means.length,
      note: `历史月均值样本 N=${means.length} 个月`
    }
  }
  if (period === 'year') {
    const groups = new Map<string, number[]>()
    for (const p of valid) {
      const k = p.date.slice(0, 4)
      if (!groups.has(k)) groups.set(k, [])
      groups.get(k)!.push(p.value)
    }
    const years = [...groups.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1))
    const means = years.map(([, vals]) => mean(vals) ?? 0)
    const curIdx = years.findIndex(([k]) => k === date.slice(0, 4))
    const curMean = curIdx >= 0 ? means[curIdx] : means[means.length - 1]
    const rank = rankIn(means, curMean ?? 0)
    return {
      value: curMean,
      rank,
      rankYear: null,
      sampleN: means.length,
      note: `历史年均值样本 N=${means.length} 个年度`
    }
  }
  // all：全历史均值（无排名意义，显示均值 + 样本量）
  const all = valid.map((p) => p.value)
  return { value: mean(all), rank: null, rankYear: null, sampleN: all.length, note: `全历史样本 N=${all.length}` }
}

export function pctileText(rank: number | null, n: number): string {
  if (rank == null || n < 30) return '样本不足'
  return `历史 ${pctileOf(rank, n)}%`
}

// ===== 基于 index_agg 预聚合表的指数/宽基四档计算 =====
import type { CodeAgg } from '@/types'

export interface CodeAggResult {
  value: number | null
  rank: number | null
  sampleN: number
}

/** 月/年/历史档：从预聚合表计算聚合值与排位 */
export function aggFromCodeAgg(agg: CodeAgg | undefined, date: string, period: Period): CodeAggResult {
  if (!agg) return { value: null, rank: null, sampleN: 0 }
  if (period === 'month') {
    const means = Object.entries(agg.months).sort((a, b) => (a[0] < b[0] ? -1 : 1)).map(([, v]) => v)
    const cur = agg.months[date.slice(0, 6)] ?? means[means.length - 1]
    return { value: cur, rank: rankIn(means, cur), sampleN: means.length }
  }
  if (period === 'year') {
    const means = Object.entries(agg.years).sort((a, b) => (a[0] < b[0] ? -1 : 1)).map(([, v]) => v)
    const cur = agg.years[date.slice(0, 4)] ?? means[means.length - 1]
    return { value: cur, rank: rankIn(means, cur), sampleN: means.length }
  }
  // all
  return { value: agg.all_mean, rank: null, sampleN: agg.count }
}

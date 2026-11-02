// 时间范围筛选与周期聚合工具（两市成交额「本周/本月/本年」、两融「日/周/月」）
// 关键：全部按自然周期（周一~周日 / 自然月 / 自然年），且只用真实有效交易日的日期，
// 周末、节假日不补 0、不虚构点。

export type Range = 'week' | 'month' | 'year'
export type Granularity = 'day' | 'week' | 'month'

export const RANGES: { key: Range; label: string }[] = [
  { key: 'week', label: '本周' },
  { key: 'month', label: '本月' },
  { key: 'year', label: '本年' }
]

export const GRANULARITIES: { key: Granularity; label: string }[] = [
  { key: 'day', label: '日' },
  { key: 'week', label: '周' },
  { key: 'month', label: '月' }
]

/** 自然周起始日（周一）的 YYYYMMDD */
export function weekKey(d: string): string {
  const dt = new Date(+d.slice(0, 4), +d.slice(4, 6) - 1, +d.slice(6, 8))
  const day = dt.getDay() || 7 // 1=周一 … 7=周日
  const mon = new Date(dt)
  mon.setDate(dt.getDate() - day + 1)
  return `${mon.getFullYear()}${String(mon.getMonth() + 1).padStart(2, '0')}${String(mon.getDate()).padStart(2, '0')}`
}

/** 判断日期 d 是否落在 ref 所在的自然周/月/年内 */
export function inRange(d: string, ref: string, r: Range): boolean {
  if (r === 'year') return d.slice(0, 4) === ref.slice(0, 4)
  if (r === 'month') return d.slice(0, 6) === ref.slice(0, 6)
  return weekKey(d) === weekKey(ref)
}

/**
 * 时点余额按自然周/月聚合：取该周期「最后一个有效交易日」的值（绝不累加）。
 * 输入需已按日期升序。
 */
export function aggregateLast(
  points: { date: string; value: number }[],
  g: 'week' | 'month'
): { date: string; value: number; label: string }[] {
  const groups = new Map<string, { date: string; value: number }>()
  for (const p of points) {
    const k = g === 'week' ? weekKey(p.date) : p.date.slice(0, 6)
    const cur = groups.get(k)
    if (!cur || p.date > cur.date) groups.set(k, { date: p.date, value: p.value })
  }
  return [...groups.values()]
    .sort((a, b) => (a.date < b.date ? -1 : 1))
    .map((x) => ({ ...x, label: g === 'week' ? weekKey(x.date).slice(4, 6) + '/' + weekKey(x.date).slice(6, 8) : x.date.slice(0, 4) + '-' + x.date.slice(4, 6) }))
}

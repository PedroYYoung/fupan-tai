// 统一百分比昨日变化展示格式（任务一）：今日主值在前，括号内显示与上一有效交易日的差值。
// 规则：
// - 百分比类：`今日%（±变化%）`，变化值 = 今日百分比数值 − 昨日百分比数值（不计算增长率）
// - 点位类：`3684.51（+12.30）`（点位差）
// - 金额类：`7324.75亿（-419.17亿）`（金额差）
// - 缺上一有效交易日：一律显示 `（—）`，不得用 `0` 代替
// - 不使用 `pct` 或「百分点」字样

/** 数值格式化：null/undefined → `—` */
export function fmtNum(n: number | null | undefined, digits = 2): string {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}

/** 带符号数值（正数带 +），null/undefined → ''；零 → `0`（不带符号、不带小数） */
function signed(v: number, digits: number): string {
  if (v === 0) return '0'
  return (v > 0 ? '+' : '') + fmtNum(v, digits)
}

/** 百分比变化括号：`（+1.2%）` / `（-1.2%）` / `（0%）` / `（—）` */
export function pctDelta(v: number | null | undefined, digits = 1): string {
  if (v == null) return '（—）'
  return `（${signed(v, digits)}%）`
}

/** 点位/金额等非百分比变化括号：`（+12.30）` / `（-419.17亿）` / `（—）` */
export function numDelta(v: number | null | undefined, digits = 2, unit = ''): string {
  if (v == null) return '（—）'
  return `（${signed(v, digits)}${unit}）`
}

/** 涨跌幅颜色类：涨红跌绿，平盘/缺失中性 */
export function pctClass(n: number | null | undefined): string {
  if (n == null) return 'muted'
  return n > 0 ? 'up' : n < 0 ? 'down' : 'muted'
}

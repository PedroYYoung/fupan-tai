// ===== 数据契约类型（与 data/*.json 严格对应）=====
export interface TradingDaysMeta {
  list: string[]
  latest: string
  updated_at: string
  source_versions: Record<string, string>
}

export interface LatestPointer {
  latest: string
  updated_at: string
}

export interface Overview {
  total_amount: number
  total_amount_rank_year: number | null
  total_amount_rank_all: number | null
  total_amount_pctile_all: number | null
  margin_balance: number | null
  /** 两融余额的实际统计日期（T+1 发布，可能早于 trade_date） */
  margin_date?: string | null
  margin_rank_year: number | null
  margin_pctile_all: number | null
  limit_up: number
  limit_down: number
  over_10e_count: number
  over_10e_ratio: number
  stock_count: number
}

export interface IndexRow {
  name: string
  code: string
  /** 当日成交额（亿）；接口抓取失败且无历史可降级时为 null */
  amount: number | null
  /** 成交额实际对应的交易日；降级时早于当前交易日 */
  amount_date?: string | null
  /** 取数说明：'' 当日真实值 / 'last_trading_day' 取自最近交易日 / 'etf_proxy' ETF 代理 */
  note?: string | null
  /** 当日涨跌幅（%）；无可用行情源时为 null */
  change_pct?: number | null
  /** 成交额较上一交易日的差值（亿）；任一侧缺失为 null */
  amount_change?: number | null
  rank_year: number | null
  rank_1y: number | null
  pctile_all: number | null
  approx?: boolean
}

export interface IndustryRow {
  name: string
  change: number
  amount: number
  ratio: number
}

export interface IndustryRankRow {
  name: string
  change: number
}

export interface ValueBucket {
  label: string
  count: number
  total_value: number
  pct: number
  /** 股票数量较上一交易日的差值；缺上一交易日为 null */
  count_change?: number | null
}

export interface IndexObservation {
  code: string
  name: string
  ytd_pct: number | null
  avg_week_amount: number | null
  avg_month_amount: number | null
  avg_year_amount: number | null
  /** 较上一交易日的差值（百分比指标为百分点差，均额为金额差） */
  ytd_pct_change?: number | null
  avg_week_change?: number | null
  avg_month_change?: number | null
  avg_year_change?: number | null
}

export interface StockRow {
  code: string
  name: string
  amount: number
  change?: number
  board?: string
  pct_of_total?: number
  /** 一级行业（如后端/映射表提供） */
  lv1?: string
  /** 二级行业（如后端/映射表提供） */
  lv2?: string
}

export interface Bucket {
  label: string
  count: number
  pct: number
  /** 股票数量较上一交易日的差值；缺上一交易日为 null */
  count_change?: number | null
}

export interface Concentration {
  top_n: number[]
  top10: StockRow[]
  top20: StockRow[]
  top50: StockRow[]
  top20_cum_pct: number
  top50_cum_pct: number
  top10_total_pctile_hist: number | null
}

export interface Emotion {
  limit_up: number
  limit_down: number
  lu_pctile: number | null
  ld_pctile: number | null
  lu_ratio_of_total: number
  ld_ratio_of_total: number
  lu_ratio_of_over10e: number
  ld_ratio_of_over10e: number
  lu_over10e: StockRow[]
  ld_over10e: StockRow[]
}

export interface Sparklines {
  total_amount: { date: string; value: number }[]
  margin: { date: string; value: number }[]
  limit_up_down: { date: string; up: number; down: number }[]
  over_10e_count: { date: string; value: number }[]
}

export interface SeriesPoint {
  date: string
  value: number
  rank_year?: number | null
  rank_1y?: number | null
  rank_all?: number | null
  pctile?: number | null
}

export interface SeriesFile {
  key: string
  name: string
  unit: string
  updated_at: string
  points: SeriesPoint[]
}

export interface BucketPoint {
  date: string
  buckets: Bucket[]
}

export interface BucketSeriesFile {
  key: string
  name: string
  unit: string
  updated_at: string
  points: BucketPoint[]
}

export interface CodeAgg {
  name: string
  months: Record<string, number>
  years: Record<string, number>
  all_mean: number
  count: number
}

export interface IndexAggFile {
  updated_at: string
  codes: Record<string, CodeAgg>
}

export interface DailyData {
  trade_date: string
  overview: Overview
  index_volume: IndexRow[]
  widebase: IndexRow[]
  industry?: {
    top10_up: IndustryRow[]
    top10_down: IndustryRow[]
    /** 数据源：eastmoney / ths */
    source?: string
    /** 口径说明 */
    note?: string
    /** 继承场景下的真实数据日期 */
    as_of?: string
  }
  concentration: Concentration
  liquidity: {
    over_10e_count: number
    over_10e_ratio: number
    pctile_count: number | null
    mktcap_buckets: Bucket[]
    amount_buckets?: Bucket[]
    over_10e_marketcap_buckets?: Bucket[]
    over_10e_marketcap_value_buckets?: ValueBucket[]
  }
  emotion: Emotion
  sparklines?: Sparklines
  index_observation?: IndexObservation[]
  industry_week_rank?: {
    top5: IndustryRankRow[]
    bottom5: IndustryRankRow[]
  }
}

export interface ConclusionItem {
  text: string
  basis: string
}

export interface Conclusion {
  fund: ConclusionItem
  structure: ConclusionItem
  emotion: ConclusionItem
  score: number
}

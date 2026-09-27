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
  amount: number
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

export interface StockRow {
  code: string
  name: string
  amount: number
  change?: number
  board?: string
  pct_of_total?: number
}

export interface Bucket {
  label: string
  count: number
  pct: number
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
  }
  concentration: Concentration
  liquidity: {
    over_10e_count: number
    over_10e_ratio: number
    pctile_count: number | null
    mktcap_buckets: Bucket[]
  }
  emotion: Emotion
  sparklines?: Sparklines
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

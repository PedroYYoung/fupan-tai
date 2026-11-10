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
  limit_up: number | null
  limit_down: number | null
  /** 以下三项依赖全市场实时快照；无可靠历史来源时为 null（展示「—」，不填 0） */
  over_10e_count: number | null
  over_10e_ratio: number | null
  stock_count: number | null
}

/** 全市场快照派生字段的数据质量标记 */
export type SpotDerivedQuality = 'realtime' | 'carried_over' | 'unavailable'

export interface DataQuality {
  /** realtime=本次实时抓取 / carried_over=沿用旧快照原值 / unavailable=无可靠来源、字段已置空 */
  spot_derived?: SpotDerivedQuality
  note?: string
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
  /** 当日收盘点位；无可用行情源时为 null */
  close?: number | null
  /** 点位较上一交易日的差值；任一侧缺失为 null */
  close_change?: number | null
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
  /** 占比较上一交易日的差值（百分点）；缺上一交易日为 null */
  pct_change?: number | null
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
  /** 占比较上一交易日的差值（百分点）；缺上一交易日为 null */
  pct_change?: number | null
}

export interface Concentration {
  top_n: number[]
  top10: StockRow[]
  top20: StockRow[]
  top50: StockRow[]
  /** 以下累计占比依赖全市场实时快照；无可靠历史来源时为 null（展示「—」，不填 0） */
  top20_cum_pct: number | null
  top50_cum_pct: number | null
  top10_total: number | null
  top10_total_pctile_hist: number | null
  /** Top10/Top20/Top50 累计占比较上一交易日的差值（百分点）；缺上一交易日为 null */
  top10_change?: number | null
  top20_change?: number | null
  top50_change?: number | null
  /** 变化值实际比较的交易日（YYYYMMDD）；回退到早于「前一交易日」时用于展示真实比较日期 */
  concentration_change_date?: string | null
}

export interface Emotion {
  limit_up: number | null
  limit_down: number | null
  lu_pctile: number | null
  ld_pctile: number | null
  /** 占比依赖全市场快照家数；缺失时为 null（展示「—」，不填 0） */
  lu_ratio_of_total: number | null
  ld_ratio_of_total: number | null
  lu_ratio_of_over10e: number | null
  ld_ratio_of_over10e: number | null
  /** 成交额≥5亿的涨停/跌停家数 */
  lu_over5e_count?: number
  ld_over5e_count?: number
  lu_over10e: StockRow[]
  ld_over10e: StockRow[]
}

/** 高活跃个股（当日成交额≥5亿 且 涨幅≥5%） */
export interface ActiveStock {
  code: string
  name: string
  close: number
  change_pct: number
  amount: number
  is_limit_up: boolean
}

export interface Sparklines {
  total_amount: { date: string; value: number }[]
  margin: { date: string; value: number }[]
  /** down 为 null 表示该日无跌停数据（东财跌停池只保留最近 30 天），不是 0 家 */
  limit_up_down: { date: string; up: number; down: number | null }[]
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
    over_10e_count: number | null
    over_10e_ratio: number | null
    pctile_count: number | null
    mktcap_buckets: Bucket[]
    amount_buckets?: Bucket[]
    over_10e_marketcap_buckets?: Bucket[]
    over_10e_marketcap_value_buckets?: ValueBucket[]
  }
  emotion: Emotion
  /** 实时快照派生字段的数据质量标记（缺失视为 normal 旧数据） */
  data_quality?: DataQuality
  /** 高活跃个股（≥5亿且涨幅≥5%） */
  active_stocks?: ActiveStock[]
  sparklines?: Sparklines
  index_observation?: IndexObservation[]
  industry_week_rank?: {
    top5: IndustryRankRow[]
    bottom5: IndustryRankRow[]
  }
}

/** 单个规则信号（多信号累积，不再互相覆盖） */
export interface SignalTag {
  /** 信号标签，如「成交高度集中」「小微盘活跃」「结构分化」 */
  label: string
  /** 信号方向：risk=风险/扣分，positive=积极/加分，neutral=中性（如分化标签，不改分） */
  direction: 'risk' | 'positive' | 'neutral'
  /** 加减分贡献（中性信号为 0） */
  delta: number
  /** 该信号的具体数据依据 */
  basis: string
}

export interface ConclusionItem {
  text: string
  basis: string
  /** 段落式结论（报告页用，比 text 更完整） */
  paragraph?: string
  /** 维度得分（0 ~ scoreMax） */
  score?: number
  /** 维度满分 */
  scoreMax?: number
  /** 触发的信号列表（多信号累积，含「结构分化」等中性标签） */
  tags?: SignalTag[]
}

export interface Conclusion {
  fund: ConclusionItem
  structure: ConclusionItem
  emotion: ConclusionItem
  score: number
  /** 综合结论段落 */
  summary?: string
  /** 评分明细（用于报告页展示维度得分拆解） */
  scoreDetail?: string
}

// ===== 每日市场观察（/daily-observation）数据契约 =====
// 对应 public/data/daily_observation/YYYYMMDD.json（由 scripts/build_observation.py 生成）

export interface MetricValue {
  value: number | null
  /** 较上一有效交易日的绝对变化量 */
  change: number | null
  /** 变化百分比（%）；计数类指标为 null，用绝对变化量表达 */
  change_pct: number | null
  unit?: string
  /** 两融余额的真实统计日期（T+1） */
  stat_date?: string | null
  /** 两融上一次有效统计日期（比较两条实际有效记录） */
  prev_stat_date?: string | null
  /** 两融上一次有效统计值 */
  prev_value?: number | null
  /** pp=百分点变化（集中度），abs=绝对变化 */
  change_kind?: 'pp' | 'abs'
}

export interface ObservationMarketMetrics {
  total_amount: MetricValue
  limit_up: MetricValue
  limit_down: MetricValue
  over_10e_count: MetricValue
  top10_pct: MetricValue
  top20_pct: MetricValue
  top50_pct: MetricValue
  margin_balance: MetricValue
  stock_count: MetricValue
}

export interface SectorRankRow {
  name: string
  change: number
  amount: number
  ratio: number | null
  amount_change: number | null
}

export interface ResonanceIndicator {
  label: string
  weight: number
  value: number | null
  valid: boolean
  pctile?: number | null
}

export interface ResonanceBoard {
  name: string
  category: string
  change: number
  relative_strength: number | null
  up_ratio: number | null
  amount: number
  amount_change: number | null
  limit_up_count: number | null
  limit_up_density: number | null
  /** 有效指标数量 / 5 */
  valid_count: number
  indicators: Record<string, ResonanceIndicator>
  /** 0~100 共振参考分；仅 valid_count>=4 时有值，否则为 null（不显示评分） */
  raw_score: number | null
  representative_stocks: StockRankRow[]
  representative_note?: string
  /** 板块成分股总数（东财当日数据） */
  constituent_count?: number | null
  /** 领涨股 */
  lead_name?: string | null
  lead_code?: string | null
  lead_limit_up?: boolean | null
}

export interface SectorResonance {
  board: ResonanceBoard | null
  benchmark: number | null
  benchmark_name: string
  note: string
  /** 是否达到「≥4 项有效」的完整共振门槛（进入正式排名） */
  qualified_full: boolean
  /** 正式排名候选数 */
  qualified_count?: number
  /** 行业榜首 / 概念榜首（东财当日独立排名） */
  industry_top?: ResonanceBoard | null
  concept_top?: ResonanceBoard | null
  /** 数据来源：ths_top10 | eastmoney_push2 */
  source?: string
}

export interface StockRankRow {
  code: string
  name: string
  change_pct?: number
  change?: number
  amount: number
  is_limit_up?: boolean
  board?: string
}

export interface RiskEventSource {
  name: string
  url: string
  status: string
  meta?: Record<string, unknown>
}

/** 一条公司公告 / 监管 / 媒体事件（客观事实，非投资评价） */
export interface ObservationEvent {
  event_id: string
  event_date: string
  published_at: string | null
  collected_at?: string
  company_name: string
  stock_code: string
  source_type: string          // announcement | regulation | media
  source_name: string
  event_category: string       // 经营进展 / 业绩信息 / 股东行为 / 资本运作 / 监管事项 / 法律事项 / 行业政策 / 宏观事件 / 其他信息
  category_group: 'positive' | 'risk' | 'neutral'  // A 积极进展 / B 风险监管 / C 其他
  title: string
  factual_summary: string
  event_status: string
  original_url: string
  related_primary_url?: string
  verification_status: string  // official_confirmed | unverified
  duplicate_key?: string
  is_routine?: boolean
}

export interface SourceCoverageItem {
  status: 'available' | 'missing' | 'unavailable'
  detail: string
}

/** 六大指数当日行情 */
export interface IndexQuote {
  name: string
  code: string
  close: number | null
  change_pct: number | null
  change_points: number | null
  prev_close: number | null
}

/** 板块涨跌 Top5 行 */
export interface SectorTopRow {
  name: string
  category: string       // 行业 | 概念
  change: number | null
  amount: number | null
  limit_up_count: number | null
  limit_down_count: number | null
}

export interface MktcapBucket {
  label: string
  count: number
  pct: number | null
}

export interface ObservationData {
  trade_date: string
  generated_at: string
  report_trade_date?: string
  coverage_window_start?: string
  coverage_cutoff_at?: string
  market_metrics: ObservationMarketMetrics
  indexes: IndexQuote[]
  market_summary: string
  sector_top5: {
    industry: { up: SectorTopRow[]; down: SectorTopRow[]; source?: string; note?: string }
    concept: { up: SectorTopRow[] | null; down: SectorTopRow[] | null; source?: string | null; note: string }
  }
  mktcap_dist: {
    buckets: MktcapBucket[]
    sample_total: number | null
    missing_mktcap: number | null
    note: string
  }
  risk_events: {
    events: ObservationEvent[]
    groups: { buyback: ObservationEvent[]; risk: ObservationEvent[] }
    coverage_status: string
    message: string
    sources: RiskEventSource[]
    total_events?: number
    displayed_events?: number
  }
  source_coverage: Record<string, SourceCoverageItem>
  data_warnings: string[]
  ai_generated: boolean
  generation_mode: string
  disclaimer?: string
}

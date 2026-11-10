# 每日市场观察 · 数据结构文档（第三版）

> 数据文件：`public/data/daily_observation/YYYYMMDD.json`
> 由 `scripts/build_observation.py` 从复盘台现有 `public/data/daily/YYYYMMDD.json` 派生，并采集外部来源，**不改写核心快照**。

## 顶层字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `trade_date` | string | 交易日 YYYYMMDD |
| `generated_at` | string | 生成时间（ISO 8601，北京时间） |
| `report_trade_date` | string | 报告对应交易日 |
| `coverage_window_start` / `coverage_cutoff_at` | string | 覆盖窗口起点 / 采集截止时间 |
| `market_metrics` | object | 01 市场核心数据（含两融变化、Top50） |
| `indexes` | object[] | 02 六大指数行情 |
| `market_summary` | string | 03 今日市场概况（融合指数与板块） |
| `sector_top5` | object | 04 行业及概念板块涨跌榜（行业/概念独立） |
| `mktcap_dist` | object | 05 成交额≥10亿股票市值分布（六档） |
| `risk_events` | object | 06 重要公告（回购 / 风险减持两组） |
| `source_coverage` / `data_warnings` | — | 来源覆盖 / 数据缺失提示 |
| `disclaimer` | string | 统一免责声明 |

## 关键字段

### market_metrics
键：`total_amount`、`margin_balance`、`limit_up`、`limit_down`、`over_10e_count`、`top50_pct`、`stock_count`（另保留 `top10_pct`/`top20_pct` 底层数据但客户展示不再使用）。
`margin_balance` 新增：`change`（较上一次有效统计日增减）、`prev_stat_date`、`prev_value`、`stat_date`（真实统计日）。两融变化比较两条实际有效记录，不拿相邻交易日强行匹配。

### indexes
六大指数：上证指数(sh000001)、深证成指(sz399001)、创业板指(sz399006)、科创50(sh000688)、中证500(sh000905)、中证1000(sh000852)。
每项 `{name, code, close, change_pct, change_points, prev_close}`。涨跌点数 = 当日收盘 − 上一有效交易日收盘（上一收盘缺失时按涨跌幅反推）。

### sector_top5
`{ industry: {up[], down[], source, note}, concept: {up[], down[], source, note} }`。行业/概念独立排序，各取涨跌 Top5。每行 `{name, category, change, amount, limit_up_count, limit_down_count}`。涨跌停家数按板块真实成分股计算（东财当日）；历史未采集时为 null。

### mktcap_dist
成交额≥10亿股票的总市值六档（<50 / 50-100 / 100-200 / 200-500 / 500-1000 / >1000 亿元，按家数）。
`{buckets[], sample_total, missing_mktcap, note}`。基于东财全市场快照（当日），历史不可回溯时 sample_total=null，不复用全A分档。

### risk_events
`{events[]（全量溯源）, groups: {buyback[], risk[]}, coverage_status, message, sources[]}`。
- `buyback`：公司回购名单（同公司合并，前 N 条）。
- `risk`：风险/监管/股东减持名单（同公司同类别合并）。

## 数据源能力边界（最终版）

| 模块 | 数据来源 | 状态 |
|---|---|---|
| 核心指标 + 环比 + 两融变化 | 现有 daily 快照 + series/margin | ✅ 可用 |
| 六大指数 | daily 快照 index_volume/widebase | ✅ 可用（涨跌点反推） |
| 行业板块 Top5 | 东财行业（当日）/ 同花顺 Top10（历史） | ⚠️ 历史无涨跌停家数 |
| 概念板块 Top5 | 东财概念（当日） | ⚠️ 历史未采集 |
| 市值分布饼图 | 东财全市场快照（当日） | ⚠️ 历史不可回溯 |
| 公司公告 | 巨潮资讯网（可回溯历史） | ✅ 可采集 |
| 交易所监管 / 证监会 | 官网接口 | ⚠️ 需精确参数/反爬，未接入 |
| 财联社/中证网/证券时报/上证报 | — | ⚠️ 无稳定结构化接口，未接入 |

环比一律使用「上一个有效交易日」。事件分类仅说明客观性质，不构成对股价影响的判断。

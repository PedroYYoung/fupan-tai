<script setup lang="ts">
import { computed } from 'vue'
import type { DailyData, Conclusion } from '../types'

const props = defineProps<{
  daily: DailyData
  conclusion: Conclusion
  note: string
  /** 数据更新时间（latest.json 的 updated_at，可选） */
  updatedAt?: string | null
}>()

// ---- 格式化 ----
function fmt(n: number | null | undefined, digits = 0): string {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}
function signed(n: number | null | undefined, digits = 1): string {
  if (n == null) return '—'
  const s = n.toFixed(digits)
  return n > 0 ? `+${s}` : s
}
function pctOrDash(n: number | null | undefined): string {
  return n != null ? n + '%' : '—'
}
function formatDay(d: string): string {
  return /^\d{8}$/.test(d) ? `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}` : d
}

// ---- 环比（前一交易日，从 sparklines 计算）----
function momPct(spark: { date: string; value: number }[] | undefined): number | null {
  if (!spark || spark.length < 2) return null
  const prev = spark[spark.length - 2].value
  const cur = spark[spark.length - 1].value
  if (!prev) return null
  return ((cur - prev) / prev) * 100
}
function momDelta(spark: { date: string; value: number }[] | undefined): number | null {
  if (!spark || spark.length < 2) return null
  return spark[spark.length - 1].value - spark[spark.length - 2].value
}
const sp = computed(() => props.daily.sparklines)
const amtMom = computed(() => momPct(sp.value?.total_amount))
const marginDelta = computed(() => momDelta(sp.value?.margin))
const luDelta = computed(() => {
  const s = sp.value?.limit_up_down
  if (!s || s.length < 2) return null
  return s[s.length - 1].up - s[s.length - 2].up
})
const ldDelta = computed(() => {
  const s = sp.value?.limit_up_down
  if (!s || s.length < 2) return null
  const a = s[s.length - 1].down
  const b = s[s.length - 2].down
  if (a == null || b == null) return null
  return a - b
})
const o10Delta = computed(() => momDelta(sp.value?.over_10e_count))

// ---- 信号标签样式 ----
function tagStyle(direction: string): Record<string, string> {
  const color = direction === 'risk' ? '#C0392B' : direction === 'positive' ? '#1E8449' : '#B7950B'
  return {
    display: 'inline-block',
    margin: '0 8px 6px 0',
    padding: '3px 10px',
    borderRadius: '4px',
    fontSize: '15px',
    fontWeight: '600',
    border: `1px solid ${color}`,
    color,
    background: direction === 'risk' ? '#FBEAE9' : direction === 'positive' ? '#EAF7EE' : '#FDF6E3'
  }
}
function deltaText(delta: number): string {
  return delta > 0 ? ` +${delta} 分` : delta < 0 ? ` ${delta} 分` : ' 0 分'
}

// ---- 指标表 ----
interface MetricRow { name: string; value: string; mom: string; momClass: string; pctile: string; rank: string }
const metricRows = computed<MetricRow[]>(() => {
  const d = props.daily
  const o = d.overview
  const c = d.concentration
  const liq = d.liquidity
  const momClass = (v: number | null) => (v == null ? '' : v > 0 ? 'up' : v < 0 ? 'down' : '')
  return [
    {
      name: '两市成交额', value: fmt(o.total_amount) + ' 亿元',
      mom: amtMom.value != null ? signed(amtMom.value) + '%' : '—', momClass: momClass(amtMom.value),
      pctile: pctOrDash(o.total_amount_pctile_all), rank: o.total_amount_rank_year != null ? `年内第 ${o.total_amount_rank_year}` : '—'
    },
    {
      name: '两融余额', value: o.margin_balance != null ? fmt(o.margin_balance) + ' 亿元' : '—',
      mom: marginDelta.value != null ? signed(marginDelta.value) + ' 亿' : '—', momClass: momClass(marginDelta.value),
      pctile: pctOrDash(o.margin_pctile_all), rank: o.margin_rank_year != null ? `年内第 ${o.margin_rank_year}` : '—'
    },
    {
      name: '涨停家数', value: fmt(o.limit_up) + ' 家',
      mom: luDelta.value != null ? signed(luDelta.value, 0) : '—', momClass: momClass(luDelta.value),
      pctile: pctOrDash(d.emotion.lu_pctile), rank: '—'
    },
    {
      name: '跌停家数', value: fmt(o.limit_down) + ' 家',
      mom: ldDelta.value != null ? signed(ldDelta.value, 0) : '—', momClass: momClass(ldDelta.value),
      pctile: pctOrDash(d.emotion.ld_pctile), rank: '—'
    },
    {
      name: '10亿以上家数', value: fmt(o.over_10e_count) + ' 家',
      mom: o10Delta.value != null ? signed(o10Delta.value, 0) : '—', momClass: momClass(o10Delta.value),
      pctile: pctOrDash(liq.pctile_count), rank: '—'
    },
    {
      name: '前10成交占比', value: c.top10_total != null ? fmt(c.top10_total, 1) + '%' : '—',
      mom: c.top10_change != null ? signed(c.top10_change, 2) + 'pp' : '—', momClass: momClass(c.top10_change ?? null),
      pctile: pctOrDash(c.top10_total_pctile_hist), rank: '—'
    },
    {
      name: '前20成交占比', value: c.top20_cum_pct != null ? fmt(c.top20_cum_pct, 1) + '%' : '—',
      mom: c.top20_change != null ? signed(c.top20_change, 2) + 'pp' : '—', momClass: momClass(c.top20_change ?? null),
      pctile: '—', rank: '—'
    },
    {
      name: '前50成交占比', value: c.top50_cum_pct != null ? fmt(c.top50_cum_pct, 1) + '%' : '—',
      mom: c.top50_change != null ? signed(c.top50_change, 2) + 'pp' : '—', momClass: momClass(c.top50_change ?? null),
      pctile: '—', rank: '—'
    }
  ]
})

// ---- 口径说明 ----
const spotNote = computed(() => props.daily.data_quality?.note ?? '')
const marginDate = computed(() => props.daily.overview.margin_date ?? '')
</script>

<template>
  <div id="report-export" class="export">
    <!-- 1. 标题 -->
    <header class="r-header">
      <div class="r-brand">复盘台 · fupan-tai</div>
      <h1 class="r-title">A股市场每日复盘</h1>
      <div class="r-meta">
        交易日：<strong>{{ formatDay(daily.trade_date) }}</strong>
        <span v-if="updatedAt">｜ 数据更新：{{ updatedAt }}</span>
        <span>｜ 时区：Asia/Shanghai（北京时间）</span>
      </div>
    </header>

    <!-- 2. 市场核心指标 -->
    <section class="r-section">
      <h2 class="r-h2">一、市场核心指标</h2>
      <table class="r-table">
        <thead>
          <tr><th>指标</th><th>当日数据</th><th>较前一交易日</th><th>历史百分位</th><th>年内排名</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in metricRows" :key="r.name">
            <td class="r-td-name">{{ r.name }}</td>
            <td class="r-num">{{ r.value }}</td>
            <td class="r-num" :class="r.momClass">{{ r.mom }}</td>
            <td class="r-num">{{ r.pctile }}</td>
            <td class="r-num">{{ r.rank }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 3. 三维分析 -->
    <section class="r-section">
      <h2 class="r-h2">二、市场三维分析</h2>

      <div class="r-block">
        <h3 class="r-h3">资金面 <span class="r-score">{{ conclusion.fund.score }}/{{ conclusion.fund.scoreMax }} 分</span></h3>
        <p class="r-p">{{ conclusion.fund.paragraph }}</p>
        <div class="r-basis">依据：{{ conclusion.fund.basis }}</div>
      </div>

      <div class="r-block">
        <h3 class="r-h3">结构面 <span class="r-score">{{ conclusion.structure.score }}/{{ conclusion.structure.scoreMax }} 分</span></h3>
        <div v-if="conclusion.structure.tags?.length" class="r-tags">
          <span v-for="t in conclusion.structure.tags" :key="t.label" :style="tagStyle(t.direction)">{{ t.label }} {{ deltaText(t.delta) }}</span>
        </div>
        <p class="r-p">{{ conclusion.structure.paragraph }}</p>
        <div class="r-basis">依据：{{ conclusion.structure.basis }}</div>
      </div>

      <div class="r-block">
        <h3 class="r-h3">情绪面 <span class="r-score">{{ conclusion.emotion.score }}/{{ conclusion.emotion.scoreMax }} 分</span></h3>
        <div v-if="conclusion.emotion.tags?.length" class="r-tags">
          <span v-for="t in conclusion.emotion.tags" :key="t.label" :style="tagStyle(t.direction)">{{ t.label }} {{ deltaText(t.delta) }}</span>
        </div>
        <p class="r-p">{{ conclusion.emotion.paragraph }}</p>
        <div class="r-basis">依据：{{ conclusion.emotion.basis }}</div>
      </div>
    </section>

    <!-- 4. 综合结论 -->
    <section class="r-section">
      <h2 class="r-h2">三、综合市场结论 <span class="r-total">{{ conclusion.score }}/100 分</span></h2>
      <p class="r-p">{{ conclusion.summary }}</p>
      <div class="r-basis">评分拆解：{{ conclusion.scoreDetail }}</div>
    </section>

    <!-- 5. 人工备注 -->
    <section class="r-section">
      <h2 class="r-h2">四、人工备注</h2>
      <p class="r-p r-note">{{ note ? note : '本日暂无人工备注' }}</p>
    </section>

    <!-- 6. 口径说明 -->
    <footer class="r-footer">
      <div class="r-h2">五、数据口径与说明</div>
      <ul class="r-notes">
        <li>数据来源：通达信本地行情 + 东方财富/腾讯/baostock 实时接口，指数成交额与两市合计为「上证 + 深证」指数口径。</li>
        <li>两融余额为时点存量，T+1 发布<template v-if="marginDate">，本报告两融实际统计日期为 {{ formatDay(marginDate) }}</template>；无当日统计值时保留真实统计日期，不伪造。</li>
        <li>涨跌停家数、10亿以上家数、集中度等依赖全市场实时快照；无可靠历史来源时显示「—」，不填 0。</li>
        <li>历史百分位为「当前值在自身历史有效样本中的经验百分位」，样本量不足时不生成判断。</li>
        <li>结构/情绪信号标签：风险=扣分、积极=加分、中性=分化标记；涨红跌绿。</li>
        <li v-if="spotNote">本日数据备注：{{ spotNote }}</li>
      </ul>
    </footer>
  </div>
</template>

<style scoped>
.export {
  width: 1200px;
  background: #ffffff;
  color: #111418;
  font-size: 18px;
  line-height: 1.7;
  padding: 36px 40px;
  box-sizing: border-box;
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', sans-serif;
}
.r-header { border-bottom: 3px solid #C0392B; padding-bottom: 18px; margin-bottom: 26px; }
.r-brand { font-size: 14px; color: #8B949E; letter-spacing: 1px; }
.r-title { font-size: 30px; font-weight: 700; margin: 6px 0 8px; color: #111418; }
.r-meta { font-size: 15px; color: #444; }
.r-meta strong { color: #C0392B; }
.r-section { margin-bottom: 26px; }
.r-h2 { font-size: 22px; font-weight: 700; color: #111418; border-left: 4px solid #C0392B; padding-left: 10px; margin: 0 0 14px; }
.r-total { color: #C0392B; }
.r-table { width: 100%; border-collapse: collapse; }
.r-table th, .r-table td { border: 1px solid #E5E7EB; padding: 9px 12px; text-align: left; font-size: 17px; }
.r-table th { background: #F6F8FA; font-weight: 600; }
.r-td-name { font-weight: 600; color: #111418; }
.r-num { text-align: right; font-variant-numeric: tabular-nums; }
.r-block { margin-bottom: 18px; }
.r-h3 { font-size: 19px; font-weight: 700; margin: 0 0 6px; color: #111418; }
.r-score { font-weight: 600; color: #57606A; font-size: 16px; }
.r-tags { margin: 6px 0 4px; }
.r-p { margin: 0 0 8px; white-space: pre-wrap; }
.r-note { white-space: pre-wrap; color: #111418; }
.r-basis { font-size: 14px; color: #57606A; }
.r-footer { border-top: 2px solid #E5E7EB; padding-top: 16px; }
.r-notes { margin: 0; padding-left: 20px; font-size: 14px; color: #57606A; }
.r-notes li { margin-bottom: 4px; }
.up { color: #C0392B !important; font-weight: 600; }
.down { color: #1E8449 !important; font-weight: 600; }
</style>

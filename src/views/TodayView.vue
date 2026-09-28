<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useDataStore } from '../stores/data'
import { conclude, type BucketPt } from '../rules/engine'
import MetricCard from '../components/MetricCard.vue'
import MiniLine from '../components/MiniLine.vue'

const store = useDataStore()

const daily = computed(() => store.daily)
const bucketPts = ref<BucketPt[]>([])
watch(
  () => store.currentDate,
  async (d) => {
    if (!d) return
    try {
      const f = await (await fetch('/data/series/mktcap_buckets.json')).json()
      bucketPts.value = f.points ?? []
    } catch {
      bucketPts.value = []
    }
  },
  { immediate: true }
)
const conclusion = computed(() => (daily.value ? conclude(daily.value, bucketPts.value) : null))
const sparks = computed(() => daily.value?.sparklines)

const N_YEAR = computed(() => store.yearSampleN())
const N_ALL = computed(() => store.allSampleN())

function fmt(n: number | null | undefined, digits = 0): string {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}

function toPts(arr: { date: string; value: number }[] | undefined) {
  return (arr ?? []).slice(-20).map((p) => ({ label: p.date.slice(4, 6) + '/' + p.date.slice(6, 8), value: p.value }))
}
function toPtsUD(arr: { date: string; up: number; down: number }[] | undefined) {
  return (arr ?? []).slice(-20).map((p) => ({ label: p.date.slice(4, 6) + '/' + p.date.slice(6, 8), value: p.up - p.down }))
}

const canDraw = computed(() => {
  const n = store.allSampleN()
  return !store.insufficient(n)
})

// ===== 自选股行情（store 统一管理，失败不影响主数据）=====
const quotesFile = computed(() => store.quotes)
const quotesError = computed(() => store.quotesError)
onMounted(() => store.loadQuotes())

function fmtPrice(n: number | null): string {
  return n == null ? '—' : n.toFixed(2)
}
function fmtChange(n: number | null): string {
  if (n == null) return '—'
  return (n > 0 ? '+' : '') + n.toFixed(2) + '%'
}
function changeClass(n: number | null): string {
  if (n == null) return 'muted'
  return n > 0 ? 'up' : n < 0 ? 'down' : ''
}
</script>

<template>
  <div class="page">
    <template v-if="daily">
      <h1 class="page-title">🏠 今日速览 · <span class="num">{{ store.formatDay(daily.trade_date) }}</span></h1>
      <p class="page-desc">两市核心资金指标 · 数据每日收盘后更新</p>

      <div class="card-grid cols-4">
        <MetricCard
          icon="💰" title="两市成交额" desc="沪深两市合计"
          :value="fmt(daily.overview.total_amount)" unit="亿"
          :sub="daily.overview.total_amount_rank_year
            ? `年内第 ${daily.overview.total_amount_rank_year} 名 · 历史 ${daily.overview.total_amount_pctile_all ?? '—'}%`
            : '排名待回补'"
          :sample-n="N_ALL"
        />
        <MetricCard
          icon="🏦" title="两融余额" desc="沪市+深市汇总"
          :value="daily.overview.margin_balance != null ? fmt(daily.overview.margin_balance) : '—'" unit="亿"
          :sub="daily.overview.margin_rank_year
            ? `年内第 ${daily.overview.margin_rank_year} 名 · 历史 ${daily.overview.margin_pctile_all ?? '—'}%`
            : '两融数据延迟约1日'"
          :sample-n="daily.overview.margin_balance != null ? N_YEAR : null"
        />
        <MetricCard
          icon="🔥" title="涨停 · 跌停" desc="剔除ST/北交所/次新"
          :value="`${daily.overview.limit_up} / ${daily.overview.limit_down}`"
          sub="红=涨停 绿=跌停"
          :sample-n="N_ALL"
        />
        <MetricCard
          icon="📐" title="10亿以上家数" desc="成交额≥10亿元个股"
          :value="fmt(daily.overview.over_10e_count)" unit="家"
          :sub="`占全部个股 ${fmt(daily.overview.over_10e_ratio, 1)}%（共 ${fmt(daily.overview.stock_count)} 家）`"
          :sample-n="N_ALL"
        />
      </div>

      <div v-if="conclusion" class="conclusion-box">
        <strong>自动结论</strong>（综合评分 <span class="num">{{ conclusion.score }}</span>/100）：
        {{ conclusion.fund.text }}；{{ conclusion.structure.text }}；{{ conclusion.emotion.text }}
        <div class="basis">{{ conclusion.fund.basis }}</div>
      </div>

      <!-- 自选股行情：数据 /data/quotes.json（scripts/update_data.py 每日更新） -->
      <div class="card">
        <div class="card-title">📈 自选股行情</div>
        <div class="card-desc">
          更新时间：<span class="num">{{ quotesFile?.date ?? '—' }}</span>
          · 清单维护：public/data/stocks.json
        </div>
        <div v-if="quotesFile && quotesFile.quotes.length" class="table-wrap" style="margin-top:8px">
          <table class="data">
            <thead>
              <tr><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th></tr>
            </thead>
            <tbody>
              <tr v-for="q in quotesFile.quotes" :key="q.code">
                <td class="num muted">{{ q.code }}</td>
                <td>{{ q.name }}</td>
                <td class="num">{{ fmtPrice(q.price) }}</td>
                <td class="num" :class="changeClass(q.change)">{{ fmtChange(q.change) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty-box" style="margin-top:8px">
          🟡 {{ quotesError || '自选股清单为空，请在 public/data/stocks.json 中维护关注标的' }}
        </div>
      </div>

      <div v-if="canDraw && sparks" class="card-grid cols-3" style="grid-template-columns: repeat(3, 1fr); margin-top: 6px;">
        <div class="card">
          <div class="card-title">📊 近20日成交额</div>
          <div class="card-desc">单位：亿元</div>
          <MiniLine :points="toPts(sparks.total_amount)" color="#B7410E" />
        </div>
        <div class="card">
          <div class="card-title">🏦 近20日两融余额</div>
          <div class="card-desc">单位：亿元</div>
          <MiniLine :points="toPts(sparks.margin)" color="#58A6FF" />
        </div>
        <div class="card">
          <div class="card-title">🔥 近20日涨跌停差</div>
          <div class="card-desc">涨停家数 − 跌停家数</div>
          <MiniLine :points="toPtsUD(sparks.limit_up_down)" color="#F59E0B" />
        </div>
      </div>
      <div v-else-if="sparks" class="empty-box">🟡 历史样本不足 30 个交易日，暂不绘制折线（样本N={{ N_ALL }}）</div>

      <p style="margin-top:14px" class="muted">
        📋 完整指标见 <router-link to="/report">复盘报告</router-link> ·
        🟢 数据状态见 <router-link to="/status">数据状态</router-link>
      </p>
    </template>
    <div v-else class="empty-box">
      🟡 该日期暂无数据（最后更新：{{ store.meta?.updated_at ?? '—' }}），已展示最近一个有效交易日
    </div>
  </div>
</template>

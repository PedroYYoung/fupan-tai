<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDataStore } from '../stores/data'
import type { SeriesPoint, StockRow } from '../types'
import ChartPanel from '../components/ChartPanel.vue'
import { miniLineOption } from '../lib/echarts'

const store = useDataStore()
const concSeries = ref<SeriesPoint[]>([])
const ready = ref(false)

watch(
  () => store.currentDate,
  async () => {
    if (!store.currentDate) return
    ready.value = false
    const s = await store.getSeries('top10_concentration')
    concSeries.value = s?.points ?? []
    ready.value = true
  },
  { immediate: true }
)

const daily = computed(() => store.daily)
const conc = computed(() => daily.value?.concentration)
const nAll = computed(() => store.allSampleN())

function fmt(n: number | null | undefined, digits = 2): string {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}

function rows(k: number): StockRow[] {
  return (k === 10 ? conc.value?.top10 : k === 20 ? conc.value?.top20 : conc.value?.top50) ?? []
}
function cum(list: StockRow[]): number[] {
  let s = 0
  return list.map((x) => (s = +(s + (x.pct_of_total ?? 0)).toFixed(2)))
}

const concOpt = computed(() =>
  miniLineOption(
    concSeries.value.slice(-120).map((p) => ({
      label: p.date.slice(4, 6) + '/' + p.date.slice(6, 8),
      value: p.value
    })),
    '#B7410E'
  )
)
</script>

<template>
  <div class="page">
    <h1 class="page-title">🎯 个股集中度 · <span class="num">{{ daily ? store.formatDay(daily.trade_date) : '—' }}</span></h1>
    <p class="page-desc">按成交额排序的头部个股结构 · 抱团度 = 前10成交占比在历史中的百分位</p>

    <template v-if="conc && daily">
      <div class="card-grid cols-3">
        <div class="card">
          <div class="card-title">🎯 前10合计占比</div>
          <div class="card-value num">{{ fmt(conc.top10.reduce((s, x) => s + (x.pct_of_total ?? 0), 0)) }}<span class="unit">%</span></div>
          <div class="card-sub num">
            {{ nAll >= 30 && conc.top10_total_pctile_hist != null ? `历史 ${conc.top10_total_pctile_hist}%` : '样本不足' }}
          </div>
          <span class="card-sample num">样本N={{ nAll }}</span>
        </div>
        <div class="card">
          <div class="card-title">🎯 前20合计占比</div>
          <div class="card-value num">{{ fmt(conc.top20_cum_pct) }}<span class="unit">%</span></div>
          <div class="card-sub num">较前10 +{{ fmt(conc.top20_cum_pct - conc.top10.reduce((s, x) => s + (x.pct_of_total ?? 0), 0)) }}pct</div>
        </div>
        <div class="card">
          <div class="card-title">🎯 前50合计占比</div>
          <div class="card-value num">{{ fmt(conc.top50_cum_pct) }}<span class="unit">%</span></div>
          <div class="card-sub num">较前20 +{{ fmt(conc.top50_cum_pct - conc.top20_cum_pct) }}pct</div>
        </div>
      </div>

      <div class="card-grid cols-3" style="margin-top:14px">
        <div v-for="k in ([10, 20, 50] as const)" :key="k" class="card">
          <div class="card-title">📋 前{{ k }}明细</div>
          <div class="table-wrap" style="margin-top:8px">
            <table class="data">
              <thead>
                <tr><th>代码</th><th>名称</th><th>成交额(亿)</th><th>占比</th><th>累计</th></tr>
              </thead>
              <tbody>
                <tr v-for="(s, i) in rows(k)" :key="s.code">
                  <td class="num">{{ s.code }}</td>
                  <td>{{ s.name }}</td>
                  <td class="num">{{ fmt(s.amount, 1) }}</td>
                  <td class="num">{{ fmt(s.pct_of_total) }}%</td>
                  <td class="num muted">{{ cum(rows(k))[i] }}%</td>
                </tr>
                <tr v-if="!rows(k).length"><td colspan="5" class="muted">无</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="card" style="margin-top:14px">
        <div class="card-title">🧲 头部抱团度（前10成交占比 %，近120个交易日）</div>
        <ChartPanel v-if="ready && nAll >= 30" :option="concOpt" height="240px" />
        <div v-else class="empty-box">🟡 样本不足（N={{ nAll }}），不绘制折线</div>
        <span v-if="nAll >= 30" class="card-sample num">样本N={{ nAll }}</span>
      </div>
    </template>
    <div v-else class="empty-box">
      🟡 该日期暂无数据（最后更新：{{ store.meta?.updated_at ?? '—' }}），已展示最近一个有效交易日
    </div>
  </div>
</template>

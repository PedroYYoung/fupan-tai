<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDataStore } from '../stores/data'
import { PERIODS, aggregate, pctileText, type Period } from '../lib/agg'
import type { SeriesPoint } from '../types'
import ChartPanel from '../components/ChartPanel.vue'
import { miniLineOption } from '../lib/echarts'

const store = useDataStore()
const period = ref<Period>('day')
const taSeries = ref<SeriesPoint[]>([])
const mgSeries = ref<SeriesPoint[]>([])
const ready = ref(false)

watch(
  () => [store.currentDate, period.value],
  async () => {
    if (!store.currentDate) return
    ready.value = false
    const [ta, mg] = await Promise.all([
      store.getSeries('total_amount'),
      store.getSeries('margin')
    ])
    taSeries.value = ta?.points ?? []
    mgSeries.value = mg?.points ?? []
    ready.value = true
  },
  { immediate: true }
)

const date = computed(() => store.currentDate)

const taAgg = computed(() => aggregate(taSeries.value, date.value, period.value))
const mgAgg = computed(() => aggregate(mgSeries.value, date.value, period.value))

function fmt(n: number | null | undefined, digits = 0): string {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}

function lineOpt(points: SeriesPoint[]) {
  const last = points.slice(-20)
  return miniLineOption(
    last.map((p) => ({ label: p.date.slice(4, 6) + '/' + p.date.slice(6, 8), value: p.value }))
  )
}

function subText(agg: { rank: number | null; rankYear: number | null; sampleN: number }, n: number): string {
  const parts: string[] = []
  if (period.value === 'day') {
    if (agg.rankYear != null) parts.push(`年内第 ${agg.rankYear} 名`)
    parts.push(pctileText(agg.rank, n))
  } else if (agg.rank != null) {
    parts.push(`历史第 ${agg.rank} 名（同口径均值）`)
    parts.push(pctileText(agg.rank, agg.sampleN))
  } else {
    parts.push('均值口径无排名')
  }
  return parts.join(' · ')
}
</script>

<template>
  <div class="page">
    <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;">
      <div>
        <h1 class="page-title">💰 资金面 · <span class="num">{{ store.formatDay(date) }}</span></h1>
        <p class="page-desc">两市成交 / 两融余额 · 排名与百分位（{{ taAgg.note }}）</p>
      </div>
      <div style="display:flex; gap:6px;">
        <button
          v-for="p in PERIODS" :key="p.key"
          class="btn" :class="period === p.key ? '' : 'secondary'"
          @click="period = p.key"
        >{{ p.label }}</button>
      </div>
    </div>

    <div v-if="ready" class="card-grid cols-2">
      <div class="card">
        <div class="card-title">📊 两市成交额</div>
        <div class="card-desc">
          {{ period === 'day' ? '当日合计（亿元）' : period === 'month' ? '本月交易日均值' : period === 'year' ? '本年交易日均值' : '全历史均值' }}
        </div>
        <div class="card-value num">{{ fmt(taAgg.value) }}<span class="unit">亿</span></div>
        <div class="card-sub num">{{ subText(taAgg, taAgg.sampleN) }}</div>
        <span v-if="taAgg.sampleN >= 30" class="card-sample num">样本N={{ taAgg.sampleN }}</span>
        <span v-else class="card-insufficient">样本不足</span>
        <div style="margin-top:8px"><ChartPanel :option="lineOpt(taSeries)" height="150px" /></div>
      </div>

      <div class="card">
        <div class="card-title">🏦 两融余额</div>
        <div class="card-desc">沪市+深市汇总（亿元）· 数据延迟约1日</div>
        <div class="card-value num">{{ fmt(mgAgg.value) }}<span class="unit">亿</span></div>
        <div class="card-sub num">{{ subText(mgAgg, mgAgg.sampleN) }}</div>
        <span v-if="mgAgg.sampleN >= 30" class="card-sample num">样本N={{ mgAgg.sampleN }}</span>
        <span v-else-if="mgAgg.sampleN > 0" class="card-insufficient">样本不足</span>
        <div style="margin-top:8px"><ChartPanel :option="lineOpt(mgSeries)" height="150px" color="#58A6FF" /></div>
      </div>
    </div>
    <div v-else class="loading-box">加载序列数据…</div>

    <p class="muted" style="margin-top:14px; font-size:12px">
      切换档位只改变聚合口径（均值合成），指标定义与样本窗口不变。
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useDataStore } from '../stores/data'
import { GRANULARITIES, aggregateLast, type Granularity } from '../lib/period'
import type { SeriesPoint } from '../types'
import ChartPanel from '../components/ChartPanel.vue'
import type { EChartsOption } from 'echarts'
import { MUTED, TEXT, BORDER } from '../lib/echarts'

const store = useDataStore()
const router = useRouter()
const gran = ref<Granularity>('day')
const sseSeries = ref<SeriesPoint[]>([])
const szseSeries = ref<SeriesPoint[]>([])
const totalSeries = ref<SeriesPoint[]>([])

watch(
  () => store.currentDate,
  async () => {
    const [sse, szse, total] = await Promise.all([
      store.getSeries('margin_sse'),
      store.getSeries('margin_szse'),
      store.getSeries('margin')
    ])
    sseSeries.value = sse?.points ?? []
    szseSeries.value = szse?.points ?? []
    totalSeries.value = total?.points ?? []
  },
  { immediate: true }
)

function toVals(pts: SeriesPoint[]): { date: string; value: number }[] {
  return pts.filter((p) => p.value != null).map((p) => ({ date: p.date, value: p.value }))
}

const sseVals = computed(() => toVals(sseSeries.value))
const szseVals = computed(() => toVals(szseSeries.value))
const totalVals = computed(() => toVals(totalSeries.value))

function byGran(points: { date: string; value: number }[]): { date: string; value: number; label: string }[] {
  if (gran.value === 'day') {
    return points.map((p) => ({ ...p, label: p.date.slice(0, 4) + '-' + p.date.slice(4, 6) + '-' + p.date.slice(6, 8) }))
  }
  return aggregateLast(points, gran.value)
}

const sseAgg = computed(() => byGran(sseVals.value))
const szseAgg = computed(() => byGran(szseVals.value))
const totalAgg = computed(() => byGran(totalVals.value))

// 以合计的日期轴为主轴（分项可能缺失）
function align(series: { date: string; value: number }[], refDates: string[]): (number | null)[] {
  const m = new Map(series.map((p) => [p.date, p.value]))
  return refDates.map((d) => m.get(d) ?? null)
}

const chartOpt = computed<EChartsOption>(() => {
  const dates = totalAgg.value.map((p) => p.date)
  const labels = totalAgg.value.map((p) => p.label)
  return {
    animation: false,
    grid: { left: 8, right: 8, top: 40, bottom: 4, containLabel: true },
    legend: { top: 4, textStyle: { color: MUTED, fontSize: 11 } },
    tooltip: {
      trigger: 'axis', confine: true,
      backgroundColor: '#131820', borderColor: BORDER, textStyle: { color: TEXT, fontSize: 12 },
      formatter: (params: unknown) => {
        const arr = params as { axisValue: string; seriesName: string; value: number | null }[]
        const idx = totalAgg.value.findIndex((p) => p.label === arr[0]?.axisValue)
        const d = dates[idx] ?? ''
        const lines = [`<b>${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}</b>`]
        for (const s of arr) lines.push(`${s.seriesName}：${s.value == null ? '—' : s.value.toLocaleString('zh-CN')} 亿`)
        return lines.join('<br/>')
      }
    },
    xAxis: {
      type: 'category', data: labels,
      axisLine: { lineStyle: { color: BORDER } }, axisTick: { show: false },
      axisLabel: { color: MUTED, fontSize: 10, interval: Math.max(Math.floor(labels.length / 10), 0) }
    },
    yAxis: {
      type: 'value', scale: true,
      splitLine: { lineStyle: { color: BORDER, type: 'dashed' } },
      axisLabel: { color: MUTED, fontSize: 10 }
    },
    series: [
      { name: '沪深合计', type: 'line', data: totalAgg.value.map((p) => p.value), smooth: true, symbol: 'none', lineStyle: { color: '#E6EDF3', width: 2.5 }, itemStyle: { color: '#E6EDF3' } },
      { name: '沪市', type: 'line', data: align(sseAgg.value, dates), smooth: true, symbol: 'none', connectNulls: false, lineStyle: { color: '#B7410E', width: 1.6 }, itemStyle: { color: '#B7410E' } },
      { name: '深市', type: 'line', data: align(szseAgg.value, dates), smooth: true, symbol: 'none', connectNulls: false, lineStyle: { color: '#58A6FF', width: 1.6 }, itemStyle: { color: '#58A6FF' } }
    ]
  }
})

function fmt(n: number | null | undefined, digits = 0): string {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}
function signed(n: number | null | undefined): string {
  if (n == null) return '—'
  return n > 0 ? `+${n.toFixed(0)}` : `${n.toFixed(0)}`
}

// 三序列各自的最新值 + 相对上一周期变化
const latestRow = computed(() => {
  const last = (agg: { value: number }[]) => (agg.length ? agg[agg.length - 1].value : null)
  const prev = (agg: { value: number }[]) => (agg.length >= 2 ? agg[agg.length - 2].value : null)
  const d = (agg: { value: number }[]) => (last(agg) != null && prev(agg) != null ? last(agg)! - prev(agg)! : null)
  return [
    { name: '沪市', val: last(sseAgg.value), delta: d(sseAgg.value) },
    { name: '深市', val: last(szseAgg.value), delta: d(szseAgg.value) },
    { name: '沪深合计', val: last(totalAgg.value), delta: d(totalAgg.value) }
  ]
})

const granNote = computed(() =>
  gran.value === 'day' ? '日度走势（时点余额）' : gran.value === 'week' ? '按自然周取该周最后一个有效交易日余额' : '按自然月取该月最后一个有效交易日余额'
)

function back() {
  router.push('/money')
}
</script>

<template>
  <div class="page">
    <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;">
      <div>
        <h1 class="page-title">🏦 两融余额走势 · <span class="num">{{ store.formatDay(store.currentDate) }}</span></h1>
        <p class="page-desc">沪深两融余额（时点余额，亿元）· {{ granNote }} · 历史自 2010-03-31</p>
      </div>
      <div style="display:flex; gap:6px;">
        <button
          v-for="g in GRANULARITIES" :key="g.key"
          class="btn" :class="gran === g.key ? '' : 'secondary'"
          @click="gran = g.key"
        >{{ g.label }}</button>
        <button class="btn secondary" @click="back">← 返回</button>
      </div>
    </div>

    <div class="card-grid cols-3" style="margin-top:14px">
      <div v-for="r in latestRow" :key="r.name" class="card">
        <div class="card-title">{{ r.name }}</div>
        <div class="card-value num">{{ fmt(r.val) }}<span class="unit">亿</span></div>
        <div class="card-sub num">较上{{ gran === 'day' ? '一交易日' : gran === 'week' ? '一周' : '一月' }} <span :class="r.delta == null ? 'muted' : r.delta > 0 ? 'up' : 'down'">{{ signed(r.delta) }}</span> 亿</div>
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <div class="card-title">📈 沪深两融余额走势（{{ GRANULARITIES.find((g) => g.key === gran)?.label }}）</div>
      <ChartPanel v-if="totalAgg.length" :option="chartOpt" height="420px" />
      <div v-else class="empty-box">🟡 暂无两融数据</div>
    </div>

    <p class="muted" style="margin-top:14px; font-size:12px">
      说明：两融余额为时点余额，周/月取该周期最后一个有效交易日的余额，不做累加；沪市/深市分项缺失的日期如实断线，不补 0、不虚构。
    </p>
  </div>
</template>

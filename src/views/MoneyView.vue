<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useDataStore } from '../stores/data'
import { RANGES, inRange, type Range } from '../lib/period'
import type { SeriesPoint } from '../types'
import ChartPanel from '../components/ChartPanel.vue'
import { miniLineOption, MUTED, TEXT, BORDER } from '../lib/echarts'
import type { EChartsOption } from 'echarts'

const store = useDataStore()
const router = useRouter()
const range = ref<Range>('week')
const taSeries = ref<SeriesPoint[]>([])
const mgSeries = ref<SeriesPoint[]>([])
const ready = ref(false)

watch(
  () => store.currentDate,
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
const rangeLabel = computed(() => RANGES.find((r) => r.key === range.value)?.label ?? '本周')

// 两市成交额：按所选自然周期筛选真实交易日，不补 0
const taFiltered = computed(() =>
  taSeries.value.filter((p) => p.value != null && inRange(p.date, date.value, range.value))
)

function fmt(n: number | null | undefined, digits = 0): string {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}

const taLineOpt = computed<EChartsOption>(() => {
  const pts = taFiltered.value
  const labels = pts.map((p) => p.date.slice(4, 6) + '/' + p.date.slice(6, 8))
  return {
    animation: false,
    grid: { left: 8, right: 8, top: 12, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis', confine: true,
      backgroundColor: '#131820', borderColor: BORDER, textStyle: { color: TEXT, fontSize: 12 },
      formatter: (params: unknown) => {
        const arr = params as { dataIndex: number }[]
        const p = pts[arr[0]?.dataIndex ?? 0]
        return p ? `${p.date.slice(0, 4)}-${p.date.slice(4, 6)}-${p.date.slice(6, 8)}<br/>两市成交额：${p.value.toLocaleString('zh-CN')} 亿` : ''
      }
    },
    xAxis: {
      type: 'category', data: labels,
      axisLine: { lineStyle: { color: BORDER } }, axisTick: { show: false },
      axisLabel: { color: MUTED, fontSize: 10, interval: Math.max(Math.floor(labels.length / 8), 0) }
    },
    yAxis: {
      type: 'value', scale: true,
      splitLine: { lineStyle: { color: BORDER, type: 'dashed' } },
      axisLabel: { color: MUTED, fontSize: 10 }
    },
    series: [{
      type: 'line', smooth: true, symbol: 'none',
      data: pts.map((p) => p.value),
      lineStyle: { color: '#B7410E', width: 2 }, itemStyle: { color: '#B7410E' },
      areaStyle: { color: '#B7410E22' }
    }]
  }
})

// 两融余额卡片：最近一条有效余额 + 统计日期
const mgLatest = computed(() => {
  const pts = mgSeries.value.filter((p) => p.value != null)
  return pts.length ? pts[pts.length - 1] : null
})
const mgSpark = computed<EChartsOption>(() =>
  miniLineOption(
    mgSeries.value.slice(-120).filter((p) => p.value != null).map((p) => ({
      label: p.date.slice(4, 6) + '/' + p.date.slice(6, 8),
      value: p.value
    })),
    '#58A6FF'
  )
)

function openMargin() {
  router.push('/margin')
}
</script>

<template>
  <div class="page">
    <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;">
      <div>
        <h1 class="page-title">💰 资金面 · <span class="num">{{ store.formatDay(date) }}</span></h1>
        <p class="page-desc">两市成交 / 两融余额 · 点击两融卡片查看日、周、月完整走势</p>
      </div>
    </div>

    <div v-if="ready" class="card-grid cols-2">
      <div class="card">
        <div class="card-title">📊 {{ rangeLabel }}两市成交额</div>
        <div style="display:flex; gap:6px; margin-top:4px;">
          <button
            v-for="p in RANGES" :key="p.key"
            class="btn" :class="range === p.key ? '' : 'secondary'"
            @click="range = p.key"
          >{{ p.label }}</button>
        </div>
        <div class="card-desc" style="margin-top:8px">
          {{ rangeLabel }}内 {{ taFiltered.length }} 个有效交易日
        </div>
        <div class="card-value num">{{ fmt(taFiltered[taFiltered.length - 1]?.value ?? store.daily?.overview.total_amount) }}<span class="unit">亿</span></div>
        <div class="card-sub num">最近交易日合计（亿元）</div>
        <div style="margin-top:8px"><ChartPanel :option="taLineOpt" height="170px" /></div>
      </div>

      <div class="card clickable" @click="openMargin" title="查看两融日/周/月完整走势">
        <div class="card-title">🏦 两融余额<span class="muted" style="font-size:12px; margin-left:6px">点击查看详情 →</span></div>
        <div class="card-desc">沪市+深市汇总（亿元）<template v-if="store.daily?.overview.margin_date"> · 统计日期 {{ store.formatDay(store.daily.overview.margin_date) }}</template></div>
        <div class="card-value num">{{ fmt(mgLatest?.value) }}<span class="unit">亿</span></div>
        <div class="card-sub num">历史样本 N={{ mgSeries.filter((p) => p.value != null).length }}（自 2010-03-31）</div>
        <div style="margin-top:8px"><ChartPanel :option="mgSpark" height="170px" /></div>
      </div>
    </div>
    <div v-else class="loading-box">加载序列数据…</div>
  </div>
</template>

<style scoped>
.clickable {
  cursor: pointer;
  transition: border-color 0.15s ease;
}
.clickable:hover {
  border-color: #58A6FF;
}
</style>

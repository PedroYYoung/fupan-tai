<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDataStore } from '../stores/data'
import type { BucketSeriesFile, SeriesPoint } from '../types'
import ChartPanel from '../components/ChartPanel.vue'
import type { EChartsOption } from 'echarts'
import { MUTED, TEXT, BORDER } from '../lib/echarts'

const store = useDataStore()
const o10Series = ref<SeriesPoint[]>([])
const bucketSeries = ref<BucketSeriesFile['points']>([])
const ready = ref(false)

watch(
  () => store.currentDate,
  async () => {
    if (!store.currentDate) return
    ready.value = false
    const [o10, buckets] = await Promise.all([
      store.getSeries('over_10e_count'),
      (async () => {
        try {
          return await (await fetch('/data/series/mktcap_buckets.json')).json() as BucketSeriesFile
        } catch {
          return null
        }
      })()
    ])
    o10Series.value = o10?.points ?? []
    bucketSeries.value = buckets?.points ?? []
    ready.value = true
  },
  { immediate: true }
)

const daily = computed(() => store.daily)
const liq = computed(() => daily.value?.liquidity)
const nAll = computed(() => store.allSampleN())

function fmt(n: number | null | undefined, digits = 1): string {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}

const o10Opt = computed<EChartsOption>(() => ({
  animation: false,
  grid: { left: 8, right: 8, top: 12, bottom: 4, containLabel: true },
  tooltip: { trigger: 'axis', confine: true, backgroundColor: '#131820', borderColor: BORDER, textStyle: { color: TEXT, fontSize: 12 } },
  xAxis: {
    type: 'category',
    data: o10Series.value.slice(-60).map((p) => p.date.slice(4, 6) + '/' + p.date.slice(6, 8)),
    axisLine: { lineStyle: { color: BORDER } }, axisTick: { show: false },
    axisLabel: { color: MUTED, fontSize: 10 }
  },
  yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: BORDER, type: 'dashed' } }, axisLabel: { color: MUTED, fontSize: 10 } },
  series: [{
    type: 'line', smooth: true, symbol: 'none',
    data: o10Series.value.slice(-60).map((p) => p.value),
    lineStyle: { color: '#58A6FF', width: 2 }, itemStyle: { color: '#58A6FF' },
    areaStyle: { color: '#58A6FF22' }
  }]
}))

// 市值 6 档堆叠面积图（hover 显示家数 + 占比）
const BUCKET_COLORS = ['#1E3A5F', '#2C5282', '#B7410E', '#D97B29', '#F59E0B', '#FF4D4F']
const stackOpt = computed<EChartsOption | null>(() => {
  if (!bucketSeries.value.length) return null
  const pts = bucketSeries.value.slice(-60)
  const labels = pts.map((p) => p.date.slice(4, 6) + '/' + p.date.slice(6, 8))
  const labelsFull = pts.map((p) => p.date)
  const labelSet = pts[0]?.buckets.map((b) => b.label) ?? []
  return {
    animation: false,
    grid: { left: 8, right: 8, top: 30, bottom: 4, containLabel: true },
    legend: { top: 2, textStyle: { color: MUTED, fontSize: 11 }, data: labelSet },
    tooltip: {
      trigger: 'axis', confine: true,
      backgroundColor: '#131820', borderColor: BORDER, textStyle: { color: TEXT, fontSize: 12 },
      formatter: (params: unknown) => {
        const arr = params as { axisValue: string; seriesName: string; value: number; dataIndex: number }[]
        const idx = arr[0]?.dataIndex ?? 0
        const buckets = pts[idx]?.buckets ?? []
        const date = labelsFull[idx] ?? ''
        const lines = [`<b>${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)}</b>`]
        for (const b of [...buckets].reverse()) {
          lines.push(`${b.label}：${b.count} 家（${b.pct}%）`)
        }
        return lines.join('<br/>')
      }
    },
    xAxis: {
      type: 'category', data: labels,
      axisLine: { lineStyle: { color: BORDER } }, axisTick: { show: false },
      axisLabel: { color: MUTED, fontSize: 10 }
    },
    yAxis: { type: 'value', max: 100, axisLabel: { color: MUTED, fontSize: 10, formatter: '{value}%' }, splitLine: { lineStyle: { color: BORDER, type: 'dashed' } } },
    series: labelSet.map((label, i) => ({
      name: label, type: 'line' as const, stack: 'total', areaStyle: { opacity: 0.85 },
      lineStyle: { width: 0 }, symbol: 'none', emphasis: { focus: 'series' as const },
      itemStyle: { color: BUCKET_COLORS[i % BUCKET_COLORS.length] },
      data: pts.map((p) => p.buckets.find((b) => b.label === label)?.pct ?? 0)
    }))
  }
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">📐 流动性结构 · <span class="num">{{ daily ? store.formatDay(daily.trade_date) : '—' }}</span></h1>
    <p class="page-desc">10亿以上活跃家数 + 市值 6 档结构（堆叠面积，占比%）</p>

    <template v-if="liq && daily">
      <div class="card-grid cols-4">
        <div class="card">
          <div class="card-title">📐 10亿以上家数</div>
          <div class="card-value num">{{ daily.overview.over_10e_count }}<span class="unit">家</span></div>
          <div class="card-sub num">
            {{ nAll >= 30 && liq.pctile_count != null ? `历史 ${liq.pctile_count}%` : '样本不足' }}
          </div>
          <span class="card-sample num">样本N={{ nAll }}</span>
        </div>
        <div class="card">
          <div class="card-title">🥧 占全部个股</div>
          <div class="card-value num">{{ fmt(liq.over_10e_ratio) }}<span class="unit">%</span></div>
          <div class="card-sub num">共 {{ daily.overview.stock_count }} 只</div>
        </div>
      </div>

      <div class="card" style="margin-top:14px">
        <div class="card-title">📈 10亿以上家数（近60个交易日）</div>
        <ChartPanel v-if="ready && nAll >= 30" :option="o10Opt" height="220px" />
        <div v-else class="empty-box">🟡 样本不足（N={{ nAll }}），不绘制折线</div>
      </div>

      <div class="card" style="margin-top:14px">
        <div class="card-title">🧱 市值 6 档堆叠面积（占比%，hover 看家数）</div>
        <ChartPanel v-if="stackOpt" :option="stackOpt" height="280px" />
        <div v-else class="empty-box">🟡 市值分档序列尚未累积（自启用日起每日累积，无法历史回补）</div>
      </div>

      <div class="table-wrap" style="margin-top:10px">
        <table class="data">
          <thead>
            <tr><th>档位</th><th>家数</th><th>占比</th></tr>
          </thead>
          <tbody>
            <tr v-for="b in liq.mktcap_buckets" :key="b.label">
              <td>{{ b.label }}</td><td class="num">{{ b.count }}</td><td class="num">{{ b.pct }}%</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
    <div v-else class="empty-box">
      🟡 该日期暂无数据（最后更新：{{ store.meta?.updated_at ?? '—' }}），已展示最近一个有效交易日
    </div>
  </div>
</template>

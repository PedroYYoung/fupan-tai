<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDataStore } from '../stores/data'
import type { Bucket, BucketSeriesFile, SeriesPoint, ValueBucket } from '../types'
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

// 统一市值档位颜色
const MKTCAP_COLORS: Record<string, string> = {
  '1000亿以上': '#8B0000',
  '500-1000亿': '#E67E22',
  '200-500亿': '#F1C40F',
  '100-200亿': '#27AE60',
  '50-100亿': '#3498DB',
  '50亿以下': '#7F8C8D'
}

const amountBuckets = computed(() => liq.value?.amount_buckets ?? [])
const mcapCountBuckets = computed(() => liq.value?.over_10e_marketcap_buckets ?? [])
const mcapValueBuckets = computed(() => liq.value?.over_10e_marketcap_value_buckets ?? [])

const activeStockCount = computed(() => mcapCountBuckets.value.reduce((s, b) => s + b.count, 0))
const activeTotalValue = computed(() => mcapValueBuckets.value.reduce((s, b) => s + b.total_value, 0))

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

// 成交额≥10亿 市值数量 横向条形图（按数量降序）
const mcapCountBarOpt = computed<EChartsOption | null>(() => {
  const data = [...mcapCountBuckets.value].filter((b) => b.count > 0).sort((a, b) => b.count - a.count)
  if (!data.length) return null
  return {
    animation: false,
    grid: { left: 8, right: 80, top: 12, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis', confine: true,
      backgroundColor: '#131820', borderColor: BORDER, textStyle: { color: TEXT, fontSize: 12 },
      formatter: (params: unknown) => {
        const arr = params as { name: string; value: number; dataIndex: number }[]
        const b = data[arr[0]?.dataIndex ?? 0]
        if (!b) return ''
        return `<b>${b.label}</b><br/>股票数：${b.count} 只<br/>占活跃：${b.pct}%`
      }
    },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: BORDER, type: 'dashed' } }, axisLabel: { color: MUTED, fontSize: 10 } },
    yAxis: {
      type: 'category', data: data.map((b) => b.label),
      axisLine: { lineStyle: { color: BORDER } }, axisTick: { show: false },
      axisLabel: { color: TEXT, fontSize: 11 }
    },
    series: [{
      type: 'bar', data: data.map((b) => ({
        value: b.count,
        itemStyle: { color: MKTCAP_COLORS[b.label] || MUTED, borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: 'right', color: TEXT, fontSize: 10, formatter: `${b.count}只 (${b.pct}%)` }
      })),
      barMaxWidth: 20
    }]
  }
})

function pieOpt(data: { name: string; value: number }[], centerTitle: string, centerSub: string): EChartsOption | null {
  if (!data.length) return null
  return {
    animation: false,
    tooltip: {
      trigger: 'item', confine: true,
      backgroundColor: '#131820', borderColor: BORDER, textStyle: { color: TEXT, fontSize: 12 },
      formatter: '{b}<br/>{c} ({d}%)'
    },
    title: {
      text: centerTitle, subtext: centerSub, left: 'center', top: 'center',
      textStyle: { color: TEXT, fontSize: 18, fontWeight: 'bold' },
      subtextStyle: { color: MUTED, fontSize: 11 }
    },
    series: [{
      type: 'pie', radius: ['45%', '70%'], center: ['50%', '50%'],
      label: { color: TEXT, fontSize: 11, formatter: '{b}\n{d}%' },
      labelLine: { lineStyle: { color: BORDER } },
      data: data.map((d) => ({ ...d, itemStyle: { color: MKTCAP_COLORS[d.name] || MUTED } }))
    }]
  }
}

const mcapCountPieOpt = computed<EChartsOption | null>(() => {
  const data = mcapCountBuckets.value.filter((b) => b.count > 0).map((b) => ({ name: b.label, value: b.count }))
  return pieOpt(data, String(activeStockCount.value), '活跃股票')
})

const mcapValuePieOpt = computed<EChartsOption | null>(() => {
  const data = mcapValueBuckets.value.filter((b) => b.total_value > 0).map((b) => ({ name: b.label, value: b.total_value }))
  const t = activeTotalValue.value / 1e4
  return pieOpt(data, `${t.toFixed(2)}`, '活跃股票总市值（万亿）')
})

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
    <p class="page-desc">10亿以上活跃家数 + 成交额结构 + 活跃股市值结构 + 市值 6 档结构</p>

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
        <div class="card-title">📊 全市场成交额结构</div>
        <div class="table-wrap" style="margin-top:8px">
          <table class="data">
            <thead><tr><th>成交额区间</th><th>股票数量</th><th>占全市场比例</th></tr></thead>
            <tbody>
              <tr v-for="b in amountBuckets" :key="b.label">
                <td>{{ b.label }}</td><td class="num">{{ b.count }}</td><td class="num">{{ b.pct }}%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card" style="margin-top:14px">
        <div class="card-title">🏢 成交额≥10亿股票市值分布（{{ activeStockCount }} 只）</div>
        <div class="card-grid cols-2" style="margin-top:8px">
          <div>
            <ChartPanel v-if="mcapCountBarOpt" :option="mcapCountBarOpt" height="260px" />
            <div v-else class="empty-box">🟡 无数据</div>
          </div>
          <div>
            <ChartPanel v-if="mcapCountPieOpt" :option="mcapCountPieOpt" height="260px" />
            <div v-else class="empty-box">🟡 无数据</div>
          </div>
        </div>
        <div class="table-wrap" style="margin-top:8px">
          <table class="data">
            <thead><tr><th>市值区间</th><th>股票数量</th><th>占活跃股票比例</th></tr></thead>
            <tbody>
              <tr v-for="b in mcapCountBuckets" :key="b.label">
                <td><span class="dot" :style="{ background: MKTCAP_COLORS[b.label] }"></span>{{ b.label }}</td>
                <td class="num">{{ b.count }}</td><td class="num">{{ b.pct }}%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card" style="margin-top:14px">
        <div class="card-title">💰 成交额≥10亿股票市值贡献结构（合计 {{ (activeTotalValue / 1e4).toFixed(2) }} 万亿）</div>
        <ChartPanel v-if="mcapValuePieOpt" :option="mcapValuePieOpt" height="280px" />
        <div v-else class="empty-box">🟡 无数据</div>
        <div class="table-wrap" style="margin-top:8px">
          <table class="data">
            <thead><tr><th>市值区间</th><th>股票数量</th><th>合计市值（亿）</th><th>占活跃股票总市值</th></tr></thead>
            <tbody>
              <tr v-for="b in mcapValueBuckets" :key="b.label">
                <td><span class="dot" :style="{ background: MKTCAP_COLORS[b.label] }"></span>{{ b.label }}</td>
                <td class="num">{{ b.count }}</td>
                <td class="num">{{ fmt(b.total_value, 0) }}</td>
                <td class="num">{{ b.pct }}%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card" style="margin-top:14px">
        <div class="card-title">🧱 市值 6 档堆叠面积（占比%，hover 看家数）</div>
        <ChartPanel v-if="stackOpt" :option="stackOpt" height="280px" />
        <div v-else class="empty-box">🟡 市值分档序列尚未累积（自启用日起每日累积，无法历史回补）</div>
      </div>

      <div class="table-wrap" style="margin-top:10px">
        <table class="data">
          <thead><tr><th>档位</th><th>家数</th><th>占比</th></tr></thead>
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

<style scoped>
.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 8px;
}
</style>

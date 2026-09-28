<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDataStore } from '../stores/data'
import type { SeriesPoint } from '../types'
import ChartPanel from '../components/ChartPanel.vue'
import type { EChartsOption } from 'echarts'
import { UP, DOWN, MUTED, TEXT, BORDER } from '../lib/echarts'

const store = useDataStore()
const luSeries = ref<SeriesPoint[]>([])
const ldSeries = ref<SeriesPoint[]>([])
const ready = ref(false)

watch(
  () => store.currentDate,
  async () => {
    if (!store.currentDate) return
    ready.value = false
    const [lu, ld] = await Promise.all([
      store.getSeries('limit_up_down'),
      store.getSeries('limit_down')
    ])
    luSeries.value = lu?.points ?? []
    ldSeries.value = ld?.points ?? []
    ready.value = true
  },
  { immediate: true }
)

const daily = computed(() => store.daily)
const emotion = computed(() => daily.value?.emotion)

const dualOpt = computed<EChartsOption | null>(() => {
  if (!luSeries.value.length) return null
  const n = 60
  const lu = luSeries.value.slice(-n)
  const ldMap = new Map(ldSeries.value.map((p) => [p.date, p.value]))
  const labels = lu.map((p) => p.date.slice(4, 6) + '/' + p.date.slice(6, 8))
  return {
    animation: false,
    grid: { left: 8, right: 8, top: 34, bottom: 4, containLabel: true },
    legend: { top: 4, textStyle: { color: MUTED, fontSize: 12 }, data: ['涨停', '跌停'] },
    tooltip: {
      trigger: 'axis', confine: true,
      backgroundColor: '#131820', borderColor: BORDER, textStyle: { color: TEXT, fontSize: 12 }
    },
    xAxis: {
      type: 'category', data: labels,
      axisLine: { lineStyle: { color: BORDER } }, axisTick: { show: false },
      axisLabel: { color: MUTED, fontSize: 10 }
    },
    yAxis: {
      type: 'value', scale: true,
      splitLine: { lineStyle: { color: BORDER, type: 'dashed' } },
      axisLabel: { color: MUTED, fontSize: 10 }
    },
    series: [
      { name: '涨停', type: 'line', smooth: true, symbol: 'none', data: lu.map((p) => p.value),
        lineStyle: { color: UP, width: 2 }, itemStyle: { color: UP } },
      { name: '跌停', type: 'line', smooth: true, symbol: 'none', data: lu.map((p) => ldMap.get(p.date) ?? 0),
        lineStyle: { color: DOWN, width: 2 }, itemStyle: { color: DOWN } }
    ]
  }
})

function fmt(n: number | null | undefined, digits = 1): string {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}

const nAll = computed(() => store.allSampleN())
</script>

<template>
  <div class="page">
    <h1 class="page-title">🔥 情绪 · <span class="num">{{ daily ? store.formatDay(daily.trade_date) : '—' }}</span></h1>
    <p class="page-desc">涨停/跌停家数 + 占比结构 + 10亿以上活跃票明细（剔除 ST/北交所/上市不足250日）</p>

    <template v-if="emotion && daily">
      <div class="card-grid cols-4">
        <div class="card">
          <div class="card-title">🔥 涨停</div>
          <div class="card-value num up">{{ emotion.limit_up }}<span class="unit">家</span></div>
          <div class="card-sub num">{{ nAll >= 30 && emotion.lu_pctile != null ? `历史 ${emotion.lu_pctile}%` : '样本不足' }}</div>
          <span class="card-sample num">样本N={{ nAll }}</span>
        </div>
        <div class="card">
          <div class="card-title">🧊 跌停</div>
          <div class="card-value num down">{{ emotion.limit_down }}<span class="unit">家</span></div>
          <div class="card-sub num">{{ nAll >= 30 && emotion.ld_pctile != null ? `历史 ${emotion.ld_pctile}%` : '样本不足' }}</div>
          <span class="card-sample num">样本N={{ nAll }}</span>
        </div>
        <div class="card">
          <div class="card-title">📐 占总股本数%</div>
          <div class="card-value num">{{ fmt(emotion.lu_ratio_of_total, 2) }} / {{ fmt(emotion.ld_ratio_of_total, 2) }}<span class="unit">%</span></div>
          <div class="card-sub">涨停 / 跌停 占全部 {{ daily.overview.stock_count }} 只个股</div>
        </div>
        <div class="card">
          <div class="card-title">🎯 占10亿以上%</div>
          <div class="card-value num">{{ fmt(emotion.lu_ratio_of_over10e) }} / {{ fmt(emotion.ld_ratio_of_over10e) }}<span class="unit">%</span></div>
          <div class="card-sub">10亿以上共 {{ daily.overview.over_10e_count }} 家</div>
        </div>
      </div>

      <div class="card" style="margin-top:14px">
        <div class="card-title">📈 涨停 / 跌停双折线（近60个交易日）</div>
        <ChartPanel v-if="dualOpt && nAll >= 30" :option="dualOpt" height="280px" />
        <div v-else class="empty-box">🟡 样本不足（N={{ nAll }}），不绘制折线</div>
      </div>

      <div class="card-grid cols-2" style="margin-top:14px">
        <div class="card">
          <div class="card-title">🔥 10亿以上 · 涨停票（{{ emotion.lu_over10e.length }}）</div>
          <div class="table-wrap" style="margin-top:8px">
            <table class="data">
              <thead><tr><th>代码</th><th>名称</th><th>成交额(亿)</th><th>涨跌幅</th><th>板块</th></tr></thead>
              <tbody>
                <tr v-for="s in emotion.lu_over10e" :key="s.code">
                  <td class="num">{{ s.code }}</td><td>{{ s.name }}</td>
                  <td class="num">{{ fmt(s.amount, 2) }}</td>
                  <td class="num up">+{{ fmt(s.change ?? 0, 2) }}%</td>
                  <td class="muted">{{ s.board }}</td>
                </tr>
                <tr v-if="!emotion.lu_over10e.length"><td colspan="5" class="muted">无</td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="card">
          <div class="card-title">🧊 10亿以上 · 跌停票（{{ emotion.ld_over10e.length }}）</div>
          <div class="table-wrap" style="margin-top:8px">
            <table class="data">
              <thead><tr><th>代码</th><th>名称</th><th>成交额(亿)</th><th>涨跌幅</th><th>板块</th></tr></thead>
              <tbody>
                <tr v-for="s in emotion.ld_over10e" :key="s.code">
                  <td class="num">{{ s.code }}</td><td>{{ s.name }}</td>
                  <td class="num">{{ fmt(s.amount, 2) }}</td>
                  <td class="num down">{{ fmt(s.change ?? 0, 2) }}%</td>
                  <td class="muted">{{ s.board }}</td>
                </tr>
                <tr v-if="!emotion.ld_over10e.length"><td colspan="5" class="muted">无</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </template>
    <div v-else class="empty-box">
      🟡 该日期暂无数据（最后更新：{{ store.meta?.updated_at ?? '—' }}），已展示最近一个有效交易日
    </div>
  </div>
</template>

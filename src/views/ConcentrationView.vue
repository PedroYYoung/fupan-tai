<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDataStore } from '../stores/data'
import type { SeriesPoint, StockRow } from '../types'
import ChartPanel from '../components/ChartPanel.vue'
import { miniLineOption } from '../lib/echarts'
import type { EChartsOption } from 'echarts'
import { MUTED, TEXT, BORDER } from '../lib/echarts'

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

const top50 = computed<StockRow[]>(() => conc.value?.top50 ?? [])

// 行业显示：优先使用已有的 lv1 / lv2；当前数据未提供时显示 —
function industryText(row: StockRow): string {
  if (row.lv1 && row.lv2) return `${row.lv1} / ${row.lv2}`
  if (row.lv1) return row.lv1
  return '—'
}

// 三个辅助指标：Top10 / Top20 / Top50 成交占比
const share10 = computed(() => top50.value.slice(0, 10).reduce((s, x) => s + (x.pct_of_total ?? 0), 0))
const share20 = computed(() => top50.value.slice(0, 20).reduce((s, x) => s + (x.pct_of_total ?? 0), 0))
const share50 = computed(() => top50.value.slice(0, 50).reduce((s, x) => s + (x.pct_of_total ?? 0), 0))

// 资金重要程度颜色分层
function rankColor(rank: number): string {
  if (rank <= 10) return '#C0392B' // 核心资金区：暖红色系
  if (rank <= 20) return '#E67E22' // 次核心资金区：橙色系
  return '#5D6D7E' // 普通活跃区：灰蓝色系
}

const top50Opt = computed<EChartsOption>(() => {
  const rows = top50.value
  const data = rows.map((r, i) => ({
    value: r.amount,
    itemStyle: { color: rankColor(i + 1) },
    code: r.code,
    name: r.name,
    rank: i + 1,
    pct: r.pct_of_total ?? 0
  }))
  return {
    animation: false,
    grid: { left: 8, right: 8, top: 28, bottom: 28, containLabel: true },
    tooltip: {
      trigger: 'axis',
      confine: true,
      backgroundColor: '#131820',
      borderColor: BORDER,
      textStyle: { color: TEXT, fontSize: 12 },
      axisPointer: { type: 'shadow' as const },
      formatter: (params: unknown) => {
        const p = (params as { data: typeof data[0] }[])[0]?.data
        if (!p) return ''
        return `<b>#${p.rank} ${p.name}</b>（${p.code}）<br/>成交额：${p.value.toFixed(2)} 亿<br/>占市场：${p.pct.toFixed(2)}%`
      }
    },
    xAxis: {
      type: 'category',
      data: rows.map((_, i) => String(i + 1)),
      axisLine: { lineStyle: { color: BORDER } },
      axisTick: { show: false },
      axisLabel: { color: MUTED, fontSize: 10, interval: 4 }
    },
    yAxis: {
      type: 'value',
      scale: true,
      name: '成交额（亿）',
      nameTextStyle: { color: MUTED, fontSize: 11, padding: [0, 0, 0, 40] },
      splitLine: { lineStyle: { color: BORDER, type: 'dashed' } },
      axisLabel: { color: MUTED, fontSize: 10 }
    },
    series: [{
      type: 'bar' as const,
      data,
      barWidth: '60%',
      label: { show: false }
    }]
  }
})

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
    <p class="page-desc">资金结构视角：前50名成交排名 + 分层占比 · 判断龙头集中 / 资金扩散 / 普遍活跃</p>

    <template v-if="conc && daily">
      <!-- ① Top50 成交排名柱状图 -->
      <div class="card" style="margin-top:14px">
        <div class="card-title">📊 Top50 成交排名（按成交额降序 · 1-10核心/11-20次核心/21-50普通）</div>
        <ChartPanel :option="top50Opt" height="320px" />
      </div>

      <!-- ② Top50 个股排名表 -->
      <div class="card" style="margin-top:14px">
        <div class="card-title">📋 Top50 成交额个股排名</div>
        <div class="table-wrap" style="margin-top:8px">
          <table class="data">
            <thead>
              <tr>
                <th style="width:50px">排名</th>
                <th>股票代码</th>
                <th>股票名称</th>
                <th class="num" style="width:110px">成交额(亿元)</th>
                <th class="num" style="width:110px">占市场成交</th>
                <th>行业</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in top50" :key="row.code">
                <td>
                  <span class="rank-dot" :style="{ background: rankColor(i + 1) }"></span>
                  {{ i + 1 }}
                </td>
                <td class="num">{{ row.code }}</td>
                <td>{{ row.name }}</td>
                <td class="num">{{ fmt(row.amount) }}</td>
                <td class="num">{{ row.pct_of_total ?? 0 }}%</td>
                <td>{{ industryText(row) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ③ Top10/20/50 集中度卡片 -->
      <div class="card-grid cols-3" style="margin-top:14px">
        <div class="card">
          <div class="card-title">🔴 核心资金区 Top10</div>
          <div class="card-value num">{{ fmt(share10) }}<span class="unit">%</span></div>
          <div class="card-sub num">市场最核心成交资金</div>
          <span class="card-sample num">占全市场成交</span>
        </div>
        <div class="card">
          <div class="card-title">🟠 次核心资金区 Top20</div>
          <div class="card-value num">{{ fmt(share20) }}<span class="unit">%</span></div>
          <div class="card-sub num">较前10 +{{ fmt(share20 - share10) }}pct</div>
          <span class="card-sample num">含前10累计</span>
        </div>
        <div class="card">
          <div class="card-title">🔵 普通活跃区 Top50</div>
          <div class="card-value num">{{ fmt(share50) }}<span class="unit">%</span></div>
          <div class="card-sub num">较前20 +{{ fmt(share50 - share20) }}pct</div>
          <span class="card-sample num">含前20累计</span>
        </div>
      </div>

      <!-- ④ 头部抱团度历史折线 -->
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

<style scoped>
.rank-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}
</style>

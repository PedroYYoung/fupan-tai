<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDataStore } from '../stores/data'
import type { IndexObservation } from '../types'
import ChartPanel from '../components/ChartPanel.vue'
import type { EChartsOption } from 'echarts'
import { MUTED, TEXT, BORDER } from '../lib/echarts'

const store = useDataStore()
const daily = computed(() => store.daily)
const obsMap = computed(() => {
  const map = new Map<string, IndexObservation>()
  daily.value?.index_observation?.forEach((o) => map.set(o.code, o))
  return map
})

const idxRows = computed(() => daily.value?.index_volume ?? [])

function fmt(n: number | null | undefined, digits = 0): string {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}
function signPct(n: number | null | undefined): string {
  if (n == null) return '—'
  return (n > 0 ? '+' : '') + fmt(n, 2) + '%'
}
/** 较上一交易日变化：缺失返回「（—）」；成交额/均额用金额差，百分比用百分点差 */
function deltaText(v: number | null | undefined, digits = 2): string {
  if (v == null) return '（—）'
  const s = v > 0 ? '+' + fmt(v, digits) : fmt(v, digits)
  return `（${s}）`
}
function deltaClass(v: number | null | undefined): string {
  if (v == null) return 'muted'
  return v > 0 ? 'up' : v < 0 ? 'down' : 'muted'
}
function pctClass(n: number | null | undefined): string {
  if (n == null) return 'muted'
  return n > 0 ? 'up' : n < 0 ? 'down' : 'muted'
}

// 上证指数/深证成指 成交额均值对比图
const shszCodes = ['sh000001', 'sz399001']
const compareOpt = computed<EChartsOption | null>(() => {
  const rows = idxRows.value.filter((r) => shszCodes.includes(r.code))
  if (!rows.length) return null
  const labels = ['今日', '本周平均', '本月平均', '年内平均']
  const series = rows.map((r) => {
    const o = obsMap.value.get(r.code)
    return {
      name: r.name,
      type: 'bar' as const,
      data: [
        r.amount ?? 0,
        o?.avg_week_amount ?? 0,
        o?.avg_month_amount ?? 0,
        o?.avg_year_amount ?? 0
      ],
      itemStyle: { borderRadius: [4, 4, 0, 0] }
    }
  })
  return {
    animation: false,
    grid: { left: 8, right: 8, top: 30, bottom: 4, containLabel: true },
    legend: { top: 2, textStyle: { color: MUTED, fontSize: 11 } },
    tooltip: {
      trigger: 'axis', confine: true,
      backgroundColor: '#131820', borderColor: BORDER, textStyle: { color: TEXT, fontSize: 12 }
    },
    xAxis: {
      type: 'category', data: labels,
      axisLine: { lineStyle: { color: BORDER } }, axisTick: { show: false },
      axisLabel: { color: MUTED, fontSize: 11 }
    },
    yAxis: {
      type: 'value', name: '亿元', nameTextStyle: { color: MUTED, fontSize: 10 },
      splitLine: { lineStyle: { color: BORDER, type: 'dashed' } },
      axisLabel: { color: MUTED, fontSize: 10 }
    },
    series
  }
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">📊 指数观察 · <span class="num">{{ daily ? store.formatDay(daily.trade_date) : '—' }}</span></h1>
    <p class="page-desc">主要指数成交额 + 年内涨跌幅 + 本周/本月/年内均额 · 括号内为较上一交易日变化（成交额/均额为亿元差，涨跌幅为百分点差）</p>

    <div v-if="daily" class="card" style="margin-top:14px">
      <div class="table-wrap">
        <table class="data">
          <thead>
            <tr>
              <th>指数</th>
              <th>当日成交额（亿）</th>
              <th>今年涨跌幅</th>
              <th>本周平均</th>
              <th>本月平均</th>
              <th>年内平均</th>
              <th>历史百分位</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in idxRows" :key="r.code">
              <td>{{ r.name }} <span v-if="r.approx" class="muted" style="font-size:11px">（近似值）</span></td>
              <td class="num">{{ fmt(r.amount, 2) }}<span class="muted" :class="deltaClass(r.amount_change)">{{ deltaText(r.amount_change, 2) }}</span></td>
              <td class="num" :class="pctClass(obsMap.get(r.code)?.ytd_pct)">
                {{ signPct(obsMap.get(r.code)?.ytd_pct) }}<span class="muted" :class="deltaClass(obsMap.get(r.code)?.ytd_pct_change)">{{ deltaText(obsMap.get(r.code)?.ytd_pct_change, 2) }}</span>
              </td>
              <td class="num">{{ fmt(obsMap.get(r.code)?.avg_week_amount, 2) }}<span class="muted" :class="deltaClass(obsMap.get(r.code)?.avg_week_change)">{{ deltaText(obsMap.get(r.code)?.avg_week_change, 2) }}</span></td>
              <td class="num">{{ fmt(obsMap.get(r.code)?.avg_month_amount, 2) }}<span class="muted" :class="deltaClass(obsMap.get(r.code)?.avg_month_change)">{{ deltaText(obsMap.get(r.code)?.avg_month_change, 2) }}</span></td>
              <td class="num">{{ fmt(obsMap.get(r.code)?.avg_year_amount, 2) }}<span class="muted" :class="deltaClass(obsMap.get(r.code)?.avg_year_change)">{{ deltaText(obsMap.get(r.code)?.avg_year_change, 2) }}</span></td>
              <td class="num">{{ r.pctile_all != null ? r.pctile_all + '%' : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <div class="card-title">📈 上证 / 深证 成交额均值对比（亿）</div>
      <ChartPanel v-if="compareOpt" :option="compareOpt" height="260px" />
      <div v-else class="empty-box">🟡 暂无指数观察数据</div>
    </div>

    <div v-if="!daily" class="empty-box">
      🟡 该日期暂无数据（最后更新：{{ store.meta?.updated_at ?? '—' }}），已展示最近一个有效交易日
    </div>
  </div>
</template>

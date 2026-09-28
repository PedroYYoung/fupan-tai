<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDataStore } from '../stores/data'
import { PERIODS, aggFromCodeAgg, pctileText, type Period } from '../lib/agg'
import type { IndexAggFile } from '../types'

const store = useDataStore()
const period = ref<Period>('day')
const aggFile = ref<IndexAggFile | null>(null)
const ready = ref(false)

watch(
  () => store.currentDate,
  async () => {
    if (!store.currentDate) return
    ready.value = false
    try {
      aggFile.value = await (await fetch('/data/series/index_agg.json')).json() as IndexAggFile
    } catch {
      aggFile.value = null
    }
    ready.value = true
  },
  { immediate: true }
)

const daily = computed(() => store.daily)
const nAll = computed(() => store.allSampleN())

interface Row {
  name: string; code: string; approx: boolean
  value: number | null
  rankYear: number | null
  rank1y: number | null
  rank: number | null
  pctile: number | null
  sampleN: number
}

const rows = computed<Row[]>(() => {
  const d = daily.value
  if (!d) return []
  const isDay = period.value === 'day'
  return d.index_volume.map((r) => {
    const agg = aggFromCodeAgg(aggFile.value?.codes[r.code], d.trade_date, period.value)
    return {
      name: r.name, code: r.code, approx: !!r.approx,
      value: isDay ? r.amount : agg.value,
      rankYear: isDay ? r.rank_year : null,
      rank1y: isDay ? r.rank_1y : null,
      rank: isDay ? null : agg.rank,
      pctile: isDay ? r.pctile_all : null,
      sampleN: isDay ? nAll.value : agg.sampleN
    }
  })
})

function fmt(n: number | null | undefined, digits = 0): string {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}

function pctileCell(row: Row): string {
  if (period.value === 'day') {
    if (row.pctile == null) return '—'
    return nAll.value >= 30 ? `历史 ${row.pctile}%` : '样本不足'
  }
  if (row.rank == null) return '—'
  return pctileText(row.rank, row.sampleN)
}
</script>

<template>
  <div class="page">
    <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;">
      <div>
        <h1 class="page-title">📊 指数成交排位 · <span class="num">{{ daily ? store.formatDay(daily.trade_date) : '—' }}</span></h1>
        <p class="page-desc">5 大指数成交额排位 · 恒生科技等以 ETF 成交额近似（UI 已标注）</p>
      </div>
      <div style="display:flex; gap:6px;">
        <button v-for="p in PERIODS" :key="p.key" class="btn" :class="period === p.key ? '' : 'secondary'" @click="period = p.key">{{ p.label }}</button>
      </div>
    </div>

    <div v-if="daily" class="card" style="margin-top:14px">
      <div class="table-wrap">
        <table class="data">
          <thead>
            <tr>
              <th>指数</th>
              <th>{{ period === 'day' ? '当日成交额(亿)' : period === 'month' ? '本月均值(亿)' : period === 'year' ? '本年均值(亿)' : '历史均值(亿)' }}</th>
              <th>年内排名</th>
              <th>近一年排名</th>
              <th>历史百分位</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.code">
              <td>{{ r.name }} <span v-if="r.approx" class="muted" style="font-size:11px">（近似值）</span></td>
              <td class="num">{{ fmt(r.value, 2) }}</td>
              <td class="num">{{ period === 'day' ? (r.rankYear ?? '—') : (r.rank != null ? `第 ${r.rank} 名` : '—') }}</td>
              <td class="num">{{ period === 'day' ? (r.rank1y ?? '—') : '—' }}</td>
              <td class="num">{{ pctileCell(r) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="card-sub num" style="margin-top:6px">样本N={{ rows[0]?.sampleN ?? nAll }}</div>
      <div class="muted" style="font-size:12px; margin-top:4px">
        行固定：上证 / 深成指 / 创业板指 / 科创50 / 北证50。月/年/历史档排名为「均值在同口径历史均值样本中的降序排位」。
      </div>
    </div>
    <div v-else class="empty-box">
      🟡 该日期暂无数据（最后更新：{{ store.meta?.updated_at ?? '—' }}），已展示最近一个有效交易日
    </div>
  </div>
</template>

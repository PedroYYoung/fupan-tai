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

interface Cell {
  name: string; code: string; amount: number | null; approx: boolean
  value: number | null
  rank1y: number | null
  pctile: number | null
  sampleN: number
}

/** 百分位 → 色阶（放量集中区越深）：0%→透明，100%→#B7410E */
function heatStyle(pctile: number | null): Record<string, string> {
  if (pctile == null) return { background: 'transparent' }
  const a = 0.08 + (pctile / 100) * 0.55
  return { background: `rgba(183, 65, 14, ${a.toFixed(2)})` }
}

const cells = computed<Cell[]>(() => {
  const d = daily.value
  if (!d) return []
  const isDay = period.value === 'day'
  return d.widebase.map((r) => {
    const agg = aggFromCodeAgg(aggFile.value?.codes[r.code], d.trade_date, period.value)
    return {
      name: r.name, code: r.code, amount: r.amount, approx: !!r.approx,
      value: isDay ? r.amount : agg.value,
      rank1y: isDay ? r.rank_1y : agg.rank,
      pctile: isDay ? r.pctile_all : (agg.rank != null && agg.sampleN > 1
        ? Math.round(((agg.sampleN - agg.rank) / (agg.sampleN - 1)) * 1000) / 10
        : null),
      sampleN: isDay ? nAll.value : agg.sampleN
    }
  })
})

function fmt(n: number | null | undefined, digits = 0): string {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}

function sub(c: Cell): string {
  if (period.value === 'day') {
    const p = c.pctile != null && nAll.value >= 30 ? `历史 ${c.pctile}%` : '样本不足'
    return `近一年第 ${c.rank1y ?? '—'} 名 · ${p}`
  }
  if (c.rank1y != null) {
    return `均值历史第 ${c.rank1y} 名（N=${c.sampleN}）`
  }
  return '—'
}
</script>

<template>
  <div class="page">
    <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;">
      <div>
        <h1 class="page-title">🧩 宽基矩阵 · <span class="num">{{ daily ? store.formatDay(daily.trade_date) : '—' }}</span></h1>
        <p class="page-desc">11 格宽基成交额矩阵 · 色阶越深=历史百分位越高（放量集中区）</p>
      </div>
      <div style="display:flex; gap:6px;">
        <button v-for="p in PERIODS" :key="p.key" class="btn" :class="period === p.key ? '' : 'secondary'" @click="period = p.key">{{ p.label }}</button>
      </div>
    </div>

    <div v-if="daily" style="display:grid; grid-template-columns:repeat(auto-fill, minmax(170px, 1fr)); gap:12px; margin-top:14px;">
      <div v-for="c in cells" :key="c.code" class="card" :style="heatStyle(period === 'day' ? c.pctile : null)" style="padding:12px 14px 26px">
        <div class="card-title" style="font-size:13px">
          {{ c.name }} <span v-if="c.approx" class="muted" style="font-size:10px">近似</span>
        </div>
        <div class="card-value num" style="font-size:19px">{{ fmt(c.value, 2) }}<span class="unit">亿</span></div>
        <div class="card-sub num" style="font-size:11px">{{ sub(c) }}</div>
        <span v-if="c.sampleN >= 30" class="card-sample num">N={{ c.sampleN }}</span>
        <span v-else class="card-insufficient">样本不足</span>
      </div>
    </div>

    <div v-if="daily" class="card" style="margin-top:14px">
      <div class="card-title">📖 口径说明</div>
      <ul class="muted" style="font-size:12px; margin:8px 0 0 18px; line-height:1.9">
        <li>微盘代理 = 全A按总市值升序取后10%等权合成（自建口径，非官方指数），取其日均成交额序列参与排名。</li>
        <li>全A代理 = 中证全指（000985）；恒生科技以 ETF 513180 成交额近似，受 ETF 规模与溢价影响，仅作方向参考。</li>
        <li>色阶 = 当日成交额的历史百分位（(N-排名)/(N-1)×100），颜色越深表示相对历史越放量。</li>
        <li>月/年/历史档 = 各自窗口均值在同口径历史均值样本中的排位与百分位。</li>
      </ul>
    </div>
    <div v-else class="empty-box">
      🟡 该日期暂无数据（最后更新：{{ store.meta?.updated_at ?? '—' }}），已展示最近一个有效交易日
    </div>
  </div>
</template>

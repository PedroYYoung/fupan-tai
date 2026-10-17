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
  /** 成交额实际对应的交易日（降级时早于当前交易日） */
  amountDate: string | null
  /** '' 当日真实值 / 'last_trading_day' 取自最近交易日 / 'etf_proxy' ETF 代理 */
  note: string
  /** 当日涨跌幅（%） */
  changePct: number | null
  /** 成交额较上一交易日差（亿） */
  amountChange: number | null
  value: number | null
  rank1y: number | null
  pctile: number | null
  sampleN: number
}

/** 涨跌幅 → 背景色：涨红跌绿，颜色强度随 |涨跌幅| 线性加深，3% 封顶；缺失/平盘中性 */
function changeBg(pct: number | null): Record<string, string> {
  if (pct == null || pct === 0) return {}
  const intensity = Math.min(Math.abs(pct) / 3, 1)
  const alpha = 0.06 + intensity * 0.5
  const rgb = pct > 0 ? '255, 77, 79' : '34, 197, 94'
  return { background: `rgba(${rgb}, ${alpha.toFixed(2)})` }
}

function pctColor(pct: number | null): string {
  if (pct == null) return 'var(--muted)'
  return pct > 0 ? 'var(--up)' : pct < 0 ? 'var(--down)' : 'var(--muted)'
}

function pctText(pct: number | null): string {
  if (pct == null) return '—'
  return (pct > 0 ? '+' : '') + pct.toFixed(2) + '%'
}

const cells = computed<Cell[]>(() => {
  const d = daily.value
  if (!d) return []
  const isDay = period.value === 'day'
  // 移除微盘股（仅矩阵展示层，底层 index_amount_micro_proxy 序列与数据保留）
  return d.widebase
    .filter((r) => r.code !== 'micro_proxy')
    .map((r) => {
      const agg = aggFromCodeAgg(aggFile.value?.codes[r.code], d.trade_date, period.value)
      return {
        name: r.name, code: r.code, amount: r.amount, approx: !!r.approx,
        amountDate: r.amount_date ?? null, note: r.note ?? '',
        changePct: r.change_pct ?? null, amountChange: r.amount_change ?? null,
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

function amountDeltaText(v: number | null): string {
  if (v == null) return ''
  return (v > 0 ? '+' : '') + fmt(v, 2)
}

function sub(c: Cell): string {
  if (period.value === 'day') {
    if (c.amount == null) return '当日成交额未获取'
    if (c.note === 'etf_proxy') return 'ETF代理 · 量级不可比'
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
        <p class="page-desc">宽基指数涨跌红绿（颜色深浅随涨跌幅）+ 成交额与较昨日变化</p>
      </div>
      <div style="display:flex; gap:6px;">
        <button v-for="p in PERIODS" :key="p.key" class="btn" :class="period === p.key ? '' : 'secondary'" @click="period = p.key">{{ p.label }}</button>
      </div>
    </div>

    <div v-if="daily" style="display:grid; grid-template-columns:repeat(auto-fill, minmax(170px, 1fr)); gap:12px; margin-top:14px;">
      <div v-for="c in cells" :key="c.code" class="card" :style="period === 'day' ? changeBg(c.changePct) : {}" style="padding:12px 14px 20px">
        <div class="card-title" style="font-size:13px">
          {{ c.name }} <span v-if="c.approx" class="muted" style="font-size:10px">近似</span>
        </div>

        <template v-if="period === 'day'">
          <div class="card-value num" style="font-size:22px; color: pctColor(c.changePct)">{{ pctText(c.changePct) }}</div>
          <div class="num" style="font-size:13px; margin-top:2px">
            {{ fmt(c.amount, 2) }}<span class="unit">亿</span>
            <span style="font-size:11px" :style="{ color: c.amountChange == null ? 'var(--muted)' : c.amountChange > 0 ? 'var(--up)' : c.amountChange < 0 ? 'var(--down)' : 'var(--muted)' }">
              （{{ c.amountChange != null ? amountDeltaText(c.amountChange) : '—' }}）
            </span>
          </div>
          <div class="card-sub num" style="font-size:11px">{{ sub(c) }}</div>
          <div v-if="c.note === 'last_trading_day' && c.amountDate" style="font-size:10px; color:var(--warn); margin-top:3px">* 数据来自 {{ store.formatDay(c.amountDate) }}</div>
        </template>

        <template v-else>
          <div class="card-value num" style="font-size:19px">{{ fmt(c.value, 2) }}<span class="unit">亿</span></div>
          <div class="card-sub num" style="font-size:11px">{{ sub(c) }}</div>
        </template>

        <span v-if="c.sampleN >= 30" class="card-sample num">N={{ c.sampleN }}</span>
        <span v-else class="card-insufficient">样本不足</span>
      </div>
    </div>

    <div v-if="daily" class="card" style="margin-top:14px">
      <div class="card-title">📖 口径说明</div>
      <ul class="muted" style="font-size:12px; margin:8px 0 0 18px; line-height:1.9">
        <li>涨跌幅 = 指数当日涨跌幅（baostock/腾讯），涨红跌绿，颜色深浅随 |涨跌幅| 线性加深，3% 封顶；缺失或平盘为中性样式。</li>
        <li>成交额 = 当日成交额（亿元），括号内为较上一交易日成交额差（亿）。</li>
        <li>历史百分位 = 当日成交额在自身全历史成交额样本中的分位（(N-排名)/(N-1)×100），颜色越深历史分位越高。</li>
        <li>全A代理 = 中证全指（000985）；恒生科技以 ETF 513180 成交额近似，仅作方向参考。</li>
        <li>月/年/历史档 = 各自窗口成交额均值在同口径历史均值样本中的排位与百分位。</li>
        <li>成交额带「*」的格子 = 当日行情源未取到值，降级展示最近一个已收盘交易日的真实成交额（复用自身历史，非估算），下方标注数据日期。</li>
      </ul>
    </div>
    <div v-else class="empty-box">
      🟡 该日期暂无数据（最后更新：{{ store.meta?.updated_at ?? '—' }}），已展示最近一个有效交易日
    </div>
  </div>
</template>

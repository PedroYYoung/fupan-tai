<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDataStore } from '../stores/data'
import type { IndexObservation, IndexAggFile } from '../types'
import ChartPanel from '../components/ChartPanel.vue'
import type { EChartsOption } from 'echarts'
import { MUTED, TEXT, BORDER } from '../lib/echarts'
import { PERIODS, aggFromCodeAgg, type Period } from '../lib/agg'
import { fmtNum, pctDelta, numDelta, pctClass } from '../lib/format'

const store = useDataStore()
const daily = computed(() => store.daily)
const obsMap = computed(() => {
  const map = new Map<string, IndexObservation>()
  daily.value?.index_observation?.forEach((o) => map.set(o.code, o))
  return map
})

const idxRows = computed(() => daily.value?.index_volume ?? [])

// ---- 宽基矩阵（合并自原宽基矩阵页；移除微盘股展示，底层序列保留）----
const period = ref<Period>('day')
const aggFile = ref<IndexAggFile | null>(null)
watch(
  () => store.currentDate,
  async () => {
    if (!store.currentDate) return
    try {
      aggFile.value = await (await fetch('/data/series/index_agg.json')).json() as IndexAggFile
    } catch {
      aggFile.value = null
    }
  },
  { immediate: true }
)
const nAll = computed(() => store.allSampleN())

interface Cell {
  name: string; code: string; amount: number | null; approx: boolean
  amountDate: string | null
  note: string
  changePct: number | null
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

function pctText(pct: number | null | undefined): string {
  if (pct == null) return '—'
  return (pct > 0 ? '+' : '') + pct.toFixed(2) + '%'
}

const cells = computed<Cell[]>(() => {
  const d = daily.value
  if (!d) return []
  const isDay = period.value === 'day'
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

function sub(c: Cell): string {
  if (period.value === 'day') {
    if (c.amount == null) return '当日成交额未获取'
    if (c.note === 'etf_proxy') return 'ETF代理 · 量级不可比'
    const p = c.pctile != null && nAll.value >= 30 ? `历史 ${c.pctile}%` : '样本不足'
    return `近一年第 ${c.rank1y ?? '—'} 名 · ${p}`
  }
  if (c.rank1y != null) return `均值历史第 ${c.rank1y} 名（N=${c.sampleN}）`
  return '—'
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
    <p class="page-desc">主要指数行情（点位/涨跌幅/成交额/年内涨跌幅/周月年均额）+ 宽基矩阵历史分位 · 括号内为较上一交易日变化，百分比统一为差值格式</p>

    <template v-if="daily">
      <!-- ① 主要指数行情表 -->
      <div class="card" style="margin-top:14px">
        <div class="card-title">📈 主要指数行情</div>
        <div class="table-wrap" style="margin-top:8px">
          <table class="data">
            <thead>
              <tr>
                <th>指数</th>
                <th class="num">点位</th>
                <th class="num">涨跌幅</th>
                <th class="num">当日成交额（亿）</th>
                <th class="num">今年涨跌幅</th>
                <th class="num">本周平均</th>
                <th class="num">本月平均</th>
                <th class="num">年内平均</th>
                <th class="num">历史百分位</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in idxRows" :key="r.code">
                <td>{{ r.name }} <span v-if="r.approx" class="muted" style="font-size:11px">（近似值）</span></td>
                <td class="num" :class="pctClass(r.change_pct)">
                  {{ fmtNum(r.close, 2) }}<span class="muted">{{ numDelta(r.close_change, 2) }}</span>
                </td>
                <td class="num" :class="pctClass(r.change_pct)">{{ pctText(r.change_pct) }}</td>
                <td class="num">{{ fmtNum(r.amount, 2) }}<span class="muted">{{ numDelta(r.amount_change, 2, '亿') }}</span></td>
                <td class="num" :class="pctClass(obsMap.get(r.code)?.ytd_pct)">
                  {{ obsMap.get(r.code)?.ytd_pct != null ? (obsMap.get(r.code)!.ytd_pct! > 0 ? '+' : '') + fmtNum(obsMap.get(r.code)!.ytd_pct, 2) + '%' : '—' }}
                  <span class="muted">{{ pctDelta(obsMap.get(r.code)?.ytd_pct_change, 2) }}</span>
                </td>
                <td class="num">{{ fmtNum(obsMap.get(r.code)?.avg_week_amount, 2) }}<span class="muted">{{ numDelta(obsMap.get(r.code)?.avg_week_change, 2, '亿') }}</span></td>
                <td class="num">{{ fmtNum(obsMap.get(r.code)?.avg_month_amount, 2) }}<span class="muted">{{ numDelta(obsMap.get(r.code)?.avg_month_change, 2, '亿') }}</span></td>
                <td class="num">{{ fmtNum(obsMap.get(r.code)?.avg_year_amount, 2) }}<span class="muted">{{ numDelta(obsMap.get(r.code)?.avg_year_change, 2, '亿') }}</span></td>
                <td class="num">{{ r.pctile_all != null ? r.pctile_all + '%' : '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ② 上证 / 深证 成交额均值对比 -->
      <div class="card" style="margin-top:14px">
        <div class="card-title">📊 上证 / 深证 成交额均值对比（亿）</div>
        <ChartPanel v-if="compareOpt" :option="compareOpt" height="260px" />
        <div v-else class="empty-box">🟡 暂无指数观察数据</div>
      </div>

      <!-- ③ 宽基矩阵 -->
      <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; margin-top:18px;">
        <div class="card-title" style="margin:0">🧩 宽基矩阵</div>
        <div style="display:flex; gap:6px;">
          <button v-for="p in PERIODS" :key="p.key" class="btn" :class="period === p.key ? '' : 'secondary'" @click="period = p.key">{{ p.label }}</button>
        </div>
      </div>
      <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(170px, 1fr)); gap:12px; margin-top:10px;">
        <div v-for="c in cells" :key="c.code" class="card" :style="period === 'day' ? changeBg(c.changePct) : {}" style="padding:12px 14px 20px">
          <div class="card-title" style="font-size:13px">
            {{ c.name }} <span v-if="c.approx" class="muted" style="font-size:10px">近似</span>
          </div>

          <template v-if="period === 'day'">
            <div class="card-value num" style="font-size:22px" :style="{ color: pctClass(c.changePct) === 'up' ? 'var(--up)' : pctClass(c.changePct) === 'down' ? 'var(--down)' : 'var(--muted)' }">{{ pctText(c.changePct) }}</div>
            <div class="num" style="font-size:13px; margin-top:2px">
              {{ fmtNum(c.amount, 2) }}<span class="unit">亿</span>
              <span style="font-size:11px" :style="{ color: c.amountChange == null ? 'var(--muted)' : c.amountChange > 0 ? 'var(--up)' : c.amountChange < 0 ? 'var(--down)' : 'var(--muted)' }">
                （{{ c.amountChange != null ? (c.amountChange > 0 ? '+' : '') + fmtNum(c.amountChange, 2) : '—' }}）
              </span>
            </div>
            <div class="card-sub num" style="font-size:11px">{{ sub(c) }}</div>
            <div v-if="c.note === 'last_trading_day' && c.amountDate" style="font-size:10px; color:var(--warn); margin-top:3px">* 数据来自 {{ store.formatDay(c.amountDate) }}</div>
          </template>

          <template v-else>
            <div class="card-value num" style="font-size:19px">{{ fmtNum(c.value, 2) }}<span class="unit">亿</span></div>
            <div class="card-sub num" style="font-size:11px">{{ sub(c) }}</div>
          </template>

          <span v-if="c.sampleN >= 30" class="card-sample num">N={{ c.sampleN }}</span>
          <span v-else class="card-insufficient">样本不足</span>
        </div>
      </div>

      <!-- ④ 口径说明 -->
      <div class="card" style="margin-top:14px">
        <div class="card-title">📖 口径说明</div>
        <ul class="muted" style="font-size:12px; margin:8px 0 0 18px; line-height:1.9">
          <li>点位 = 指数当日收盘点位（baostock/新浪），括号内为较上一交易日点位差。</li>
          <li>涨跌幅 = 指数当日涨跌幅（baostock/腾讯），涨红跌绿，宽基矩阵颜色深浅随 |涨跌幅| 线性加深，3% 封顶。</li>
          <li>今年涨跌幅 =（当日收盘 ÷ 上一年度最后交易日收盘 − 1）× 100%，括号内为与上一交易日的差值（百分点差，统一用 % 显示）。</li>
          <li>本周/本月/年内平均 = 对应周期内指数成交额均值（亿元），括号内为较上一交易日均值差。</li>
          <li>历史百分位 = 当日成交额在自身全历史成交额样本中的分位（(N-排名)/(N-1)×100）。</li>
          <li>全A代理 = 中证全指（000985）；恒生科技以 ETF 513180 成交额近似，仅作方向参考。</li>
          <li>宽基矩阵「本月/本年/历史」档 = 各自窗口成交额均值在同口径历史均值样本中的排位与百分位。</li>
          <li>成交额带「*」的格子 = 当日行情源未取到值，降级展示最近一个已收盘交易日的真实成交额（复用自身历史，非估算），下方标注数据日期。</li>
        </ul>
      </div>
    </template>
    <div v-else class="empty-box">
      🟡 该日期暂无数据（最后更新：{{ store.meta?.updated_at ?? '—' }}），已展示最近一个有效交易日
    </div>
  </div>
</template>

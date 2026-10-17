<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDataStore } from '../stores/data'
import type { SeriesPoint, ActiveStock } from '../types'
import ChartPanel from '../components/ChartPanel.vue'
import type { EChartsOption } from 'echarts'
import { UP, DOWN, MUTED, TEXT, BORDER } from '../lib/echarts'
import { fmtNum } from '../lib/format'

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
const activeStocks = computed<ActiveStock[]>(() => daily.value?.active_stocks ?? [])

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

const nAll = computed(() => store.allSampleN())

// ---- 导出 ----
function download(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/** 导出完整 CSV（UTF-8 BOM；证券代码用 ="xxxxxx" 强制 Excel 保留前导零） */
function exportCsv() {
  const rows = activeStocks.value
  const date = daily.value?.trade_date ?? ''
  if (!rows.length) {
    window.alert('当前交易日无符合条件的个股，不导出')
    return
  }
  const esc = (s: string) => `"${s.replace(/"/g, '""')}"`
  let csv = '\uFEFF交易日期,证券代码,股票名称,收盘价,涨跌幅,成交额(亿元),涨停状态\n'
  for (const s of rows) {
    csv += `${date},="${s.code}",${esc(s.name)},${s.close},${s.change_pct},${s.amount},${s.is_limit_up ? '涨停' : '—'}\n`
  }
  download(`5亿成交额_涨幅5%以上_${date}.csv`, csv, 'text/csv;charset=utf-8')
}

/** 导出同花顺自选清单（TXT，每行一个 6 位代码） */
function exportThs() {
  const rows = activeStocks.value
  const date = daily.value?.trade_date ?? ''
  if (!rows.length) {
    window.alert('当前交易日无符合条件的个股，不导出')
    return
  }
  const txt = rows.map((s) => s.code).join('\n') + '\n'
  download(`同花顺自选清单_${date}.txt`, txt, 'text/plain;charset=utf-8')
}
</script>

<template>
  <div class="page">
    <h1 class="page-title">🔥 上板与上涨 · <span class="num">{{ daily ? store.formatDay(daily.trade_date) : '—' }}</span></h1>
    <p class="page-desc">涨停/跌停家数（5亿/10亿成交额门槛）+ 高活跃个股（成交额≥5亿且涨幅≥5%）· 剔除 ST/北交所/上市不足250日</p>

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
          <div class="card-value num">{{ fmtNum(emotion.lu_ratio_of_total, 2) }} / {{ fmtNum(emotion.ld_ratio_of_total, 2) }}<span class="unit">%</span></div>
          <div class="card-sub">涨停 / 跌停 占全部 {{ daily.overview.stock_count }} 只个股</div>
        </div>
        <div class="card">
          <div class="card-title">🎯 占10亿以上%</div>
          <div class="card-value num">{{ fmtNum(emotion.lu_ratio_of_over10e, 1) }} / {{ fmtNum(emotion.ld_ratio_of_over10e, 1) }}<span class="unit">%</span></div>
          <div class="card-sub">10亿以上共 {{ daily.overview.over_10e_count }} 家</div>
        </div>
      </div>

      <!-- 5亿 / 10亿 成交额门槛涨跌停统计 -->
      <div class="card" style="margin-top:14px">
        <div class="card-title">📊 成交额门槛 · 涨跌停家数</div>
        <div class="table-wrap" style="margin-top:8px">
          <table class="data">
            <thead><tr><th>成交额门槛</th><th class="num">涨停家数</th><th class="num">跌停家数</th><th class="num">合计</th></tr></thead>
            <tbody>
              <tr>
                <td>≥ 5 亿元</td>
                <td class="num up">{{ emotion.lu_over5e_count ?? '—' }}</td>
                <td class="num down">{{ emotion.ld_over5e_count ?? '—' }}</td>
                <td class="num">{{ (emotion.lu_over5e_count ?? 0) + (emotion.ld_over5e_count ?? 0) }}</td>
              </tr>
              <tr>
                <td>≥ 10 亿元（含于 ≥5 亿）</td>
                <td class="num up">{{ emotion.lu_over10e.length }}</td>
                <td class="num down">{{ emotion.ld_over10e.length }}</td>
                <td class="num">{{ emotion.lu_over10e.length + emotion.ld_over10e.length }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="muted" style="font-size:11px; margin:6px 0 0">注：10亿以上股票同时属于5亿以上范围，两档为包含关系，不可直接相加作为市场总数。</p>
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
                  <td class="num">{{ fmtNum(s.amount, 2) }}</td>
                  <td class="num up">+{{ fmtNum(s.change ?? 0, 2) }}%</td>
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
                  <td class="num">{{ fmtNum(s.amount, 2) }}</td>
                  <td class="num down">{{ fmtNum(s.change ?? 0, 2) }}%</td>
                  <td class="muted">{{ s.board }}</td>
                </tr>
                <tr v-if="!emotion.ld_over10e.length"><td colspan="5" class="muted">无</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- 高活跃个股列表 + 导出 -->
      <div class="card" style="margin-top:14px">
        <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;">
          <div>
            <div class="card-title">📈 高活跃个股（成交额≥5亿 且 涨幅≥5%，共 {{ activeStocks.length }} 只）</div>
            <div class="card-desc">交易日期 {{ store.formatDay(daily.trade_date) }} · 按涨幅降序 · 涨停状态仅在有可靠涨跌停池时标注</div>
          </div>
          <div style="display:flex; gap:8px;">
            <button class="btn" @click="exportCsv">⬇ 导出完整 CSV</button>
            <button class="btn secondary" @click="exportThs">⬇ 导出同花顺自选清单</button>
          </div>
        </div>
        <div class="table-wrap" style="margin-top:8px">
          <table class="data">
            <thead><tr><th>证券代码</th><th>股票名称</th><th class="num">收盘价</th><th class="num">涨跌幅</th><th class="num">成交额(亿)</th><th>涨停状态</th></tr></thead>
            <tbody>
              <tr v-for="s in activeStocks" :key="s.code">
                <td class="num">{{ s.code }}</td>
                <td>{{ s.name }}</td>
                <td class="num">{{ fmtNum(s.close, 2) }}</td>
                <td class="num" :class="s.change_pct > 0 ? 'up' : 'down'">+{{ fmtNum(s.change_pct, 2) }}%</td>
                <td class="num">{{ fmtNum(s.amount, 2) }}</td>
                <td class="num">{{ s.is_limit_up ? '涨停' : '—' }}</td>
              </tr>
              <tr v-if="!activeStocks.length"><td colspan="6" class="muted">无符合条件的个股</td></tr>
            </tbody>
          </table>
        </div>
        <p class="muted" style="font-size:11px; margin-top:6px">
          导出说明：CSV 采用 UTF-8 BOM，证券代码以 ="xxxxxx" 形式保留前导零；同花顺自选清单为 TXT，每行一个 6 位代码（通用格式，请按你使用的同花顺版本实际导入能力核对）。
        </p>
      </div>
    </template>
    <div v-else class="empty-box">
      🟡 该日期暂无数据（最后更新：{{ store.meta?.updated_at ?? '—' }}），已展示最近一个有效交易日
    </div>
  </div>
</template>

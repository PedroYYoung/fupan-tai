<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useDataStore } from '../stores/data'
import { conclude, type BucketPt } from '../rules/engine'
import { getNote, setNote } from '../lib/notesdb'

const store = useDataStore()
const daily = computed(() => store.daily)
const bucketPts = ref<BucketPt[]>([])
watch(
  () => store.currentDate,
  async (d) => {
    if (!d) return
    try {
      const f = await (await fetch('/data/series/mktcap_buckets.json')).json()
      bucketPts.value = f.points ?? []
    } catch {
      bucketPts.value = []
    }
  },
  { immediate: true }
)
const conclusion = computed(() => (daily.value ? conclude(daily.value, bucketPts.value) : null))

const note = ref('')
const savedTip = ref('')
const exporting = ref(false)

onMounted(async () => {
  if (daily.value) {
    try { note.value = await getNote(daily.value.trade_date) } catch { /* IndexedDB 不可用时静默降级 */ }
  }
})

async function saveNote() {
  if (!daily.value) return
  try {
    await setNote(daily.value.trade_date, note.value)
    savedTip.value = '✅ 已保存至本地（IndexedDB，不上服务器）'
    setTimeout(() => (savedTip.value = ''), 2500)
  } catch {
    savedTip.value = '⚠️ 本地存储不可用，备注未保存'
  }
}

async function exportPng() {
  const el = document.getElementById('report-export')
  if (!el || !daily.value) return
  exporting.value = true
  try {
    const html2canvas = (await import('html2canvas')).default
    const canvas = await html2canvas(el, {
      backgroundColor: '#0B0F14',
      scale: 2,
      width: 1200,
      windowWidth: 1200,
      useCORS: true
    })
    const a = document.createElement('a')
    a.download = `复盘报告_${daily.value.trade_date}.png`
    a.href = canvas.toDataURL('image/png')
    a.click()
  } finally {
    exporting.value = false
  }
}

function fmt(n: number | null | undefined, digits = 0): string {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}
</script>

<template>
  <div class="page">
    <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:10px; flex-wrap:wrap;">
      <div>
        <h1 class="page-title">📋 复盘报告 · <span class="num">{{ daily ? store.formatDay(daily.trade_date) : '—' }}</span></h1>
        <p class="page-desc">关键指标总表 + 自动结论，可直接截图或导出 PNG 转发</p>
      </div>
      <button class="btn" :disabled="exporting || !daily" @click="exportPng">
        {{ exporting ? '生成中…' : '🖼️ 导出 PNG' }}
      </button>
    </div>

    <div v-if="daily && conclusion" id="report-export">
      <div class="card" style="margin-bottom:14px">
        <div class="card-title">📊 当日关键指标总表</div>
        <div class="table-wrap">
          <table class="data">
            <thead>
              <tr><th>指标</th><th>数值</th><th>年内排名</th><th>历史百分位</th></tr>
            </thead>
            <tbody>
              <tr>
                <td>两市成交额</td>
                <td class="num">{{ fmt(daily.overview.total_amount) }} 亿</td>
                <td class="num">{{ daily.overview.total_amount_rank_year ?? '—' }}</td>
                <td class="num">{{ daily.overview.total_amount_pctile_all != null ? daily.overview.total_amount_pctile_all + '%' : '—' }}</td>
              </tr>
              <tr>
                <td>两融余额</td>
                <td class="num">{{ daily.overview.margin_balance != null ? fmt(daily.overview.margin_balance) + ' 亿' : '—' }}</td>
                <td class="num">{{ daily.overview.margin_rank_year ?? '—' }}</td>
                <td class="num">{{ daily.overview.margin_pctile_all != null ? daily.overview.margin_pctile_all + '%' : '—' }}</td>
              </tr>
              <tr>
                <td>涨停家数</td>
                <td class="num up">{{ daily.overview.limit_up }}</td>
                <td class="muted">—</td>
                <td class="num">{{ daily.emotion.lu_pctile != null ? daily.emotion.lu_pctile + '%' : '—' }}</td>
              </tr>
              <tr>
                <td>跌停家数</td>
                <td class="num down">{{ daily.overview.limit_down }}</td>
                <td class="muted">—</td>
                <td class="num">{{ daily.emotion.ld_pctile != null ? daily.emotion.ld_pctile + '%' : '—' }}</td>
              </tr>
              <tr>
                <td>10亿以上家数</td>
                <td class="num">{{ fmt(daily.overview.over_10e_count) }} 家</td>
                <td class="muted">—</td>
                <td class="num">{{ daily.liquidity.pctile_count != null ? daily.liquidity.pctile_count + '%' : '—' }}</td>
              </tr>
              <tr>
                <td>前10成交占比</td>
                <td class="num">{{ fmt(daily.concentration.top10.reduce((s, x) => s + (x.pct_of_total ?? 0), 0), 1) }}%</td>
                <td class="muted">—</td>
                <td class="num">{{ daily.concentration.top10_total_pctile_hist != null ? daily.concentration.top10_total_pctile_hist + '%' : '—' }}</td>
              </tr>
              <tr>
                <td>个股总数</td>
                <td class="num">{{ fmt(daily.overview.stock_count) }}</td>
                <td class="muted">—</td>
                <td class="muted">—</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card" style="margin-bottom:14px">
        <div class="card-title">🤖 自动结论（评分 {{ conclusion.score }}/100）</div>
        <div class="conclusion-box" style="margin:10px 0 0">
          <strong>💰 资金：</strong>{{ conclusion.fund.text }}
          <div class="basis">{{ conclusion.fund.basis }}</div>
        </div>
        <div class="conclusion-box" style="margin:10px 0 0">
          <strong>🧩 结构：</strong>{{ conclusion.structure.text }}
          <div class="basis">{{ conclusion.structure.basis }}</div>
        </div>
        <div class="conclusion-box" style="margin:10px 0 0">
          <strong>🔥 情绪：</strong>{{ conclusion.emotion.text }}
          <div class="basis">{{ conclusion.emotion.basis }}</div>
        </div>
      </div>
    </div>

    <div class="card" v-if="daily">
      <div class="card-title">✏️ 手动备注（仅存本地 IndexedDB）</div>
      <textarea v-model="note" class="note-input" style="margin-top:10px" placeholder="记录今日操作、思路、明日计划……"></textarea>
      <div style="margin-top:10px; display:flex; gap:10px; align-items:center;">
        <button class="btn secondary" @click="saveNote">保存备注</button>
        <span class="muted" style="font-size:12px">{{ savedTip }}</span>
      </div>
    </div>

    <div v-else class="empty-box">
      🟡 该日期暂无数据（最后更新：{{ store.meta?.updated_at ?? '—' }}），已展示最近一个有效交易日
    </div>
  </div>
</template>

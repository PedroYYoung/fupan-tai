<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useDataStore } from '../stores/data'
import { conclude, type BucketPt } from '../rules/engine'
import { getNote, setNote } from '../lib/notesdb'
import SpotDataNotice from '../components/SpotDataNotice.vue'
import ReportExport from '../components/ReportExport.vue'

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

// ---- 人工备注 ----
const note = ref('')
const savedTip = ref('')
const exporting = ref(false)

watch(
  () => daily.value?.trade_date,
  async (date) => {
    note.value = ''
    if (date) {
      try { note.value = await getNote(date) } catch { /* IndexedDB 不可用时静默降级 */ }
    }
  },
  { immediate: true }
)

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

async function clearNote() {
  if (!daily.value) return
  if (!window.confirm('确认清空该交易日的备注？此操作不可撤销。')) return
  note.value = ''
  try {
    await setNote(daily.value.trade_date, '')
    savedTip.value = '✅ 已清空该日期备注'
    setTimeout(() => (savedTip.value = ''), 2500)
  } catch {
    savedTip.value = '⚠️ 本地存储不可用，清空未完成'
  }
}

async function exportPng() {
  const el = document.getElementById('report-export')
  if (!el || !daily.value) return
  exporting.value = true
  try {
    const html2canvas = (await import('html2canvas')).default
    const canvas = await html2canvas(el, {
      backgroundColor: '#FFFFFF',
      scale: 1,
      useCORS: true,
      onclone: (clonedDoc) => {
        // 导出白底：背景纯白、默认文字深色；保留 .up(红)/.down(绿) 语义色
        const root = clonedDoc.getElementById('report-export')
        if (!root) return
        root.style.background = '#FFFFFF'
        root.style.color = '#111418'
        root.querySelectorAll('*').forEach((n) => {
          const e = n as HTMLElement
          if (e.classList.contains('up')) { e.style.color = '#C0392B'; return }
          if (e.classList.contains('down')) { e.style.color = '#1E8449'; return }
          e.style.color = '#111418'
          e.style.background = 'transparent'
          e.style.borderColor = '#E5E7EB'
        })
      }
    })
    const a = document.createElement('a')
    a.download = `复盘报告_${daily.value.trade_date}.png`
    a.href = canvas.toDataURL('image/png')
    a.click()
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <div class="page">
    <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:10px; flex-wrap:wrap;">
      <div>
        <h1 class="page-title">📋 复盘报告 · <span class="num">{{ daily ? store.formatDay(daily.trade_date) : '—' }}</span></h1>
        <p class="page-desc">资金 · 结构 · 情绪三维复盘，可直接截图或导出 PNG 转发</p>
        <SpotDataNotice />
      </div>
      <button class="btn" :disabled="exporting || !daily" @click="exportPng">
        {{ exporting ? '生成中…' : '🖼️ 导出 PNG' }}
      </button>
    </div>

    <ReportExport
      v-if="daily && conclusion"
      :daily="daily"
      :conclusion="conclusion"
      :note="note"
      :updated-at="store.latest?.updated_at"
    />

    <!-- 人工备注编辑区（不进入导出） -->
    <div class="card" v-if="daily" style="margin-top:14px">
      <div class="card-title">✏️ 人工备注（仅存本地 IndexedDB，按交易日独立保存）</div>
      <textarea v-model="note" class="note-input" style="margin-top:10px" placeholder="记录今日市场观察、个人判断、明日计划……"></textarea>
      <div style="margin-top:10px; display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
        <button class="btn secondary" @click="saveNote">保存备注</button>
        <button class="btn secondary" @click="clearNote">清空备注</button>
        <span class="muted" style="font-size:12px">{{ savedTip }}</span>
      </div>
    </div>

    <div v-else class="empty-box">
      🟡 该日期暂无数据（最后更新：{{ store.meta?.updated_at ?? '—' }}），已展示最近一个有效交易日
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDataStore } from '../stores/data'
import type { ObservationData } from '../types'
import { getObservationEdit, saveObservationEdit, type ObservationEdit } from '../lib/obsdb'
import ObservationExport from '../components/ObservationExport.vue'

const store = useDataStore()
const date = computed(() => store.currentDate)

const obs = ref<ObservationData | null>(null)
const edit = ref<ObservationEdit | null>(null)
const loading = ref(false)
const loadError = ref('')

const editing = ref(false)
const savedTip = ref('')
const exporting = ref(false)

// 可编辑文字字段（模块 → 编辑稿字段）
const editFields = [
  { key: 'market_summary', label: '03 · 今日市场概况', rows: 5 },
  { key: 'sector_text', label: '04 · 板块表现说明', rows: 3 },
  { key: 'announcement_text', label: '06 · 公司公告说明', rows: 3 },
] as const

// 可隐藏模块
const modules = [
  { id: 'metrics', label: '01 市场核心数据' },
  { id: 'indexes', label: '02 六大指数' },
  { id: 'summary', label: '03 今日市场概况' },
  { id: 'sector', label: '04 板块涨跌榜' },
  { id: 'mktcap', label: '05 市值分布' },
  { id: 'events', label: '06 重要公告' },
]

// 编辑稿本地草稿（编辑面板用）
const draft = ref<Record<string, string>>({})

async function load() {
  if (!date.value) return
  loading.value = true
  loadError.value = ''
  obs.value = null
  edit.value = null
  try {
    const res = await fetch(`/data/daily_observation/${date.value}.json`, { cache: 'no-cache' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json() as ObservationData
    obs.value = data
    edit.value = await getObservationEdit(date.value)
    // 初始化草稿（编辑稿优先，否则原始生成文字）
    const e = edit.value
    draft.value = {
      market_summary: e?.market_summary ?? data.market_summary,
      sector_text: e?.sector_text ?? '',
      announcement_text: e?.announcement_text ?? '',
    }
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : String(err)
    obs.value = null
  } finally {
    loading.value = false
  }
}

watch(date, load, { immediate: true })

// 隐藏模块状态（响应式，直接操作 edit.hidden）
function isHidden(id: string): boolean {
  return (edit.value?.hidden ?? []).includes(id)
}
function toggleHidden(id: string) {
  if (!edit.value) return
  const hidden = new Set(edit.value.hidden ?? [])
  if (hidden.has(id)) hidden.delete(id)
  else hidden.add(id)
  edit.value = { ...edit.value, hidden: [...hidden] }
}

async function save() {
  if (!date.value) return
  try {
    const hidden = edit.value?.hidden ?? []
    const e: ObservationEdit = {
      date: date.value,
      market_summary: draft.value.market_summary,
      sector_text: draft.value.sector_text,
      announcement_text: draft.value.announcement_text,
      hidden,
      updated_at: new Date().toISOString(),
    }
    await saveObservationEdit(e)
    edit.value = e
    savedTip.value = '✅ 已保存至本地（IndexedDB，不上服务器）'
    setTimeout(() => (savedTip.value = ''), 2500)
  } catch {
    savedTip.value = '⚠️ 本地存储不可用，编辑未保存'
  }
}

async function resetEdit() {
  if (!date.value) return
  if (!window.confirm('恢复为原始自动生成文字？（不会删除行情数据）')) return
  const hidden = edit.value?.hidden ?? []
  edit.value = {
    date: date.value, hidden,
    market_summary: '', sector_text: '', announcement_text: '',
    updated_at: new Date().toISOString(),
  }
  if (obs.value) {
    draft.value = {
      market_summary: obs.value.market_summary,
      sector_text: '',
      announcement_text: '',
    }
  }
  await saveObservationEdit(edit.value)
  savedTip.value = '✅ 已恢复原始文字'
  setTimeout(() => (savedTip.value = ''), 2500)
}

// 日期导航
const dates = computed(() => store.meta?.list ?? [])
function goDate(d: string) {
  store.gotoDate(d)
}
function prevDay() {
  const idx = dates.value.indexOf(date.value)
  if (idx > 0) goDate(dates.value[idx - 1])
}
function nextDay() {
  const idx = dates.value.indexOf(date.value)
  if (idx >= 0 && idx < dates.value.length - 1) goDate(dates.value[idx + 1])
}

async function exportPng() {
  const el = document.getElementById('obs-export')
  if (!el || !obs.value) return
  exporting.value = true
  try {
    const html2canvas = (await import('html2canvas')).default
    const canvas = await html2canvas(el, {
      backgroundColor: '#FFFFFF',
      scale: 1,
      useCORS: true,
      onclone: (clonedDoc) => {
        const root = clonedDoc.getElementById('obs-export')
        if (!root) return
        root.style.background = '#FFFFFF'
        root.querySelectorAll('*').forEach((n) => {
          const e = n as HTMLElement
          if (e.classList.contains('up')) { e.style.color = '#C0392B'; return }
          if (e.classList.contains('down')) { e.style.color = '#1E8449'; return }
        })
      }
    })
    const a = document.createElement('a')
    a.download = `每日市场观察_${obs.value.trade_date}.png`
    a.href = canvas.toDataURL('image/png')
    a.click()
    savedTip.value = '✅ PNG 已生成并开始下载'
    setTimeout(() => (savedTip.value = ''), 2500)
  } catch (e) {
    savedTip.value = '⚠️ 导出失败：' + (e instanceof Error ? e.message : String(e))
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <div class="page">
    <!-- 头部 -->
    <div class="obs-head">
      <div>
        <h1 class="page-title">📊 每日市场观察</h1>
        <p class="page-desc">基于真实行情的每日市场观察，可编辑、可导出高清 PNG 信息图</p>
      </div>
      <div class="obs-actions">
        <button class="btn" :disabled="!obs" @click="editing = !editing">{{ editing ? '收起编辑' : '编辑内容' }}</button>
        <button class="btn btn-primary" :disabled="!obs || exporting" @click="exportPng">{{ exporting ? '生成中…' : '导出 PNG' }}</button>
      </div>
    </div>

    <!-- 日期导航 -->
    <div class="obs-datebar">
      <button class="nav-btn" @click="prevDay">‹ 上一交易日</button>
      <span class="obs-date">{{ date ? store.formatDay(date) : '—' }}</span>
      <button class="nav-btn" @click="nextDay">下一交易日 ›</button>
    </div>

    <div v-if="savedTip" class="obs-tip">{{ savedTip }}</div>

    <!-- 加载 / 缺失 -->
    <div v-if="loading" class="obs-empty">加载中…</div>
    <div v-else-if="loadError" class="obs-empty">该日期尚未生成每日市场观察（{{ loadError }}），请选择有观察数据的交易日。</div>
    <div v-else-if="!obs" class="obs-empty">该日期尚未生成每日市场观察。</div>

    <template v-else>
      <!-- 编辑面板 -->
      <div v-if="editing" class="obs-editor">
        <div class="obs-editor-title">人工编辑（按交易日独立保存，不影响原始行情数据）</div>
        <div v-for="f in editFields" :key="f.key" class="obs-field">
          <label>{{ f.label }}</label>
          <textarea v-model="draft[f.key]" :rows="f.rows"></textarea>
        </div>
        <div class="obs-hidden">
          <span class="obs-hidden-label">显示模块：</span>
          <label v-for="m in modules" :key="m.id" class="obs-check">
            <input type="checkbox" :checked="!isHidden(m.id)" @change="toggleHidden(m.id)" />
            {{ m.label }}
          </label>
        </div>
        <div class="obs-editor-actions">
          <button class="btn btn-primary" @click="save">保存编辑</button>
          <button class="btn" @click="resetEdit">恢复原始文字</button>
        </div>
      </div>

      <!-- 报告预览（1200px 横向滚动容器，导出即抓取此 DOM） -->
      <div class="obs-preview">
        <ObservationExport :data="obs" :edit="edit" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.page { padding: 8px 4px 40px; }
.obs-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}
.obs-actions { display: flex; gap: 10px; }
.btn {
  padding: 8px 16px;
  border: 1px solid #d0d7de;
  background: #fff;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: #333;
}
.btn:hover { background: #f6f8fa; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: #1a1a1a; color: #fff; border-color: #1a1a1a; }
.btn-primary:hover { background: #333; }
.obs-datebar {
  display: flex;
  align-items: center;
  gap: 14px;
  margin: 16px 0;
}
.nav-btn {
  padding: 6px 12px;
  border: 1px solid #d0d7de;
  background: #fff;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #333;
}
.nav-btn:hover { background: #f6f8fa; }
.obs-date { font-size: 16px; font-weight: 700; }
.obs-tip {
  padding: 8px 14px;
  background: #eef7ee;
  border: 1px solid #cde5cd;
  color: #2e7d32;
  border-radius: 8px;
  font-size: 14px;
  margin-bottom: 12px;
}
.obs-empty {
  padding: 40px 20px;
  text-align: center;
  color: #888;
  background: #fafafa;
  border-radius: 12px;
  border: 1px dashed #ddd;
}
.obs-editor {
  background: #fafafa;
  border: 1px solid #eee;
  border-radius: 12px;
  padding: 18px;
  margin-bottom: 18px;
}
.obs-editor-title { font-size: 15px; font-weight: 700; margin-bottom: 14px; }
.obs-field { margin-bottom: 12px; }
.obs-field label { display: block; font-size: 13px; color: #666; margin-bottom: 5px; }
.obs-field textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 12px;
  border: 1px solid #d0d7de;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.6;
  resize: vertical;
  font-family: inherit;
}
.obs-hidden { margin: 14px 0; }
.obs-hidden-label { font-size: 13px; color: #666; margin-right: 8px; }
.obs-check { display: inline-flex; align-items: center; gap: 4px; margin-right: 14px; font-size: 13px; cursor: pointer; }
.obs-editor-actions { display: flex; gap: 10px; }
.obs-preview {
  overflow-x: auto;
  border: 1px solid #eee;
  border-radius: 12px;
  background: #fff;
}
</style>

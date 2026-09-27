<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useDataStore } from '../stores/data'
import { deleteLog, exportLogs, getAllLogs, saveLog, type TradeLog } from '../lib/notesdb'

const store = useDataStore()

const PRESET_TAGS = ['试错', '加仓', '减仓', '清仓', '开仓', '止损', '止盈', '观察', '教训', '纪律', '情绪化']
const TAG_COLORS: Record<string, string> = {
  加仓: 'var(--up)', 开仓: 'var(--up)', 止盈: 'var(--up)',
  减仓: 'var(--down)', 清仓: 'var(--down)', 止损: 'var(--down)',
  试错: 'var(--warn)', 教训: 'var(--warn)', 情绪化: 'var(--warn)',
  观察: 'var(--link)', 纪律: 'var(--link)'
}

const formDate = ref(store.currentDate || store.latest?.latest || '')
const formActions = ref('')
const formText = ref('')
const formTags = ref<string[]>([])
const tip = ref('')

const logs = ref<TradeLog[]>([])
const filterTag = ref('')
const filterDate = ref('')

const customTags = computed(() => [...new Set(logs.value.flatMap((l) => l.tags))].filter((t) => !PRESET_TAGS.includes(t)))

async function refresh() {
  try {
    logs.value = await getAllLogs()
  } catch {
    logs.value = []
  }
}
onMounted(refresh)

function toggleTag(t: string) {
  const i = formTags.value.indexOf(t)
  if (i >= 0) formTags.value.splice(i, 1)
  else formTags.value.push(t)
}

async function submit() {
  if (!/^\d{8}$/.test(formDate.value)) {
    tip.value = '⚠️ 请填写有效日期（YYYYMMDD）'
    return
  }
  const rec: TradeLog = {
    date: formDate.value,
    actions: formActions.value.trim(),
    tags: [...formTags.value],
    text: formText.value.trim(),
    updated_at: new Date().toISOString()
  }
  try {
    await saveLog(rec)
    tip.value = '✅ 已保存（IndexedDB，仅本地）'
    formActions.value = ''
    formText.value = ''
    formTags.value = []
    await refresh()
  } catch {
    tip.value = '⚠️ 本地存储不可用，未保存'
  }
  setTimeout(() => (tip.value = ''), 2500)
}

async function remove(date: string) {
  await deleteLog(date)
  await refresh()
}

function edit(l: TradeLog) {
  formDate.value = l.date
  formActions.value = l.actions
  formTags.value = [...l.tags]
  formText.value = l.text
}

const filtered = computed(() =>
  logs.value.filter((l) =>
    (!filterTag.value || l.tags.includes(filterTag.value)) &&
    (!filterDate.value || l.date.startsWith(filterDate.value.replace(/-/g, ''))))
)

function fmtDay(d: string): string {
  return /^\d{8}$/.test(d) ? `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}` : d
}
</script>

<template>
  <div class="page">
    <h1 class="page-title">✏️ 交易日志</h1>
    <p class="page-desc">IndexedDB 本地存储，不上服务器 · 支持标签筛选与 JSON 导出备份</p>

    <div class="card-grid cols-2">
      <div class="card">
        <div class="card-title">📝 新增 / 编辑记录</div>
        <div style="margin-top:10px; display:flex; flex-direction:column; gap:10px;">
          <input v-model="formDate" class="note-input" style="min-height:0" placeholder="交易日 YYYYMMDD" />
          <textarea v-model="formActions" class="note-input" style="min-height:60px" placeholder="操作记录（如：减仓 XXX 1/2，理由…）"></textarea>
          <div style="display:flex; flex-wrap:wrap; gap:6px;">
            <span
              v-for="t in [...PRESET_TAGS, ...customTags]" :key="t"
              :style="{
                cursor: 'pointer', fontSize: '12px', padding: '2px 10px',
                borderRadius: '999px', border: '1px solid var(--border)',
                background: formTags.includes(t) ? 'rgba(183,65,14,0.35)' : 'transparent',
                color: TAG_COLORS[t] ?? 'var(--text)'
              }"
              @click="toggleTag(t)"
            >{{ t }}</span>
          </div>
          <textarea v-model="formText" class="note-input" style="min-height:60px" placeholder="备注 / 复盘感想"></textarea>
          <div style="display:flex; gap:10px; align-items:center;">
            <button class="btn" @click="submit">保存</button>
            <button class="btn secondary" @click="exportLogs">⬇️ 导出 JSON 备份</button>
            <span class="muted" style="font-size:12px">{{ tip }}</span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">📚 历史记录（{{ filtered.length }}）</div>
        <div style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">
          <select v-model="filterTag" class="note-input" style="min-height:0; width:130px">
            <option value="">全部标签</option>
            <option v-for="t in [...PRESET_TAGS, ...customTags]" :key="t" :value="t">{{ t }}</option>
          </select>
          <input v-model="filterDate" class="note-input" style="min-height:0; width:130px" placeholder="按月份筛选 202609" />
        </div>
        <div style="margin-top:10px; display:flex; flex-direction:column; gap:10px; max-height:480px; overflow-y:auto;">
          <div v-for="l in filtered" :key="l.date" style="border:1px solid var(--border); border-radius:8px; padding:10px 12px;">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
              <strong class="num">{{ fmtDay(l.date) }}</strong>
              <span style="display:flex; gap:6px;">
                <button class="btn secondary" style="padding:2px 10px; font-size:12px" @click="edit(l)">编辑</button>
                <button class="btn secondary" style="padding:2px 10px; font-size:12px" @click="remove(l.date)">删除</button>
              </span>
            </div>
            <div v-if="l.tags.length" style="margin-top:6px; display:flex; gap:6px; flex-wrap:wrap;">
              <span v-for="t in l.tags" :key="t" class="num"
                :style="{ fontSize: '11px', padding: '1px 8px', borderRadius: '999px', border: '1px solid var(--border)', color: TAG_COLORS[t] ?? 'var(--text)' }">{{ t }}</span>
            </div>
            <div v-if="l.actions" style="margin-top:6px; font-size:13px; white-space:pre-wrap">{{ l.actions }}</div>
            <div v-if="l.text" class="muted" style="font-size:12px; margin-top:4px; white-space:pre-wrap">{{ l.text }}</div>
          </div>
          <div v-if="!filtered.length" class="empty-box">暂无记录，写一条吧</div>
        </div>
      </div>
    </div>
  </div>
</template>

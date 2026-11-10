<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { conclude, type BucketPt } from '../rules/engine'
import { getNote } from '../lib/notesdb'
import ReportExport from '../components/ReportExport.vue'
import type { DailyData } from '../types'

const route = useRoute()
const daily = ref<DailyData | null>(null)
const note = ref('')
const updatedAt = ref('')
const bucketPts = ref<BucketPt[]>([])
const error = ref('')

onMounted(async () => {
  try {
    const date = route.params.date as string
    const d = (await (await fetch(`/data/daily/${date}.json`)).json()) as DailyData
    daily.value = d
    try {
      const l = await (await fetch('/data/latest.json')).json()
      updatedAt.value = l.updated_at ?? ''
    } catch { /* 忽略 */ }
    try {
      const b = await (await fetch('/data/series/mktcap_buckets.json')).json()
      bucketPts.value = b.points ?? []
    } catch { /* 忽略 */ }
    try {
      note.value = await getNote(date)
    } catch { /* IndexedDB 不可用 */ }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
})

const conclusion = computed(() => (daily.value ? conclude(daily.value, bucketPts.value) : null))
</script>

<template>
  <div v-if="error" style="padding: 40px; font-size: 18px; color: #C0392B;">导出失败：{{ error }}</div>
  <div v-else-if="daily && conclusion" style="background: #ffffff; margin: 0; padding: 0;">
    <ReportExport :daily="daily" :conclusion="conclusion" :note="note" :updated-at="updatedAt" />
  </div>
  <div v-else style="padding: 40px; font-size: 18px;">加载中…</div>
</template>

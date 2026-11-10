<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import type { ObservationData } from '../types'
import { getObservationEdit, type ObservationEdit } from '../lib/obsdb'
import ObservationExport from '../components/ObservationExport.vue'

const route = useRoute()
const date = ref('')
const obs = ref<ObservationData | null>(null)
const edit = ref<ObservationEdit | null>(null)

watch(
  () => route.params.date,
  async (d) => {
    const dstr = typeof d === 'string' ? d : ''
    date.value = dstr
    if (!/^\d{8}$/.test(dstr)) return
    try {
      const res = await fetch(`/data/daily_observation/${dstr}.json`, { cache: 'no-cache' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      obs.value = await res.json()
      edit.value = await getObservationEdit(dstr)
    } catch {
      obs.value = null
    }
  },
  { immediate: true }
)
</script>

<template>
  <div class="bare-wrap">
    <ObservationExport v-if="obs" :data="obs" :edit="edit" />
    <div v-else class="bare-empty">该日期尚未生成每日市场观察</div>
  </div>
</template>

<style scoped>
.bare-wrap { background: #ffffff; min-height: 100vh; padding: 0; }
.bare-empty { padding: 60px; text-align: center; color: #888; }
</style>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import echarts, { miniLineOption } from '@/lib/echarts'

const props = defineProps<{
  points: { label: string; value: number }[]
  color?: string
  /** N<30 时由父组件直接不渲染本组件（不画折线） */
}>()

const el = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

function render() {
  if (!el.value) return
  if (!chart) chart = echarts.init(el.value)
  chart.setOption(miniLineOption(props.points, props.color))
  chart.resize()
}

function onResize() { chart?.resize() }

onMounted(() => {
  render()
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
  chart = null
})
watch(() => props.points, render, { deep: true })
</script>

<template>
  <div ref="el" class="mini-chart"></div>
</template>

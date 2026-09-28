<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import echarts from '@/lib/echarts'
import type { EChartsOption } from 'echarts'

const props = defineProps<{ option: EChartsOption; height?: string }>()

const el = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

function render() {
  if (!el.value) return
  if (!chart) chart = echarts.init(el.value)
  chart.setOption(props.option)
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
watch(() => props.option, render, { deep: true })
</script>

<template>
  <div ref="el" :style="{ width: '100%', height: height ?? '300px' }"></div>
</template>

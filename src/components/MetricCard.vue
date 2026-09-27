<script setup lang="ts">
defineProps<{
  icon: string
  title: string
  desc?: string
  value: string
  unit?: string
  sub?: string
  subClass?: string
  sampleN?: number | null
}>()
</script>

<template>
  <div class="card">
    <div class="card-title">{{ icon }} {{ title }}</div>
    <div v-if="desc" class="card-desc">{{ desc }}</div>
    <div class="card-value num">{{ value }}<span v-if="unit" class="unit">{{ unit }}</span></div>
    <div v-if="sub" class="card-sub num" :class="subClass" v-html="sub"></div>
    <span v-if="sampleN != null && sampleN >= 30" class="card-sample num">样本N={{ sampleN }}</span>
    <span v-else-if="sampleN != null && sampleN < 30" class="card-insufficient">样本不足</span>
  </div>
</template>

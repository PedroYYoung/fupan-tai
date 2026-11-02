<script setup lang="ts">
import { computed } from 'vue'
import { useDataStore } from '../stores/data'

/**
 * 全市场快照不可用提示。
 *
 * 背景：实时 spot 接口不支持历史日期，历史上用 --date 重跑过去交易日时，
 * 会把当前会话行情写进历史快照。修复后这类数据不再伪造，直接置空。
 * 本组件把这些「不可用」明确告诉用户，避免把「—」误解成「0」。
 */
const store = useDataStore()
const quality = computed(() => store.daily?.data_quality)
const unavailable = computed(() => quality.value?.spot_derived === 'unavailable')
const note = computed(
  () =>
    quality.value?.note ||
    '该交易日的全市场个股快照在现有数据源中无可靠历史版本，相关字段已置空（不做估算）'
)
</script>

<template>
  <div v-if="unavailable" class="spot-notice">
    <span class="ico">⚠️</span>
    <div>
      <b>该日全市场快照不可用</b>
      <span class="muted">{{ note }}</span>
    </div>
  </div>
</template>

<style scoped>
.spot-notice {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  margin-top: 12px;
  padding: 10px 14px;
  border: 1px dashed var(--warn);
  border-radius: var(--radius);
  background: var(--card);
  color: var(--text);
  font-size: 13px;
  line-height: 1.6;
}
.spot-notice .ico {
  flex: 0 0 auto;
}
.spot-notice .muted {
  color: var(--muted);
  margin-left: 6px;
}
</style>

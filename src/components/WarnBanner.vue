<script setup lang="ts">
import { useDataStore } from '../stores/data'
const store = useDataStore()
</script>

<template>
  <div v-if="store.warnMsg" class="warn-banner">
    <span>🟡 {{ store.warnMsg }}</span>
    <button aria-label="关闭提示" @click="store.warnMsg = ''">✕</button>
  </div>
</template>

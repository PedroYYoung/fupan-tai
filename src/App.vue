<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import Sidebar from './components/Sidebar.vue'
import WarnBanner from './components/WarnBanner.vue'
import GateShell from './GateShell.vue'
import { useDataStore } from './stores/data'

const route = useRoute()
const store = useDataStore()
const sidebarOpen = ref(false)
watch(() => route.fullPath, () => { sidebarOpen.value = false })
</script>

<template>
  <GateShell>
    <div class="app-layout">
      <Sidebar :open="sidebarOpen" @close="sidebarOpen = false" />
      <div class="overlay" :class="{ show: sidebarOpen }" @click="sidebarOpen = false"></div>
      <div class="main-area">
        <div class="topbar">
          <button class="hamburger" aria-label="打开菜单" @click="sidebarOpen = !sidebarOpen">☰</button>
          <strong>复盘台</strong>
        </div>
        <WarnBanner />
        <router-view v-if="!store.loading" />
        <div v-else class="loading-box">加载数据中…</div>
      </div>
    </div>
  </GateShell>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'

export interface NavEntry {
  path: string
  icon: string
  label: string
  enabled: boolean
  batch?: number
}

// 全部 11 个模块入口，均已交付
const nav: NavEntry[] = [
  { path: '/', icon: '🏠', label: '今日速览', enabled: true },
  { path: '/money', icon: '💰', label: '资金面', enabled: true },
  { path: '/index', icon: '📊', label: '指数成交', enabled: true },
  { path: '/widebase', icon: '🧩', label: '宽基矩阵', enabled: true },
  { path: '/industry', icon: '🏭', label: '行业', enabled: true },
  { path: '/concentration', icon: '🎯', label: '个股集中度', enabled: true },
  { path: '/liquidity', icon: '📐', label: '流动性结构', enabled: true },
  { path: '/emotion', icon: '🔥', label: '情绪', enabled: true },
  { path: '/report', icon: '📋', label: '复盘报告', enabled: true },
  { path: '/calendar', icon: '🔍', label: '日历回溯', enabled: true },
  { path: '/status', icon: '🟢', label: '数据状态', enabled: true },
  { path: '/notes', icon: '✏️', label: '交易日志', enabled: true }
]

const route = useRoute()

defineProps<{ open: boolean }>()
defineEmits<{ (e: 'close'): void }>()
</script>

<template>
  <aside class="sidebar" :class="{ open }">
    <div class="sidebar-brand">复盘台</div>
    <nav class="sidebar-nav">
      <template v-for="item in nav" :key="item.path">
        <router-link v-if="item.enabled" :to="item.path" class="nav-item" active-class="active">
          <span>{{ item.icon }}</span><span>{{ item.label }}</span>
        </router-link>
        <div v-else class="nav-item disabled" :title="`第${item.batch}批交付`">
          <span>{{ item.icon }}</span><span>{{ item.label }}</span>
          <span class="nav-badge">第{{ item.batch }}批</span>
        </div>
      </template>
    </nav>
    <div class="sidebar-foot">数据每日收盘后更新<br />本地 / CI 双模式构建</div>
  </aside>
</template>

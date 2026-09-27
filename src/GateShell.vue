<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { gateEnabled, isUnlocked, unlock } from './gate'
import { useDataStore } from './stores/data'

const route = useRoute()
const needGate = gateEnabled() && !isUnlocked()
const passwd = ref('')
const err = ref('')
const busy = ref(false)

async function tryUnlock() {
  if (busy.value) return
  busy.value = true
  err.value = ''
  const ok = await unlock(passwd.value)
  busy.value = false
  if (ok) {
    location.reload() // 解锁后重新渲染，确保 DOM 中不含任何未授权数据
  } else {
    err.value = '口令不正确'
  }
}

if (!needGate) {
  const store = useDataStore()
  onMounted(() => store.boot())
  // 日历回溯：URL ?date= 变化时重新加载当日数据
  watch(() => route.query.date, () => store.boot())
}
</script>

<template>
  <template v-if="!needGate">
    <slot />
  </template>
  <div v-else class="gate-mask">
    <div class="gate-panel">
      <div class="logo">复盘台</div>
      <div class="muted" style="font-size: 13px">本站受口令保护，请输入访问口令</div>
      <input
        v-model="passwd"
        type="password"
        placeholder="访问口令"
        autocomplete="current-password"
        @keyup.enter="tryUnlock"
      />
      <button :disabled="busy" @click="tryUnlock">{{ busy ? '验证中…' : '进入' }}</button>
      <div class="gate-err">{{ err }}</div>
    </div>
  </div>
</template>

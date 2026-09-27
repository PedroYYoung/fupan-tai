<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDataStore } from '../stores/data'

const store = useDataStore()

const cur = computed(() => store.currentDate || store.latest?.latest || '')
const viewYM = ref(cur.value.slice(0, 6))

function shiftMonth(delta: number) {
  const y = Number(viewYM.value.slice(0, 4))
  const m = Number(viewYM.value.slice(4, 6))
  const d = new Date(y, m - 1 + delta, 1)
  viewYM.value = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}`
}

const monthLabel = computed(() => `${viewYM.value.slice(0, 4)} 年 ${Number(viewYM.value.slice(4, 6))} 月`)

const tradeSet = computed(() => new Set(store.meta?.list ?? []))

interface Cell {
  day: number
  date: string | null
  isTrade: boolean
  hasData: boolean
  isCurrent: boolean
  isLatest: boolean
}

const cells = computed<Cell[]>((): Cell[] => {
  const y = Number(viewYM.value.slice(0, 4))
  const m = Number(viewYM.value.slice(4, 6))
  const first = new Date(y, m - 1, 1)
  const daysInMonth = new Date(y, m, 0).getDate()
  const offset = (first.getDay() + 6) % 7 // 周一起始
  const out: Cell[] = []
  for (let i = 0; i < offset; i++) out.push({ day: 0, date: null, isTrade: false, hasData: false, isCurrent: false, isLatest: false })
  for (let d = 1; d <= daysInMonth; d++) {
    const date = `${y}${String(m).padStart(2, '0')}${String(d).padStart(2, '0')}`
    const isTrade = tradeSet.value.has(date)
    out.push({
      day: d, date,
      isTrade,
      hasData: isTrade && date <= (store.latest?.latest ?? ''),
      isCurrent: date === cur.value,
      isLatest: date === (store.latest?.latest ?? '')
    })
  }
  return out
})

function pick(c: Cell) {
  if (c.hasData && c.date) store.gotoDate(c.date)
}
</script>

<template>
  <div class="page">
    <h1 class="page-title">🔍 日历回溯</h1>
    <p class="page-desc">仅交易日可选 · 选中后全局切换日期，URL 同步 ?date= 可直接分享</p>

    <div class="card" style="max-width: 420px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <button class="btn secondary" @click="shiftMonth(-1)">← 上月</button>
        <strong class="num">{{ monthLabel }}</strong>
        <button class="btn secondary" @click="shiftMonth(1)">下月 →</button>
      </div>
      <div style="display:grid; grid-template-columns:repeat(7,1fr); gap:4px; text-align:center;">
        <span v-for="w in ['一','二','三','四','五','六','日']" :key="w" class="muted" style="font-size:12px">{{ w }}</span>
        <template v-for="(c, i) in cells" :key="i">
          <div
            v-if="c.day"
            class="num"
            :style="{
              padding: '6px 0',
              borderRadius: '6px',
              fontSize: '13px',
              cursor: c.hasData ? 'pointer' : 'default',
              opacity: c.isTrade ? 1 : 0.35,
              background: c.isCurrent ? '#B7410E' : c.isLatest ? 'rgba(183,65,14,0.35)' : c.hasData ? 'rgba(88,166,255,0.10)' : 'transparent',
              color: c.isCurrent ? '#fff' : c.hasData ? 'var(--text)' : 'var(--muted)',
              border: c.hasData ? '1px solid var(--border)' : '1px solid transparent'
            }"
            :title="c.hasData ? `查看 ${c.date}` : c.isTrade ? '交易日（早于数据起点，暂无数据）' : '非交易日'"
            @click="pick(c)"
          >{{ c.day }}</div>
          <span v-else></span>
        </template>
      </div>
      <div class="muted" style="font-size:12px; margin-top:10px">
        <span style="display:inline-block;width:10px;height:10px;background:#B7410E;border-radius:2px;margin-right:4px"></span>当前查看
        <span style="display:inline-block;width:10px;height:10px;background:rgba(183,65,14,0.5);border-radius:2px;margin:0 4px 0 10px"></span>最新交易日
        <span style="display:inline-block;width:10px;height:10px;background:rgba(88,166,255,0.25);border:1px solid var(--border);border-radius:2px;margin:0 4px 0 10px"></span>可回溯
      </div>
    </div>

    <p class="muted" style="margin-top:14px; font-size:12px">
      当前展示：<strong class="num">{{ store.formatDay(cur) }}</strong>
      <router-link to="/" style="margin-left:10px">→ 回到今日速览</router-link>
    </p>
  </div>
</template>

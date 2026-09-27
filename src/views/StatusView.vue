<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useDataStore } from '../stores/data'

const store = useDataStore()
const lastError = ref<string>('读取中…')

onMounted(async () => {
  try {
    const res = await fetch('/data/meta/last_error.log', { cache: 'no-cache' })
    lastError.value = res.ok ? (await res.text()).trim().split('\n').slice(-5).join('\n') : '✅ 无失败记录'
  } catch {
    lastError.value = '✅ 无失败记录'
  }
})

const nAll = computed(() => store.allSampleN())
const nYear = computed(() => store.yearSampleN())
</script>

<template>
  <div class="page">
    <h1 class="page-title">🟢 数据状态</h1>
    <p class="page-desc">数据更新链路自检：最后更新时间 / 数据源版本 / 样本量 / 失败记录</p>

    <div class="card-grid cols-2">
      <div class="card">
        <div class="card-title">🕒 更新信息</div>
        <div class="table-wrap">
          <table class="data">
            <tbody>
              <tr><td>最新有效交易日</td><td class="num">{{ store.latest?.latest ?? '—' }}</td></tr>
              <tr><td>最后更新时间</td><td class="num">{{ store.meta?.updated_at ?? '—' }}</td></tr>
              <tr><td>下次计划更新</td><td>本地 18:40 / CI 19:30（北京时间，收盘后）</td></tr>
              <tr><td>当前展示日期</td><td class="num">{{ store.formatDay(store.currentDate) }}</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <div class="card-title">📦 数据源版本</div>
        <div class="table-wrap">
          <table class="data">
            <tbody>
              <tr v-for="(v, k) in store.meta?.source_versions ?? {}" :key="k">
                <td>{{ k }}</td><td class="num">{{ v }}</td>
              </tr>
              <tr v-if="!store.meta"><td class="muted">版本信息缺失</td><td>—</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <div class="card-title">📐 各指标样本量 N</div>
        <div class="table-wrap">
          <table class="data">
            <tbody>
              <tr><td>交易日历（全历史）</td><td class="num">N={{ nAll }}</td></tr>
              <tr><td>年内窗口（{{ store.currentDate.slice(0, 4) }}）</td><td class="num">N={{ nYear }}</td></tr>
              <tr><td>近一年窗口</td><td class="num">N={{ Math.min(nAll, 244) }}</td></tr>
              <tr><td>个股快照覆盖</td><td class="num">N={{ store.daily?.overview.stock_count ?? '—' }}</td></tr>
            </tbody>
          </table>
        </div>
        <div class="card-desc" style="margin-top:6px">N&lt;30 的指标在前端显示「样本不足」且不绘制折线</div>
      </div>

      <div class="card">
        <div class="card-title">⚠️ 最近失败记录（last_error.log）</div>
        <pre style="white-space:pre-wrap; font-size:12px; color:var(--muted); margin-top:8px">{{ lastError }}</pre>
      </div>
    </div>

    <p class="muted" style="margin-top:14px; font-size:12px">
      已知限制：AKShare 为爬虫源，源站改版可能导致个别接口失效；失效模块显示兜底文案，不影响其他模块。历史回补仅在本地执行，CI 只做每日增量。
    </p>
  </div>
</template>

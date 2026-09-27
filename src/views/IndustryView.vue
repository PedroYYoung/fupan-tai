<script setup lang="ts">
import { computed } from 'vue'
import { useDataStore } from '../stores/data'
import type { IndustryRow } from '../types'

const store = useDataStore()
const daily = computed(() => store.daily)
const industry = computed(() => daily.value?.industry)

function cls(v: number): string {
  return v >= 0 ? 'up' : 'down'
}
function fmt(n: number | null | undefined, digits = 1): string {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}
function sign(v: number): string {
  return v > 0 ? '+' : ''
}
</script>

<template>
  <div class="page">
    <h1 class="page-title">🏭 行业 · <span class="num">{{ daily ? store.formatDay(daily.trade_date) : '—' }}</span></h1>
    <p class="page-desc">东财行业板块当日涨跌 TOP10 · 成交额与占两市比</p>

    <template v-if="industry">
      <div class="card-grid cols-2">
        <div class="card">
          <div class="card-title up">📈 上涨 TOP10</div>
          <div class="table-wrap" style="margin-top:8px">
            <table class="data">
              <thead><tr><th>行业</th><th>涨跌幅</th><th>成交额(亿)</th><th>占两市比</th></tr></thead>
              <tbody>
                <tr v-for="r in industry.top10_up" :key="r.name">
                  <td>{{ r.name }}</td>
                  <td class="num" :class="cls(r.change)">{{ sign(r.change) }}{{ fmt(r.change, 2) }}%</td>
                  <td class="num">{{ fmt(r.amount) }}</td>
                  <td class="num muted">{{ fmt(r.ratio, 2) }}%</td>
                </tr>
                <tr v-if="!industry.top10_up.length"><td colspan="4" class="muted">无数据</td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="card">
          <div class="card-title down">📉 下跌 TOP10</div>
          <div class="table-wrap" style="margin-top:8px">
            <table class="data">
              <thead><tr><th>行业</th><th>涨跌幅</th><th>成交额(亿)</th><th>占两市比</th></tr></thead>
              <tbody>
                <tr v-for="r in industry.top10_down" :key="r.name">
                  <td>{{ r.name }}</td>
                  <td class="num" :class="cls(r.change)">{{ sign(r.change) }}{{ fmt(r.change, 2) }}%</td>
                  <td class="num">{{ fmt(r.amount) }}</td>
                  <td class="num muted">{{ fmt(r.ratio, 2) }}%</td>
                </tr>
                <tr v-if="!industry.top10_down.length"><td colspan="4" class="muted">无数据</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="card" style="margin-top:14px">
        <div class="card-title">📖 口径说明</div>
        <ul class="muted" style="font-size:12px; margin:8px 0 0 18px; line-height:1.9">
          <li>当日数据口径：<strong>东财行业板块</strong>（stock_board_industry_name_em），成交额单位亿元，占两市比 = 板块成交额 / 两市总成交额。</li>
          <li>历史序列由<strong>中证/申万指数体系</strong>回填；严格申万二级成分映射需要「东财行业 ↔ 申万二级」对齐表 CSV（V2 扩展点），
              提供 CSV 后运行 <code>python scripts/build.py --industry-backfill 对齐表.csv</code> 即可回填近一年。</li>
          <li>板块成交额与个股成交额加总存在口径差异（板块含成分调整时滞），仅作结构参考。</li>
        </ul>
      </div>
    </template>
    <div v-else class="empty-box">
      🟡 该日期暂无数据（最后更新：{{ store.meta?.updated_at ?? '—' }}），已展示最近一个有效交易日
    </div>
  </div>
</template>

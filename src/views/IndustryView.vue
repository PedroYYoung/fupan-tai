<script setup lang="ts">
import { computed } from 'vue'
import { useDataStore } from '../stores/data'
import type { IndustryRow } from '../types'

const store = useDataStore()
const daily = computed(() => store.daily)
const industry = computed(() => daily.value?.industry)
const weekRank = computed(() => daily.value?.industry_week_rank)

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
function rankCls(v: number): string {
  return v > 0 ? 'up' : v < 0 ? 'down' : 'muted'
}
</script>

<template>
  <div class="page">
    <h1 class="page-title">🏭 行业 · <span class="num">{{ daily ? store.formatDay(daily.trade_date) : '—' }}</span></h1>
    <p class="page-desc">行业板块当日涨跌 TOP10 · 成交额与占两市比（东财 → 同花顺备用源）</p>
    <p v-if="industry?.note" class="muted" style="font-size:12px; margin-top:2px">
      {{ industry.note }}<template v-if="industry?.as_of"> · 数据日期 {{ store.formatDay(industry.as_of) }}</template>
    </p>

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

      <div v-if="weekRank" class="card-grid cols-2" style="margin-top:14px">
        <div class="card">
          <div class="card-title up">📈 本周涨幅 TOP5</div>
          <div class="table-wrap" style="margin-top:8px">
            <table class="data">
              <thead><tr><th>行业</th><th>本周涨幅</th></tr></thead>
              <tbody>
                <tr v-for="r in weekRank.top5" :key="r.name">
                  <td>{{ r.name }}</td>
                  <td class="num" :class="rankCls(r.change)">{{ sign(r.change) }}{{ fmt(r.change, 2) }}%</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="card">
          <div class="card-title down">📉 本周跌幅 TOP5</div>
          <div class="table-wrap" style="margin-top:8px">
            <table class="data">
              <thead><tr><th>行业</th><th>本周跌幅</th></tr></thead>
              <tbody>
                <tr v-for="r in weekRank.bottom5" :key="r.name">
                  <td>{{ r.name }}</td>
                  <td class="num" :class="rankCls(r.change)">{{ sign(r.change) }}{{ fmt(r.change, 2) }}%</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="card" style="margin-top:14px">
        <div class="card-title">📖 口径说明</div>
        <ul class="muted" style="font-size:12px; margin:8px 0 0 18px; line-height:1.9">
          <li>当日数据口径：<strong>东财行业板块</strong>（stock_board_industry_name_em）为主源，失败时降级<strong>同花顺行业板块</strong>（stock_board_industry_summary_ths，独立通道）；成交额单位亿元，占两市比 = 板块成交额 / 两市总成交额。</li>
          <li>两源均失败时继承上一交易日有效数据，并在此页顶部标注真实数据日期，不把旧数据伪装成当日。</li>
          <li>板块成交额与个股成交额加总存在口径差异（板块含成分调整时滞），仅作结构参考。</li>
        </ul>
      </div>
    </template>
    <div v-else class="empty-box">
      🟡 该日期暂无数据（最后更新：{{ store.meta?.updated_at ?? '—' }}），已展示最近一个有效交易日
    </div>
  </div>
</template>

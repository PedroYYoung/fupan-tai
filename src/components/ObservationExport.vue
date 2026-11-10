<script setup lang="ts">
import { computed } from 'vue'
import type { ObservationData, SectorTopRow } from '../types'
import type { ObservationEdit } from '../lib/obsdb'

const props = defineProps<{
  data: ObservationData
  edit?: ObservationEdit | null
}>()

const d = computed(() => props.data)

// 隐藏模块 id 集合（01 metrics / 02 indexes / 03 summary / 04 sector / 05 mktcap / 06 events）
const hiddenSet = computed(() => new Set(props.edit?.hidden ?? []))
function visible(id: string): boolean {
  return !hiddenSet.value.has(id)
}

const t = computed(() => ({
  market_summary: props.edit?.market_summary?.trim() ? props.edit.market_summary : d.value.market_summary,
  sector_text: props.edit?.sector_text?.trim() ? props.edit.sector_text : '',
  announcement_text: props.edit?.announcement_text?.trim() ? props.edit.announcement_text : '',
}))

// ---- 格式化 ----
function fmt(n: number | null | undefined, digits = 0): string {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}
function signed(n: number | null | undefined, digits = 1): string {
  if (n == null) return '—'
  const s = n.toFixed(digits)
  return n > 0 ? `+${s}` : s
}
function signedPoints(n: number | null | undefined): string {
  if (n == null) return '—'
  return n > 0 ? `+${n.toFixed(2)}` : n.toFixed(2)
}
function cls(n: number | null | undefined): string {
  if (n == null) return 'flat'
  return n > 0 ? 'up' : n < 0 ? 'down' : 'flat'
}
function fmtDate(date: string): string {
  return `${date.slice(0, 4)}年${date.slice(4, 6)}月${date.slice(6, 8)}日`
}

const metrics = computed(() => d.value.market_metrics)
const indexes = computed(() => d.value.indexes)
const sectorTop5 = computed(() => d.value.sector_top5)
const mktcapDist = computed(() => d.value.mktcap_dist)
const groups = computed(() => d.value.risk_events.groups ?? { buyback: [], risk: [] })

// ---- 板块 Top5 展示 ----
function sectorUp(rows: SectorTopRow[] | null | undefined): SectorTopRow[] {
  return rows ?? []
}
function sectorDown(rows: SectorTopRow[] | null | undefined): SectorTopRow[] {
  return rows ?? []
}

// ---- 事件类别中性标签 ----
const CAT_COLOR: Record<string, string> = {
  '经营进展': 'c-op', '业绩信息': 'c-perf', '股东行为': 'c-sh', '资本运作': 'c-cap',
  '监管事项': 'c-reg', '法律事项': 'c-law', '行业政策': 'c-pol', '宏观事件': 'c-mac', '其他信息': 'c-other',
}
function catCls(cat: string): string {
  return CAT_COLOR[cat] ?? 'c-other'
}

// ---- 市值饼图（SVG 扇形）----
const PIE_COLORS = ['#2C5F8A', '#4A90B8', '#6FB1D8', '#98CCE8', '#C0E0F0', '#8AA9C4']

function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const a = (angleDeg - 90) * Math.PI / 180
  return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) }
}
function slicePath(cx: number, cy: number, r: number, startDeg: number, endDeg: number): string {
  if (endDeg - startDeg >= 359.9) {
    return `M ${cx} ${cy - r} A ${r} ${r} 0 1 1 ${cx} ${cy + r} A ${r} ${r} 0 1 1 ${cx} ${cy - r} Z`
  }
  const s = polar(cx, cy, r, endDeg)
  const e = polar(cx, cy, r, startDeg)
  const largeArc = endDeg - startDeg > 180 ? 1 : 0
  return `M ${cx} ${cy} L ${s.x.toFixed(2)} ${s.y.toFixed(2)} A ${r} ${r} 0 ${largeArc} 1 ${e.x.toFixed(2)} ${e.y.toFixed(2)} Z`
}

const pieSlices = computed(() => {
  const buckets = mktcapDist.value.buckets ?? []
  const total = buckets.reduce((s, b) => s + (b.count || 0), 0)
  if (!total) return []
  let acc = 0
  return buckets.map((b, i) => {
    const startDeg = acc / total * 360
    acc += b.count
    const endDeg = acc / total * 360
    return { ...b, startDeg, endDeg, color: PIE_COLORS[i % PIE_COLORS.length] }
  })
})
</script>

<template>
  <div id="obs-export" class="obs-export">
    <!-- 头部 -->
    <header class="hd">
      <div class="hd-brand">每日市场观察 · Daily Market Observation</div>
      <h1 class="hd-title">A股市场 · {{ fmtDate(data.trade_date) }}</h1>
      <div class="hd-meta">
        <span>交易日期 {{ data.trade_date }}</span>
        <span class="sep">｜</span>
        <span>生成时间 {{ (data.generated_at || '').slice(0, 16).replace('T', ' ') }}</span>
        <span class="sep">｜</span>
        <span>统计口径：较上一有效交易日</span>
        <span class="sep">｜</span>
        <span>涨红跌绿</span>
      </div>
    </header>

    <!-- 01 市场核心数据 -->
    <section v-if="visible('metrics')" class="sec">
      <div class="sec-h"><span class="sec-no">01</span><h2>市场核心数据</h2><span class="sec-sub">较上一有效交易日变化</span></div>
      <div class="metric-grid">
        <div class="metric">
          <div class="metric-label">两市成交额</div>
          <div class="metric-value" :class="cls(metrics.total_amount.change)">{{ fmt(metrics.total_amount.value, 0) }}<small> 亿</small></div>
          <div class="metric-delta" :class="cls(metrics.total_amount.change)">
            <template v-if="metrics.total_amount.change != null">
              较昨日{{ metrics.total_amount.change > 0 ? '+' : '' }}{{ fmt(metrics.total_amount.change, 0) }} 亿
              <span v-if="metrics.total_amount.change_pct != null">（{{ signed(metrics.total_amount.change_pct, 1) }}%）</span>
            </template>
            <template v-else>暂无可比较数据</template>
          </div>
        </div>
        <div class="metric">
          <div class="metric-label">两融余额</div>
          <div class="metric-value flat">{{ fmt(metrics.margin_balance.value, 0) }}<small> 亿</small></div>
          <div class="metric-delta" :class="cls(metrics.margin_balance.change)">
            <template v-if="metrics.margin_balance.change != null">
              较 {{ metrics.margin_balance.prev_stat_date }} {{ metrics.margin_balance.change > 0 ? '+' : '' }}{{ fmt(metrics.margin_balance.change, 0) }} 亿
            </template>
            <template v-else>暂无可比较数据</template>
          </div>
          <div class="metric-stat">统计日 {{ metrics.margin_balance.stat_date ?? '—' }}</div>
        </div>
        <div class="metric">
          <div class="metric-label">涨停家数</div>
          <div class="metric-value up">{{ fmt(metrics.limit_up.value, 0) }}<small> 家</small></div>
          <div class="metric-delta" :class="cls(metrics.limit_up.change)">{{ metrics.limit_up.change != null ? '较昨日' + signed(metrics.limit_up.change, 0) + ' 家' : '暂无可比较数据' }}</div>
        </div>
        <div class="metric">
          <div class="metric-label">跌停家数</div>
          <div class="metric-value down">{{ fmt(metrics.limit_down.value, 0) }}<small> 家</small></div>
          <div class="metric-delta" :class="cls(metrics.limit_down.change)">{{ metrics.limit_down.change != null ? '较昨日' + signed(metrics.limit_down.change, 0) + ' 家' : '暂无可比较数据' }}</div>
        </div>
        <div class="metric">
          <div class="metric-label">成交额≥10亿元家数</div>
          <div class="metric-value flat">{{ fmt(metrics.over_10e_count.value, 0) }}<small> 家</small></div>
          <div class="metric-delta" :class="cls(metrics.over_10e_count.change)">{{ metrics.over_10e_count.change != null ? '较昨日' + signed(metrics.over_10e_count.change, 0) + ' 家' : '暂无可比较数据' }}</div>
        </div>
        <div class="metric">
          <div class="metric-label">成交额前50占比</div>
          <div class="metric-value flat">{{ metrics.top50_pct.value != null ? fmt(metrics.top50_pct.value, 2) + '%' : '—' }}</div>
          <div class="metric-delta" :class="cls(metrics.top50_pct.change)">{{ metrics.top50_pct.change != null ? '较昨日' + signed(metrics.top50_pct.change, 2) + ' pp' : '暂无可比较数据' }}</div>
        </div>
      </div>
      <div class="sec-note muted">样本 {{ metrics.stock_count.value ?? '—' }} 家 A股；两融余额为 T+1 统计值，与上一次有效统计日比较。</div>
    </section>

    <!-- 02 六大指数 -->
    <section v-if="visible('indexes')" class="sec">
      <div class="sec-h"><span class="sec-no">02</span><h2>六大指数</h2><span class="sec-sub">较上一有效交易日收盘</span></div>
      <table class="idx-table">
        <thead><tr><th>指数</th><th>收盘点位</th><th>涨跌点</th><th>涨跌幅</th></tr></thead>
        <tbody>
          <tr v-for="i in indexes" :key="i.code">
            <td>{{ i.name }}</td>
            <td class="num">{{ i.close != null ? fmt(i.close, 2) : '—' }}</td>
            <td class="num" :class="cls(i.change_points)">{{ signedPoints(i.change_points) }}</td>
            <td class="num" :class="cls(i.change_pct)">{{ i.change_pct != null ? signed(i.change_pct, 2) + '%' : '—' }}</td>
          </tr>
        </tbody>
      </table>
      <div class="muted small">涨跌点按当日收盘与上一有效交易日收盘差值计算。</div>
    </section>

    <!-- 03 今日市场概况 -->
    <section v-if="visible('summary')" class="sec">
      <div class="sec-h"><span class="sec-no">03</span><h2>今日市场概况</h2></div>
      <p class="body-text">{{ t.market_summary }}</p>
    </section>

    <!-- 04 行业及概念板块涨跌榜 -->
    <section v-if="visible('sector')" class="sec">
      <div class="sec-h"><span class="sec-no">04</span><h2>行业及概念板块涨跌榜</h2><span class="sec-sub">行业 / 概念独立排序 · 各取 Top5</span></div>

      <!-- 行业 -->
      <h3 class="rb-title">行业板块</h3>
      <div class="rb-grid">
        <div class="rb-col">
          <div class="rb-item up-bg">
            <span class="rb-tag up-tag">涨幅 Top5</span>
            <div class="rb-rows">
              <div v-for="(r, i) in sectorUp(sectorTop5.industry.up)" :key="r.name" class="rb-row">
                <span class="rk">{{ i + 1 }}</span><span class="rn">{{ r.name }}</span>
                <span class="up">{{ signed(r.change, 2) }}%</span>
                <span class="muted small">{{ r.limit_up_count != null ? r.limit_up_count + ' 涨停' : '' }}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="rb-col">
          <div class="rb-item down-bg">
            <span class="rb-tag down-tag">跌幅 Top5</span>
            <div class="rb-rows">
              <div v-for="(r, i) in sectorDown(sectorTop5.industry.down)" :key="r.name" class="rb-row">
                <span class="rk">{{ i + 1 }}</span><span class="rn">{{ r.name }}</span>
                <span class="down">{{ signed(r.change, 2) }}%</span>
                <span class="muted small">{{ r.limit_down_count != null ? r.limit_down_count + ' 跌停' : '' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <p v-if="sectorTop5.industry.note" class="muted small">{{ sectorTop5.industry.note }}</p>

      <!-- 概念 -->
      <h3 class="rb-title rb-title-mt">概念板块</h3>
      <div v-if="sectorTop5.concept.up && sectorTop5.concept.up.length" class="rb-grid">
        <div class="rb-col">
          <div class="rb-item up-bg">
            <span class="rb-tag up-tag">涨幅 Top5</span>
            <div class="rb-rows">
              <div v-for="(r, i) in sectorUp(sectorTop5.concept.up)" :key="r.name" class="rb-row">
                <span class="rk">{{ i + 1 }}</span><span class="rn">{{ r.name }}</span>
                <span class="up">{{ signed(r.change, 2) }}%</span>
                <span class="muted small">{{ r.limit_up_count != null ? r.limit_up_count + ' 涨停' : '' }}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="rb-col">
          <div class="rb-item down-bg">
            <span class="rb-tag down-tag">跌幅 Top5</span>
            <div class="rb-rows">
              <div v-for="(r, i) in sectorDown(sectorTop5.concept.down)" :key="r.name" class="rb-row">
                <span class="rk">{{ i + 1 }}</span><span class="rn">{{ r.name }}</span>
                <span class="down">{{ signed(r.change, 2) }}%</span>
                <span class="muted small">{{ r.limit_down_count != null ? r.limit_down_count + ' 跌停' : '' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <p class="muted small">{{ sectorTop5.concept.note }}</p>
      <p v-if="t.sector_text" class="body-text">{{ t.sector_text }}</p>
    </section>

    <!-- 05 成交额超10亿股票市值分布 -->
    <section v-if="visible('mktcap')" class="sec">
      <div class="sec-h"><span class="sec-no">05</span><h2>成交额超10亿元股票市值分布</h2></div>
      <div v-if="mktcapDist.sample_total != null && pieSlices.length" class="pie-wrap">
        <svg class="pie" viewBox="0 0 260 180" xmlns="http://www.w3.org/2000/svg">
          <g transform="translate(90,90)">
            <path v-for="s in pieSlices" :key="s.label" :d="slicePath(0, 0, 80, s.startDeg, s.endDeg)" :fill="s.color" stroke="#fff" stroke-width="1.5" />
          </g>
        </svg>
        <div class="pie-legend">
          <div v-for="s in pieSlices" :key="s.label" class="pie-row">
            <span class="pie-dot" :style="{ background: s.color }"></span>
            <span class="pie-label">{{ s.label }}</span>
            <span class="pie-num">{{ s.count }} 家 · {{ s.pct != null ? s.pct.toFixed(1) + '%' : '—' }}</span>
          </div>
        </div>
      </div>
      <p v-else class="body-text muted">{{ mktcapDist.note || '当日市值分布数据缺失。' }}</p>
      <p class="muted small">
        按股票家数统计的成交额≥10亿子集市值区间分布；有效样本 N={{ mktcapDist.sample_total ?? '—' }}
        <template v-if="mktcapDist.missing_mktcap">（{{ mktcapDist.missing_mktcap }} 家缺市值单独说明）</template>。
      </p>
    </section>

    <!-- 06 重要公告 -->
    <section v-if="visible('events')" class="sec">
      <div class="sec-h"><span class="sec-no">06</span><h2>重要公告</h2><span class="badge" :class="data.risk_events.coverage_status === 'complete' ? 'badge-ok' : 'badge-warn'">{{ data.risk_events.coverage_status === 'complete' ? '覆盖完整' : '覆盖不完整' }}</span></div>

      <!-- 公司回购 -->
      <h3 class="evt-group-title">公司回购</h3>
      <div v-if="groups.buyback.length" class="evt-list">
        <div v-for="e in groups.buyback" :key="e.event_id" class="evt-item">
          <span class="evt-company">{{ e.company_name }}<span class="evt-code" v-if="e.stock_code">（{{ e.stock_code }}）</span></span>
          <span class="evt-cat c-cap">回购</span>
          <a v-if="e.original_url" :href="e.original_url" target="_blank" rel="noopener" class="evt-url">原文</a>
        </div>
      </div>
      <p v-else class="muted small">本日暂无符合展示条件的回购公告。</p>

      <!-- 风险/监管/减持 -->
      <h3 class="evt-group-title">风险事项 · 监管 · 股东减持</h3>
      <div v-if="groups.risk.length" class="evt-list">
        <div v-for="e in groups.risk" :key="e.event_id" class="evt-item">
          <span class="evt-company">{{ e.company_name }}<span class="evt-code" v-if="e.stock_code">（{{ e.stock_code }}）</span></span>
          <span class="evt-cat" :class="catCls(e.event_category)">{{ e.event_category }}</span>
          <span class="evt-title-text">{{ e.title }}</span>
          <a v-if="e.original_url" :href="e.original_url" target="_blank" rel="noopener" class="evt-url">原文</a>
        </div>
      </div>
      <p v-else class="muted small">本日暂无符合展示条件的风险/监管/减持公告。</p>

      <p v-if="t.announcement_text" class="body-text">{{ t.announcement_text }}</p>
      <p class="muted small">{{ data.risk_events.message }}</p>
    </section>

    <!-- 底部说明 -->
    <footer class="ft">
      <div class="ft-title">数据口径、来源与免责声明</div>
      <div class="ft-disclaimer">{{ data.disclaimer || '本材料根据公开行情、上市公司公告、交易所及监管信息整理，仅作当日市场信息记录与事实展示，不构成投资建议、证券买卖意见或收益承诺。' }}</div>
      <ul class="ft-list">
        <li>行情数据：复盘台每日快照（两市成交额、涨跌停、10亿以上家数、Top50集中度、两融余额、六大指数、行业板块）。</li>
        <li>公告数据：巨潮资讯网（官方披露）。</li>
        <li>板块涨停/跌停家数按板块真实成分股与当日行情计算；历史日期未采集时以「—」表示。</li>
        <li>两融余额为 T+1 统计值，与上一次有效统计日比较，真实统计日已标注。</li>
        <li>事件分类仅说明事件客观性质，不代表对其股价影响的判断。</li>
      </ul>
      <div v-if="data.data_warnings.length" class="ft-warn">
        <div v-for="w in data.data_warnings" :key="w" class="ft-warn-item">⚠ {{ w }}</div>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.obs-export {
  width: 1200px;
  margin: 0 auto;
  background: #ffffff;
  color: #1a1a1a;
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
  line-height: 1.7;
  padding: 40px 44px 48px;
  box-sizing: border-box;
}
/* 头部 */
.hd { padding-bottom: 22px; border-bottom: 3px solid #1a1a1a; margin-bottom: 26px; }
.hd-brand { font-size: 14px; letter-spacing: 2px; color: #8a8a8a; margin-bottom: 6px; }
.hd-title { font-size: 34px; font-weight: 700; margin: 0 0 10px; letter-spacing: 1px; }
.hd-meta { font-size: 13px; color: #666; }
.hd-meta .sep { margin: 0 8px; color: #ccc; }
/* 分区 */
.sec { margin-bottom: 28px; padding: 22px 24px; background: #fafafa; border-radius: 12px; border: 1px solid #eee; }
.sec-h { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.sec-no { display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px; border-radius: 8px; background: #1a1a1a; color: #fff; font-size: 15px; font-weight: 700; }
.sec-h h2 { font-size: 21px; font-weight: 700; margin: 0; }
.sec-sub { font-size: 13px; color: #999; }
.sec-note { font-size: 13px; margin-top: 12px; }
/* 指标网格 */
.metric-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.metric { background: #fff; border: 1px solid #eee; border-radius: 10px; padding: 14px 16px; }
.metric-label { font-size: 13px; color: #777; margin-bottom: 4px; }
.metric-value { font-size: 26px; font-weight: 700; }
.metric-value small { font-size: 14px; color: #999; font-weight: 400; }
.metric-delta { font-size: 13px; }
.metric-stat { font-size: 12px; color: #999; margin-top: 2px; }
/* 涨红跌绿 */
.up { color: #c0392b; }
.down { color: #1e8449; }
.flat { color: #1a1a1a; }
.muted { color: #888; }
.num { font-variant-numeric: tabular-nums; }
/* 指数表格 */
.idx-table { width: 100%; border-collapse: collapse; font-size: 15px; }
.idx-table th, .idx-table td { text-align: left; padding: 10px 12px; border-bottom: 1px solid #eee; }
.idx-table th { background: #f5f5f5; color: #666; font-weight: 600; }
/* 正文 */
.body-text { font-size: 17px; margin: 0; }
.small { font-size: 12px; }
/* 徽标 */
.badge { font-size: 12px; padding: 2px 10px; border-radius: 20px; font-weight: 600; }
.badge-warn { background: #fff4e5; color: #b5651d; border: 1px solid #f0d9b5; }
.badge-ok { background: #eef7ee; color: #2e7d32; border: 1px solid #cde5cd; }
/* 板块红黑榜 */
.rb-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.rb-title { font-size: 16px; font-weight: 700; margin: 0 0 10px; }
.rb-title-mt { margin-top: 18px; }
.rb-col { display: flex; flex-direction: column; }
.rb-item { border-radius: 10px; padding: 12px 14px; }
.up-bg { background: #fff7f5; border: 1px solid #f3ddd7; }
.down-bg { background: #f4faf6; border: 1px solid #dcebe2; }
.rb-tag { display: inline-block; font-size: 12px; font-weight: 700; padding: 2px 10px; border-radius: 20px; margin-bottom: 8px; }
.up-tag { background: #c0392b; color: #fff; }
.down-tag { background: #1e8449; color: #fff; }
.rb-rows { display: flex; flex-direction: column; }
.rb-row { display: flex; align-items: center; gap: 10px; padding: 5px 0; font-size: 15px; }
.rk { width: 20px; text-align: center; color: #aaa; font-weight: 700; }
.rn { flex: 1; font-weight: 600; }
/* 饼图 */
.pie-wrap { display: flex; align-items: center; gap: 28px; }
.pie { flex: 0 0 auto; }
.pie-legend { flex: 1; display: flex; flex-direction: column; gap: 6px; }
.pie-row { display: flex; align-items: center; gap: 10px; font-size: 14px; }
.pie-dot { width: 12px; height: 12px; border-radius: 3px; flex: 0 0 auto; }
.pie-label { min-width: 88px; }
.pie-num { color: #555; }
/* 事件 */
.evt-group-title { font-size: 16px; font-weight: 700; margin: 14px 0 10px; }
.evt-list { display: flex; flex-direction: column; gap: 8px; }
.evt-item { display: flex; align-items: center; gap: 12px; padding: 9px 12px; background: #fff; border: 1px solid #eee; border-radius: 8px; font-size: 14px; }
.evt-company { font-weight: 600; }
.evt-code { color: #888; font-weight: 400; }
.evt-cat { font-size: 12px; padding: 1px 8px; border-radius: 12px; font-weight: 600; flex: 0 0 auto; }
.c-op { background: #e8f1fb; color: #2c5f8a; }
.c-perf { background: #eef7ee; color: #2e7d32; }
.c-sh { background: #f3f0fa; color: #5a4a9a; }
.c-cap { background: #fdf1e7; color: #9a5b1d; }
.c-reg { background: #fdeeee; color: #9a3b3b; }
.c-law { background: #fdf0f0; color: #8a3b3b; }
.c-pol { background: #eef4f7; color: #38607a; }
.c-mac { background: #f0f4f0; color: #3b6a3b; }
.c-other { background: #f0f0f0; color: #666; }
.evt-title-text { flex: 1; color: #444; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.evt-url { color: #4a6fa5; font-size: 12px; flex: 0 0 auto; }
/* 底部 */
.ft { margin-top: 8px; padding-top: 20px; border-top: 2px solid #e5e5e5; }
.ft-title { font-size: 15px; font-weight: 700; margin-bottom: 10px; }
.ft-disclaimer { font-size: 13px; color: #555; background: #fafafa; border: 1px solid #eee; border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; }
.ft-list { margin: 0; padding-left: 20px; font-size: 13px; color: #777; }
.ft-list li { margin-bottom: 4px; }
.ft-warn { margin-top: 12px; }
.ft-warn-item { font-size: 12px; color: #b5651d; margin-bottom: 3px; }
</style>

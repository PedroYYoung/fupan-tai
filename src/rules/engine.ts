import type { Conclusion, ConclusionItem, DailyData } from '@/types'
import { THRESHOLDS as T } from './thresholds'

export interface BucketPt { date: string; buckets: { label: string; count: number; pct: number }[] }

function pctText(p: number | null): string {
  return p == null ? '百分位缺失' : `百分位 ${p}%`
}

/**
 * 输入当日指标 → 三条短句（资金/结构/情绪）+ 总分 0–100
 * 每条结论末尾附依据，保证可追溯。
 * bucketPts（可选）：市值分档序列，用于「大盘吸血 / 小微盘活跃」结构判断。
 */
export function conclude(d: DailyData, bucketPts?: BucketPt[]): Conclusion {
  const sp = d.sparklines
  const fund = fundRule(d)
  const structure = structureRule(d, bucketPts)
  const emotion = emotionRule(d)
  const score = Math.max(0, Math.min(100, fund.score + structure.score + emotion.score))
  return {
    fund: { text: fund.text, basis: fund.basis },
    structure: { text: structure.text, basis: structure.basis },
    emotion: { text: emotion.text, basis: emotion.basis },
    score
  }
}

function fundRule(d: DailyData): ConclusionItem & { score: number } {
  const o = d.overview
  const sp = d.sparklines
  let text = '资金面中性，量能处于常态区间'
  let score = 20
  const amtPct = o.total_amount_pctile_all
  const over10ePct = d.liquidity.pctile_count

  // 环比（前一交易日）
  let mom: number | null = null
  if (sp && sp.total_amount.length >= 2) {
    const prev = sp.total_amount[sp.total_amount.length - 2].value
    if (prev > 0) mom = ((o.total_amount - prev) / prev) * 100
  }
  if (mom != null && amtPct != null) {
    if (mom > T.fund.vol_up_pct && over10ePct != null && over10ePct > T.fund.over10e_pctile_high) {
      text = '放量普涨，流动性充裕'
      score = 38
    } else if (mom < T.fund.vol_down_pct && over10ePct != null && over10ePct < T.fund.over10e_pctile_low) {
      text = '缩量退潮，观望为主'
      score = 6
    }
  }
  let basis = ''
  if (mom != null) {
    basis = `依据：两市成交环比 ${mom > 0 ? '+' : ''}${mom.toFixed(1)}%，10亿以上家数${over10ePct != null ? '历史' + over10ePct + '%' : '百分位缺失'}`
  } else {
    basis = `依据：两市成交 ${o.total_amount} 亿，环比数据缺失`
  }
  if (o.margin_pctile_all != null && o.margin_pctile_all > T.fund.margin_pctile_high) {
    text = '杠杆资金处于历史高位区间，警惕拥挤'
    basis += `；两融余额历史百分位 ${o.margin_pctile_all}%`
    score = Math.max(score, 30)
  }
  return { text, basis, score }
}

function structureRule(d: DailyData, bucketPts?: BucketPt[]): ConclusionItem & { score: number } {
  const c = d.concentration
  let text = '成交分布均衡，无极端集中信号'
  let score = 15
  let basis = ''
  if (c.top10_total_pctile_hist != null) {
    basis = `依据：前10成交占比历史${pctText(c.top10_total_pctile_hist)}`
    if (c.top10_total_pctile_hist > T.structure.top10_pctile_extreme) {
      text = '成交高度集中于头部，风格极致'
      score = 28
    }
  } else {
    basis = '依据：前10成交占比百分位缺失'
  }
  // 大盘 vs 微盘：市值档位环比（>1000亿 上升 且 <50亿 下降 → 大盘吸血；反之 → 小微盘活跃）
  const buckets = d.liquidity.mktcap_buckets
  const big = buckets.find((b) => b.label === '>1000亿')
  const micro = buckets.find((b) => b.label === '<50亿')
  if (big && micro) {
    basis += `；>1000亿档占 ${big.pct}%，<50亿档占 ${micro.pct}%`
    if (bucketPts && bucketPts.length >= 2) {
      const last = bucketPts[bucketPts.length - 1].buckets
      const prev = bucketPts[bucketPts.length - 2].buckets
      const bLast = last.find((b) => b.label === '>1000亿')?.pct
      const bPrev = prev.find((b) => b.label === '>1000亿')?.pct
      const mLast = last.find((b) => b.label === '<50亿')?.pct
      const mPrev = prev.find((b) => b.label === '<50亿')?.pct
      if (bLast != null && bPrev != null && mLast != null && mPrev != null) {
        basis += `（环比 ${bPrev}%→${bLast}% / ${mPrev}%→${mLast}%）`
        if (bLast > bPrev && mLast < mPrev) {
          text = '大盘吸血，小微盘失血'
          score = Math.max(score, 22)
        } else if (mLast > mPrev && bLast < bPrev) {
          text = '小微盘活跃，题材主导'
          score = Math.max(score, 20)
        }
      }
    }
  }
  return { text, basis, score }
}

function emotionRule(d: DailyData): ConclusionItem & { score: number } {
  const e = d.emotion
  let text = '情绪平稳'
  let score = 15
  let basis = `依据：涨停 ${e.limit_up} 家（历史${pctText(e.lu_pctile)}），跌停 ${e.limit_down} 家（历史${pctText(e.ld_pctile)}）`
  if (e.lu_pctile != null && e.lu_pctile > T.emotion.lu_pctile_high && e.ld_pctile != null && e.ld_pctile < T.emotion.ld_pctile_low) {
    text = '赚钱效应强，情绪高位'
    score = 28
  }
  if (e.limit_down > T.emotion.ld_count_risk && e.ld_over10e.length >= T.emotion.ld_over10e_risk) {
    text = `高位股杀跌，注意接力风险（10亿以上跌停 ${e.ld_over10e.length} 只）`
    score = 4
    basis += `；10亿以上跌停票：${e.ld_over10e.map((s) => s.name).join('、')}`
  }
  return { text, basis, score }
}

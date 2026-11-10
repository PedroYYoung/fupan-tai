import type { Conclusion, ConclusionItem, DailyData, SignalTag } from '@/types'
import { THRESHOLDS as T } from './thresholds'

export interface BucketPt { date: string; buckets: { label: string; count: number; pct: number }[] }

function pctText(p: number | null): string {
  return p == null ? '百分位缺失' : `百分位 ${p}%`
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v))
}

/**
 * 输入当日指标 → 三段落结论（资金/结构/情绪）+ 综合结论 + 总分 0~100。
 * 每个维度结论附可追溯的数据依据；评分规则见 thresholds.ts 顶部注释。
 * bucketPts（可选）：市值分档序列，用于「大盘吸血 / 小微盘活跃」结构判断。
 */
export function conclude(d: DailyData, bucketPts?: BucketPt[]): Conclusion {
  const fund = fundRule(d)
  const structure = structureRule(d, bucketPts)
  const emotion = emotionRule(d)
  const score = clamp(fund.score! + structure.score! + emotion.score!, 0, 100)
  const summary = summarize(d, fund, structure, emotion)
  const scoreDetail = `资金 ${fund.score}/${fund.scoreMax} + 结构 ${structure.score}/${structure.scoreMax} + 情绪 ${emotion.score}/${emotion.scoreMax}`
  return {
    fund: { text: fund.text, basis: fund.basis, paragraph: fund.paragraph, score: fund.score, scoreMax: fund.scoreMax },
    structure: { text: structure.text, basis: structure.basis, paragraph: structure.paragraph, score: structure.score, scoreMax: structure.scoreMax, tags: structure.tags },
    emotion: { text: emotion.text, basis: emotion.basis, paragraph: emotion.paragraph, score: emotion.score, scoreMax: emotion.scoreMax, tags: emotion.tags },
    score,
    summary,
    scoreDetail
  }
}

// ---------------------------------------------------------------- 资金面

function fundRule(d: DailyData): ConclusionItem & { score: number; scoreMax: number; paragraph: string } {
  const o = d.overview
  const sp = d.sparklines
  const scoreMax = T.weight.fund
  let score = T.base.fund
  let text = '资金面中性，量能处于常态区间'
  const amtPct = o.total_amount_pctile_all
  const over10ePct = d.liquidity.pctile_count

  // 环比（前一交易日）
  let mom: number | null = null
  if (sp && sp.total_amount.length >= 2) {
    const prev = sp.total_amount[sp.total_amount.length - 2].value
    if (prev > 0) mom = ((o.total_amount - prev) / prev) * 100
  }

  let basis = ''
  const amtText = o.total_amount != null ? `${o.total_amount} 亿` : '缺失'
  if (mom != null) {
    basis = `两市成交 ${amtText}，环比 ${mom > 0 ? '+' : ''}${mom.toFixed(1)}%`
    if (amtPct != null) basis += `（历史${pctText(amtPct)}）`
    if (over10ePct != null) basis += `；10亿以上家数 ${o.over_10e_count ?? '—'} 家（历史${pctText(over10ePct)}）`
  } else {
    basis = `两市成交 ${amtText}，环比数据缺失`
  }

  let paragraph = `今日两市成交额 ${amtText}。`
  if (mom != null && amtPct != null) {
    paragraph += `较上一交易日${mom > 0 ? '放量' : '缩量'} ${Math.abs(mom).toFixed(1)}%，成交额处于历史${pctText(amtPct)}。`
  }
  if (over10ePct != null) {
    paragraph += `成交额超 10 亿的个股 ${o.over_10e_count ?? '—'} 家，历史${pctText(over10ePct)}。`
  }
  if (o.margin_balance != null) {
    const md = o.margin_date ? `（${o.margin_date}）` : ''
    paragraph += `两融余额 ${o.margin_balance.toLocaleString('zh-CN')} 亿${md}`
    if (o.margin_pctile_all != null) paragraph += `，历史${pctText(o.margin_pctile_all)}`
    paragraph += '。'
  }

  // 放量 / 缩量判断（多条件同时满足才触发）
  if (mom != null && amtPct != null && over10ePct != null) {
    if (mom > T.fund.vol_up_pct && over10ePct > T.fund.over10e_pctile_high) {
      text = '明显放量，交投活跃度提升'
      score = T.base.fund + T.fund.score_delta
      paragraph += '成交额环比显著放大且高成交个股家数处于历史高位，交投活跃度明显提升。'
    } else if (mom < T.fund.vol_down_pct && over10ePct < T.fund.over10e_pctile_low) {
      text = '明显缩量，交投热度退潮'
      score = T.base.fund - T.fund.score_delta
      paragraph += '成交额环比显著萎缩且高成交个股家数处于历史低位，交投活跃度明显退潮。'
    }
  }

  // 杠杆高位警示（不改分）
  if (o.margin_pctile_all != null && o.margin_pctile_all > T.fund.margin_pctile_high) {
    text = '杠杆资金处于历史高位区间，警惕拥挤'
    basis += `；两融余额历史${pctText(o.margin_pctile_all)}（杠杆高位警示）`
    paragraph += '两融余额处于历史高位区间，杠杆资金拥挤度偏高，需留意回调风险。'
  }

  return { text, basis, paragraph, score, scoreMax }
}

// ---------------------------------------------------------------- 结构面

function structureRule(d: DailyData, bucketPts?: BucketPt[]): ConclusionItem & { score: number; scoreMax: number; paragraph: string; tags: SignalTag[] } {
  const c = d.concentration
  const scoreMax = T.weight.structure
  const base = T.base.structure
  const tags: SignalTag[] = []

  const t10 = c.top10_total
  const t20 = c.top20_cum_pct
  const t50 = c.top50_cum_pct

  // 1. 集中度信号（top10 历史分位）
  const t10Pct = c.top10_total_pctile_hist
  if (t10Pct != null) {
    if (t10Pct > T.structure.top10_pctile_extreme) {
      tags.push({
        label: '成交高度集中',
        direction: 'risk',
        delta: -T.structure.score_delta,
        basis: `前10成交占比 ${t10 != null ? t10.toFixed(1) + '%' : '—'} 处历史分位 ${t10Pct}%（极高）`
      })
    } else if (t10Pct < T.structure.top10_pctile_disperse) {
      tags.push({
        label: '成交极度分散',
        direction: 'positive',
        delta: T.structure.score_delta,
        basis: `前10成交占比 ${t10 != null ? t10.toFixed(1) + '%' : '—'} 处历史分位 ${t10Pct}%（极低）`
      })
    }
  }

  // 2. 市值结构信号（大市值 vs 小微盘环比，按当前交易日定位）
  const buckets = d.liquidity.mktcap_buckets
  const big = buckets.find((b) => b.label === '>1000亿')
  const micro = buckets.find((b) => b.label === '<50亿')
  if (big && micro && bucketPts && bucketPts.length >= 2) {
    // 关键：按当前交易日 d.trade_date 在序列里定位，不能固定用序列最后两组（否则选历史日期会错误套用最新日期的环比）
    let idx = bucketPts.findIndex((p) => p.date === d.trade_date)
    if (idx < 0) idx = bucketPts.length - 1
    if (idx > 0) {
      const last = bucketPts[idx].buckets
      const prev = bucketPts[idx - 1].buckets
      const bLast = last.find((b) => b.label === '>1000亿')?.pct
      const bPrev = prev.find((b) => b.label === '>1000亿')?.pct
      const mLast = last.find((b) => b.label === '<50亿')?.pct
      const mPrev = prev.find((b) => b.label === '<50亿')?.pct
      if (bLast != null && bPrev != null && mLast != null && mPrev != null) {
        if (bLast > bPrev && mLast < mPrev) {
          tags.push({
            label: '大盘吸血',
            direction: 'risk',
            delta: -T.structure.mktcap_score_delta,
            basis: `大市值档占比 ${bPrev}%→${bLast}% 升、小微盘档 ${mPrev}%→${mLast}% 降`
          })
        } else if (mLast > mPrev && bLast < bPrev) {
          tags.push({
            label: '小微盘活跃',
            direction: 'positive',
            delta: T.structure.mktcap_score_delta,
            basis: `小微盘档占比 ${mPrev}%→${mLast}% 升、大市值档 ${bPrev}%→${bLast}% 降`
          })
        }
      }
    }
  }

  // 3. 识别分化：相反方向信号并存
  const hasRisk = tags.some((t) => t.direction === 'risk')
  const hasPositive = tags.some((t) => t.direction === 'positive')
  const diverged = hasRisk && hasPositive
  if (diverged) {
    tags.push({ label: '结构分化', direction: 'neutral', delta: 0, basis: '风险与积极信号并存' })
  }

  // 4. 得分累积（保留每一项分值贡献，非覆盖）
  let score = base
  for (const t of tags) score += t.delta
  score = clamp(score, 0, scoreMax)

  // 5. 生成连贯文字（不再互相覆盖）
  let concDesc = ''
  if (t10Pct != null) {
    if (t10Pct > T.structure.top10_pctile_extreme) {
      concDesc = `前10大个股成交占比处于历史极高位置（分位 ${t10Pct}%），成交集中度风险突出`
    } else if (t10Pct < T.structure.top10_pctile_disperse) {
      concDesc = `前10大个股成交占比处于历史极低位置（分位 ${t10Pct}%），成交极度分散`
    } else {
      concDesc = `前10大个股成交占比处于历史常态区间（分位 ${t10Pct}%）`
    }
  } else {
    concDesc = '（集中度历史百分位缺失，无法与历史比较）'
  }

  let mktDesc = ''
  if (tags.some((t) => t.label === '大盘吸血')) {
    mktDesc = '大市值档成交占比上升、小微盘档下降，资金向权重股集中'
  } else if (tags.some((t) => t.label === '小微盘活跃')) {
    mktDesc = '小微盘档成交占比上升、大市值档下降，市场参与范围向中小市值扩散'
  }

  let text: string
  let paragraph: string
  if (diverged) {
    text = '成交集中与扩散并存，结构分化'
    paragraph = `${concDesc}；与此同时，${mktDesc}。两个现象并存，市场结构呈现分化，而非单一的大盘主导或题材主导。`
  } else if (tags.some((t) => t.label === '成交高度集中')) {
    text = '成交高度集中于头部，风格极致'
    paragraph = `${concDesc}，资金高度集中，市场呈现明显的权重/龙头虹吸特征。`
    if (mktDesc) paragraph += mktDesc + '。'
  } else if (tags.some((t) => t.label === '成交极度分散')) {
    text = '成交极度分散，普涨格局'
    paragraph = `${concDesc}，资金分散，市场呈现普涨、题材多点开花的格局。`
    if (mktDesc) paragraph += mktDesc + '。'
  } else if (tags.some((t) => t.label === '大盘吸血')) {
    text = '大盘吸血，小微盘失血'
    paragraph = `${concDesc}；${mktDesc}。`
  } else if (tags.some((t) => t.label === '小微盘活跃')) {
    text = '小微盘活跃，题材主导'
    paragraph = `${concDesc}；${mktDesc}。`
  } else {
    text = '成交分布均衡，无极端集中信号'
    paragraph = `${concDesc}。集中度处于历史常态区间，无明显极端结构特征。`
  }

  // 6. 依据：逐信号列示（不含中性标签）
  const basis = tags.filter((t) => t.direction !== 'neutral').map((t) => t.basis).join('；') || '前10成交占比百分位缺失'

  return { text, basis, paragraph, score, scoreMax, tags }
}

// ---------------------------------------------------------------- 情绪面

function emotionRule(d: DailyData): ConclusionItem & { score: number; scoreMax: number; paragraph: string; tags: SignalTag[] } {
  const e = d.emotion
  const scoreMax = T.weight.emotion
  const base = T.base.emotion
  const tags: SignalTag[] = []

  const luText = e.limit_up == null ? '—' : `${e.limit_up} 家`
  const ldText = e.limit_down == null ? '—' : `${e.limit_down} 家`

  // 1. 赚钱效应信号
  const profit = e.lu_pctile != null && e.lu_pctile > T.emotion.lu_pctile_high && e.ld_pctile != null && e.ld_pctile < T.emotion.ld_pctile_low
  if (profit) {
    tags.push({
      label: '赚钱效应强',
      direction: 'positive',
      delta: T.emotion.score_delta,
      basis: `涨停家数历史分位 ${e.lu_pctile}%（高位）、跌停家数历史分位 ${e.ld_pctile}%（低位）`
    })
  }

  // 2. 杀跌风险信号
  const kill = e.limit_down != null && e.limit_down > T.emotion.ld_count_risk && e.ld_over10e.length >= T.emotion.ld_over10e_risk
  if (kill) {
    tags.push({
      label: '高位股杀跌',
      direction: 'risk',
      delta: -T.emotion.score_delta,
      basis: `跌停 ${e.limit_down} 家（>${T.emotion.ld_count_risk}）、10亿以上跌停 ${e.ld_over10e.length} 只：${e.ld_over10e.slice(0, 5).map((s) => s.name).join('、')}${e.ld_over10e.length > 5 ? ' 等' : ''}`
    })
  }

  // 3. 得分：杀跌风险优先（保持现有规则，不叠加）
  let score = base
  if (kill) {
    score = base - T.emotion.score_delta
  } else if (profit) {
    score = base + T.emotion.score_delta
  }
  score = clamp(score, 0, scoreMax)

  // 4. 文字：保留两个信号，突出风险
  let text: string
  let paragraph = `今日涨停 ${luText}、跌停 ${ldText}。`
  if (profit && kill) {
    text = '赚钱效应与杀跌风险并存，综合偏谨慎'
    paragraph += '涨停家数处历史高位、跌停家数处历史低位，赚钱效应仍在；但跌停家数超阈值且高成交额品种出现杀跌，亏钱效应同步显现，综合判断偏向谨慎、突出风险。'
  } else if (profit) {
    text = '赚钱效应强，情绪高位'
    paragraph += '涨停家数处于历史高位、跌停家数处于历史低位，市场赚钱效应显著。'
  } else if (kill) {
    text = '高位股杀跌，注意接力风险'
    paragraph += `跌停家数超过 ${T.emotion.ld_count_risk} 家，且成交额超 10 亿的跌停个股达 ${e.ld_over10e.length} 只，高成交额品种出现杀跌，亏钱效应显现。`
  } else {
    text = '市场情绪平稳'
    if (e.lu_pctile != null && e.ld_pctile != null) {
      paragraph += `涨停家数处于历史分位 ${e.lu_pctile}%、跌停家数处于历史分位 ${e.ld_pctile}%。`
    }
  }

  // 5. 依据：逐信号列示
  const basis = tags.map((t) => t.basis).join('；') || `涨停 ${luText}、跌停 ${ldText}`

  // 6. 附加：10亿以上涨停/跌停占比
  if (e.lu_ratio_of_over10e != null) {
    paragraph += `成交额超 10 亿个股中涨停占比 ${e.lu_ratio_of_over10e.toFixed(1)}%`
    if (e.ld_ratio_of_over10e != null) paragraph += `、跌停占比 ${e.ld_ratio_of_over10e.toFixed(1)}%`
    paragraph += '。'
  }

  return { text, basis, paragraph, score, scoreMax, tags }
}

// ---------------------------------------------------------------- 综合结论

function summarize(
  d: DailyData,
  fund: { text: string },
  structure: { text: string },
  emotion: { text: string }
): string {
  const o = d.overview
  const parts: string[] = []
  // 核心特征
  const amt = o.total_amount != null ? `${o.total_amount.toLocaleString('zh-CN')} 亿` : '（成交额缺失）'
  parts.push(`今日两市成交 ${amt}，涨停 ${o.limit_up ?? '—'} 家、跌停 ${o.limit_down ?? '—'} 家。`)
  // 三维度关系
  parts.push(`资金面${fund.text}，结构面${structure.text}，情绪面${emotion.text}。`)

  // 分化判断
  const tags = [fund.text, structure.text, emotion.text]
  const bullish = tags.some((t) => /放量|活跃|均衡|普涨|小微盘活跃|赚钱效应|题材主导/.test(t))
  const bearish = tags.some((t) => /缩量|退潮|集中|极致|杀跌|失血|高位区间|风险|谨慎/.test(t))
  const diverged = tags.some((t) => /分化|并存/.test(t))
  if (diverged) {
    parts.push('市场多空信号并存，结构存在分化，需结合具体板块与风格判断，不宜简单定性为单边改善或恶化。')
  } else if (bullish && bearish) {
    parts.push('多维度信号存在分化，市场处于结构性行情而非单边市，需结合具体板块与风格判断。')
  } else if (bullish) {
    parts.push('综合来看，市场较近期有所改善，量能与情绪配合度较好。')
  } else if (bearish) {
    parts.push('综合来看，市场较近期走弱，交投活跃度与赚钱效应均需警惕。')
  } else {
    parts.push('综合来看，市场处于相对均衡状态，无明显的单边改善或恶化信号。')
  }
  return parts.join('')
}

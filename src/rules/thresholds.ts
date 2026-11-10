// ===== 自动结论规则引擎：阈值、权重、计分集中于此，可编辑 =====
//
// 评分规则（满分 100）：
//   总评 = 资金面(0~40) + 结构面(0~30) + 情绪面(0~30)
// 每维度：基准分（中性）+ 触发条件的加减分；分数被 clamp 到 [0, 满分]。
// 阈值触发采用「多条件同时满足」，避免单指标误判；样本量不足 MIN_SAMPLE 时
// 不生成依赖历史百分位的判断。
export const THRESHOLDS = {
  // 维度满分与中性基准分
  weight: { fund: 40, structure: 30, emotion: 30 },
  base: { fund: 24, structure: 18, emotion: 18 },

  // 生成依赖历史百分位的判断所需的最小样本量
  min_sample: 30,

  fund: {
    vol_up_pct: 15,          // 两市成交环比 > +15% 视为放量
    vol_down_pct: -15,       // 环比 < -15% 视为缩量
    over10e_pctile_high: 80, // 10亿以上家数百分位 > 80 视为活跃度高
    over10e_pctile_low: 20,  // 百分位 < 20 视为活跃度低
    margin_pctile_high: 90,  // 两融百分位 > 90 → 杠杆拥挤警示（不改分）
    score_delta: 16          // 放量/缩量触发时的加减分
  },

  structure: {
    top10_pctile_extreme: 90, // 前10成交占比百分位 > 90 → 高度集中（分化）
    top10_pctile_disperse: 10, // 前10成交占比百分位 < 10 → 极度分散（均衡）
    score_delta: 12,           // 集中/分散触发时的加减分
    mktcap_score_delta: 6      // 市值结构（大盘吸血/小微盘活跃）调整分
  },

  emotion: {
    lu_pctile_high: 90,   // 涨停百分位 > 90
    ld_pctile_low: 10,    // 跌停百分位 < 10
    ld_count_risk: 50,    // 跌停家数 > 50
    ld_over10e_risk: 5,   // 10亿以上跌停票 ≥ 5
    score_delta: 12       // 赚钱效应/杀跌风险触发时的加减分
  }
}

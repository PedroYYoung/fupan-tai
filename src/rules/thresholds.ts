// ===== 自动结论规则引擎：阈值集中于此，可编辑 =====
export const THRESHOLDS = {
  fund: {
    vol_up_pct: 15,          // 两市成交环比 > +15%
    vol_down_pct: -15,       // 环比 < -15%
    over10e_pctile_high: 80, // 10亿以上家数百分位 > 80
    over10e_pctile_low: 20,  // 百分位 < 20
    margin_pctile_high: 90   // 两融百分位 > 90 → 杠杆拥挤警示
  },
  structure: {
    top10_pctile_extreme: 90 // 前10成交占比百分位 > 90 → 风格极致
  },
  emotion: {
    lu_pctile_high: 90,
    ld_pctile_low: 10,
    ld_count_risk: 50,       // 跌停家数 > 50
    ld_over10e_risk: 5       // 10亿以上跌停票 ≥ 5
  }
}

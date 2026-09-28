# 复盘台

职业交易员的每日复盘台：纯静态 Web 应用 + 本地/CI 双模式数据脚本。
**当前交付：全部四批，11/11 页面已上线。**

## 技术栈

- 前端：Vue 3.4 (Composition API) + TypeScript 5 + Vite 5 + Pinia + Vue Router (history) + ECharts 5.5（按需引入）+ PWA（manifest + Workbox，vite-plugin-pwa）
- 样式：纯 CSS 变量 + Flex/Grid，无 UI 组件库
- 数据：Python 3.11 + AKShare，JSON 静态文件随仓库提交
- 托管：Vercel 纯静态；口令 `VITE_GATE_HASH`（SHA-256，sessionStorage 24h）

## 快速开始

```bash
npm install && npm run dev      # http://localhost:5173
python scripts/build.py --date 20260925   # 真实建仓（需 pip install -r scripts/requirements.txt）
python scripts/make_sample_data.py        # 重新生成内置演示数据
python scripts/make_icons.py              # 重新生成 PWA 图标
```

> 仓库已内置演示数据（`public/data/`）：字段结构与正式数据完全一致，数值为合理真实量级（种子随机的合成行情），首次 `build.py` 会覆盖。节假日窗口为近似值，正式数据以交易日历接口为准。

## public/data/ 目录结构（统一数据根）

**单一数据架构**：所有 JSON 数据只存在于 `public/data/` 一处——Vite dev 直接托管为 `/data/*`，构建时随 `dist/` 发布，Vercel/本地/CI 三端同构，无第二份拷贝、无同步步骤。数据管线（`build.py` / `update_data.py`）也直接写入此处。

```
public/data/
├── meta/trading_days.json      # 交易日历 {list, latest, updated_at, source_versions}
├── meta/last_error.log         # 构建失败记录（成功时不生成，gitignore）
├── latest.json                 # {latest: "20260925", updated_at}
├── daily/YYYYMMDD.json         # 每日快照（overview/index_volume/widebase/concentration/liquidity/emotion + sparklines）
├── series/*.json               # 历史序列（total_amount/margin/limit_up_down/over_10e_count/index_amount_* 等），含预计算 rank/pctile
├── stocks.json                 # 自选股清单（手动维护）：{"stocks":[{"code":"000001","name":"平安银行"}]}
└── quotes.json                 # 自选股行情快照（scripts/update_data.py 生成）：{"date":"YYYY-MM-DD","quotes":[{code,name,price,change}]}
```

- 主数据（daily/series/meta）与自选股行情（quotes.json）**解耦**：主数据按交易日 YYYYMMDD 组织、由 `build.py` 每日收盘后更新；quotes 按自然日 YYYY-MM-DD、可在盘中/收盘多次更新，前端 store 中分别管理、独立失败互不影响。
- **扩展约定**（V2）：个股 K 线/历史走势放 `public/data/quotes/kline_{code}.json`，技术指标放 `series/indicator_*.json`，复盘记录沿用 `notesdb`（IndexedDB）或 `daily/` 扩展字段——均无需改动现有结构。

金额单位统一「亿元」；百分比为数值（8.5 表示 8.5%）；日期 YYYYMMDD 字符串；null 表示缺失而非 0。
契约扩展（向后兼容）：第一批新增 `daily.sparklines`；第二批新增 `concentration.top20/top50` 明细、
`series/top10_concentration.json`（头部抱团度）、`series/mktcap_buckets.json`（市值分档结构，滚动 400 点）；
第三批新增 `series/index_agg.json`（各指数月/年均值预聚合表，四档切换单请求、页面 JSON 请求 ≤3）。

## 结论规则引擎（src/rules/，阈值集中在 thresholds.ts 可编辑）

- **资金**：成交环比 >+15% 且 10亿以上百分位 >80 → 放量普涨；环比 <-15% 且百分位 <20 → 缩量退潮；两融百分位 >90 → 杠杆拥挤警示
- **结构**：前10成交占比百分位 >90 → 风格极致；>1000亿档环比上升且 <50亿档下降 → 大盘吸血、小微盘失血；反之 → 小微盘活跃、题材主导
- **情绪**：涨停百分位 >90 且跌停百分位 <10 → 赚钱效应强；跌停 >50 家且 10亿以上跌停 ≥5 → 高位股杀跌提示
- 每条结论附「依据：X=xx，百分位xx%」，总分 = 资金(≤38)+结构(≤28)+情绪(≤28)，映射 0-100

## 序列层回补（第二批，仅本地）

```bash
python scripts/build.py --incremental --backfill-days 250   # 回补最近 250 个交易日的序列
```

- **可回补**：两市成交额（上证+深成指日线代理口径）、两融余额、涨跌停池、各指数/宽基成交额
- **不可回补**（依赖当日全市场快照，东财仅实时可得，自启用日起每日累积）：10亿以上家数、市值分档、前10集中度
- 回补内置限速（每 50 次请求歇 2s、失败重试 2 次），350 天回补约 15-25 分钟

## 已交付页面

| 路由 | 页面 | 状态 |
|---|---|---|
| `/` | 🏠 今日速览（4 大数字卡片 + 自动结论 + 3 迷你折线） | ✅ 第一批 |
| `/money` | 💰 资金面（成交/两融 + 本日/本月/本年/历史四档聚合切换） | ✅ 第二批 |
| `/index` | 📊 指数成交排位（5 行固定表格 + 四档切换） | ✅ 第三批 |
| `/widebase` | 🧩 宽基矩阵（11 格 + 百分位色阶热力 + 四档切换） | ✅ 第三批 |
| `/concentration` | 🎯 个股集中度（前10/20/50 三表 + 头部抱团度折线） | ✅ 第二批 |
| `/liquidity` | 📐 流动性结构（10亿以上家数折线 + 市值 6 档堆叠面积） | ✅ 第二批 |
| `/emotion` | 🔥 情绪（涨跌停双折线 + 占比 + 10亿以上明细表） | ✅ 第二批 |
| `/report` | 📋 复盘报告（指标总表 + 三句结论 + 本地备注 + 导出 PNG） | ✅ 第一批 |
| `/calendar` | 🔍 日历回溯（交易日历月视图，URL ?date= 可分享） | ✅ 第二批 |
| `/industry` | 🏭 行业（东财行业当日涨跌 TOP10 双栏 + 口径说明） | ✅ 第四批 |
| `/notes` | ✏️ 交易日志（IndexedDB 本地存储 + 标签筛选 + JSON 导出） | ✅ 第四批 |
| `/status` | 🟢 数据状态（更新时间/源版本/样本量/失败记录） | ✅ 第一批 |

## 数据管线

- `scripts/build.py --date YYYYMMDD`：单日快照模式（第一批）
- `scripts/build.py --incremental`：增量模式（CI/任务计划用）
- `--backfill-days N`：本地历史回补（勿在 CI 使用）
- 模块：`calendar_mod` 交易日 / `spot_mod` 全市场快照（东财主源 + efinance 备源）/ `margin_mod` 两融 / `zt_mod` 涨跌停（含快照兜底判定）/ `index_mod` 指数成交额（恒生科技用 513180 近似）/ `compute` 排名·百分位·市值分档·微盘代理·集中度 / `notify` 失败推送
- 硬规则：单接口重试≤2 次间隔 5s；每 50 次请求 sleep 2s；`*.tmp` 原子替换；任一日失败保留旧数据 + `last_error.log` + `exit 0`

## 第一批验收清单（逐条可测）

1. `npm run dev` 打开 `/`：4 个真实数字（成交额/两融/涨跌停/10亿以上家数，非 0 非 —）+ 一句自动结论。
2. 断网刷新 `/report`：命中 SW 缓存仍可打开并显示最近数据（需 `npm run build && npm run preview` 或部署后测试，dev 模式无 SW）。
3. 375px 宽：侧边栏变抽屉，☰ 开关，遮罩点击关闭；后续批次表格页横向滚动。
4. 带百分位卡片右下角有「样本N=xxxx」；样本 N<30 显示「样本不足」且不画折线（阈值 `MIN_SAMPLE=30`，`src/stores/data.ts`）。
5. `/?date=20200102` 正常渲染（演示数据含该日）；`/?date=20990101` 自动回退最新交易日 + 黄色提示条。
6. 删除任一 `data/daily/*.json` 再访问该日：不白屏，黄色兜底文案并回退。
7. `build.py` 中途 Ctrl+C：`public/data/` 无 `.tmp` 残留、无半份 json（`atomic_write_json` 先写临时文件再 `os.replace`）。
8. `/report` 点「导出 PNG」：含日期、指标总表、三句结论，微信可直接查看。
9. Chrome「安装应用」可用；Android「添加到主屏幕」后独立窗口、无地址栏、红色图标（#B7410E + 白字「复盘台」）。
10. 口令：`.env.production` 设置 `VITE_GATE_HASH=<64位SHA-256>` 后构建，未解锁时页面 DOM 与源码中无任何指标数值。
11. 模拟接口失败（如把 `spot_mod.py` 中函数名改错）：网站仍显示上一交易日数据，`data/meta/last_error.log` 有记录（若配置 PUSHPLUS_TOKEN 会收到推送）。

## 已知限制（如实）

- **演示数据非实盘**：内置 `public/data/` 为种子随机合成数据，量级参照真实市场；跑一次 `build.py` 即替换为实盘数据。
- 行业页当日数据为东财行业板块口径；历史序列需申万指数回填，严格的「东财行业 ↔ 申万二级」成分映射需用户提供对齐表 CSV，
  之后运行 `python scripts/build.py --industry-backfill 对齐表.csv` 回填近一年（UI 已标注口径）。
- 历史快照（daily/*.json）只能从启用日开始每日累积；历史日的 10亿以上/市值分档/集中度无法回补（东财快照仅实时可得），序列回补中两市成交额使用沪+深指数代理口径。
- `/liquidity` 市值分档堆叠面积图依赖 `mktcap_buckets` 序列累积，全新部署初期该图为兜底文案。
- 恒生科技用 513180 ETF 成交额近似；微盘代理为全A市值后10%等权自建口径，UI 均标注。
- AKShare 为爬虫源，源站改版可能使个别接口失效；失效模块写 last_error.log 并保留旧数据，不影响其他模块。
- 无盘中实时数据，每日收盘后更新一次；盘中看到的是上一交易日数据（符合设计）。
- Tushare 123 积分仅覆盖非复权日线，仅作个股日线交叉校验；两融/指数/涨跌停均走 AKShare。
- GitHub Actions cron 长期（60天）无仓库活动会被自动禁用，恢复方法见 `docs/DEPLOY.md` 第 6 节。
- 首屏 JSON 请求：meta + latest + daily = 3 个（sparklines 合入 daily，满足 ≤3 约束）。

## V2 扩展点

- 行业严格申万二级映射：提供「east_name,sw_code,sw_name」CSV 后 `--industry-backfill` 一键回填
- 多市场扩展（港股/美股）、盘中快照、用户体系与云端日志同步
- 结论规则引擎阈值 UI 化编辑、自定义推送策略

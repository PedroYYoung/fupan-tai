# -*- coding: utf-8 -*-
"""公告事件的分类、筛选与去重。

原则（客户展示端客观中性，不评价股价）：
- 事件类别只描述事件的客观性质，不构成对股价影响的判断。
- 禁止在自动文案中输出「利好 / 利空 / 推荐 / 看多看空」等交易导向措辞。
- 展示分组（回购 / 风险与监管）仅为便于客户阅读的客观归类。
"""
import hashlib
import re

# 事件类别（客观性质，非投资评价）
CATEGORY_OPERATION = "经营进展"      # 订单、合同、投产、项目进展、中标
CATEGORY_PERFORMANCE = "业绩信息"    # 预增、预减、盈利、亏损、业绩修正
CATEGORY_SHAREHOLDER = "股东行为"    # 增持、减持、质押、股份变动
CATEGORY_CAPITAL = "资本运作"        # 回购、定增、发行、并购、资产重组
CATEGORY_REGULATION = "监管事项"     # 问询、监管措施、纪律处分、行政处罚、立案
CATEGORY_LEGAL = "法律事项"          # 诉讼、仲裁、债务、执行、冻结
CATEGORY_POLICY = "行业政策"         # 行业政策、产业规划、监管规则
CATEGORY_MACRO = "宏观事件"          # 经济数据、货币政策、财政政策、国际事件
CATEGORY_OTHER = "其他信息"

# 展示分组（客观归类）
GROUP_POSITIVE = "positive"   # 积极进展
GROUP_RISK = "risk"           # 风险事项与监管
GROUP_NEUTRAL = "neutral"     # 其他

# verification_status（公告均为官方披露确认）
VERIFY_OFFICIAL = "official_confirmed"
VERIFY_UNVERIFIED = "unverified"


def _match_any(title, words):
    return any(w in title for w in words)


def classify_title(title):
    """根据公告标题关键词返回 (category, group)。"""
    if not title:
        return CATEGORY_OTHER, GROUP_NEUTRAL

    # 经营进展（客观：订单/合同/中标/投产/项目）
    if _match_any(title, ["中标", "签订合同", "重大合同", "订单", "签署协议", "投产", "项目进展",
                          "取得批文", "获得批复", "获批", "取得注册", "对外投资", "设立子公司",
                          "设立孙公司", "战略合作", "合作框架", "合作协议"]):
        return CATEGORY_OPERATION, GROUP_POSITIVE

    # 业绩信息
    if _match_any(title, ["业绩预增", "预增", "扭亏", "盈利预增", "业绩快报", "业绩修正",
                          "业绩预告", "业绩预减", "预减", "预亏", "亏损", "业绩变脸"]):
        if _match_any(title, ["预减", "预亏", "亏损", "业绩变脸", "业绩预减"]):
            return CATEGORY_PERFORMANCE, GROUP_RISK
        return CATEGORY_PERFORMANCE, GROUP_POSITIVE

    # 股东行为：增持/减持/质押/股份变动
    if _match_any(title, ["增持", "减持", "质押", "解质押", "股份变动", "权益变动", "大宗交易",
                          "集中竞价减持", "协议转让"]):
        if _match_any(title, ["减持", "质押", "冻结", "强制平仓"]):
            return CATEGORY_SHAREHOLDER, GROUP_RISK
        if _match_any(title, ["增持", "解质押"]):
            return CATEGORY_SHAREHOLDER, GROUP_POSITIVE
        return CATEGORY_SHAREHOLDER, GROUP_NEUTRAL  # 权益变动等方向不明确，不预设积极/风险

    # 资本运作：回购/定增/发行/并购/重组/股权激励
    if _match_any(title, ["回购", "定向增发", "非公开发行", "公开发行", "可转债", "发行股份",
                          "并购", "重大资产重组", "资产重组", "收购", "股权激励", "配股",
                          "引入战略投资者", "分拆", "吸收合并"]):
        if _match_any(title, ["回购"]):
            return CATEGORY_CAPITAL, GROUP_POSITIVE
        return CATEGORY_CAPITAL, GROUP_NEUTRAL

    # 监管事项：问询/监管/处分/处罚/立案/警示
    if _match_any(title, ["问询函", "监管函", "关注函", "纪律处分", "行政处罚", "立案调查",
                          "警示函", "监管措施", "通报批评", "公开谴责", "责令改正", "监管谈话",
                          "风险提示", "退市风险", "终止上市"]):
        return CATEGORY_REGULATION, GROUP_RISK

    # 法律事项：诉讼/仲裁/债务/执行/担保/冻结
    if _match_any(title, ["诉讼", "仲裁", "债务", "执行", "担保", "冻结", "查封", "破产",
                          "重整", "逾期", "违约", "被申请"]):
        return CATEGORY_LEGAL, GROUP_RISK

    # 行业政策 / 宏观
    if _match_any(title, ["行业政策", "产业规划", "十四五", "监管规则", "管理办法", "指导意见"]):
        return CATEGORY_POLICY, GROUP_NEUTRAL
    if _match_any(title, ["利率", "存款准备金", "LPR", "货币政策", "财政政策", "GDP", "PMI",
                          "CPI", "进出口", "关税"]):
        return CATEGORY_MACRO, GROUP_NEUTRAL

    return CATEGORY_OTHER, GROUP_NEUTRAL


# 例行/低价值公告关键词（不作为重点事件展示）
_ROUTINE_KEYWORDS = [
    # 例行会议与治理
    "董事会", "监事会", "股东大会", "会议决议", "决议公告", "会议通知", "关于召开",
    "独立董事", "法律意见书", "审计报告", "内部控制", "社会责任", "ESG",
    # 例行定期报告全文
    "季度报告", "半年度报告", "年度报告", "年报", "半年报", "一季报", "三季报",
    "定期报告",
    # 债券例行（票面利率/发行结果/兑付/付息）
    "债券", "票面利率", "可续期", "兑付", "付息", "发行结果",
    # 担保（进展公告多为例行）
    "担保",
    # H股 / 月报
    "H股公告", "翌日披露报表", "月报表", "股份变动月报",
    # 人事
    "董监高", "换届", "聘任", "辞任", "辞职", "选举",
    # 停复牌提示
    "停复牌", "复牌提示", "停牌",
]


def is_routine(title):
    """判断是否例行/低价值披露（不适合作为重点事件）。"""
    return _match_any(title or "", _ROUTINE_KEYWORDS)


def make_duplicate_key(sec_code, category, title):
    """去重键：同一公司 + 同一类别 + 归一化标题关键词。

    归一化：去掉数字、日期、标点，保留核心词，用于识别同一事项的多篇转载。
    """
    norm = re.sub(r"[\d年月日\s，。、（）()【】\[\]：:；;\"'\"“”《》]+", "", title or "")
    norm = norm[:40]
    raw = f"{sec_code}|{category}|{norm}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def build_factual_summary(title, company_name):
    """生成客观事实摘要：只陈述「公司公告 + 标题」，不添加任何股价判断。"""
    name = company_name or "公司"
    return f"{name}公告：{title}"


def deduplicate(events):
    """按 duplicate_key 去重，保留首次出现（官方/更早发布时间优先）。"""
    seen = {}
    for e in events:
        key = e.get("duplicate_key") or e.get("event_id")
        if key and key in seen:
            continue
        if key:
            seen[key] = e
    return list(seen.values())

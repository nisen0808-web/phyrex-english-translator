"""Isolated Fed phrasing experiment. No inference, ASR edits or production imports.

The caller supplies the production prompt builder explicitly. Per-source hints
remain in the payload; changing base instructions per chunk loses warm threads.
"""
from __future__ import annotations

import json
import re

REVISION = 'fed-usage-r1'
MARKER = '\n资料 JSON：\n'
MAX_HINTS = 4
MAX_HINT_CHARS = 800
FED_STYLE_INSTRUCTION = (
    '\n采用自然、简明的中文财经口译表达，避免把英语抽象名词逐词硬译。'
    'fed_usage 是当前片段的用法参考，仅在原句确实具备该语义时采用；'
    '不据此改写疑似听写、猜补后文、增加结论或改变语气。'
    '听写歧义仍按原规则标记待核实，不能用顺口的专业措辞掩盖。'
)

# Rules describe distinctions, not replacements. Nothing here rewrites current.
# Patterns gate small relevant notes; the model still resolves the full context.
_RULES = (
    ('growth_moderation',
     r'\b(?:growth|economic activity|spending|wage growth)(?: [a-z]+){0,6} moderat(?:e[ds]?|ing|ion)\b'
     r'|\bmoderat(?:e[ds]?|ing|ion)(?: [a-z]+){0,5} (?:growth|spending|economic activity)\b',
     '增长语境：moderation in growth 为增长放缓；moderate growth / at a moderate pace 为温和增长。'
     'modest 不自动等于放缓。工资或支出增速放缓不等于工资或支出下降；不改写含糊连接词。'),
    ('policy_stance',
     r'\b(?:monetary|policy|stance)(?: [a-z]+){0,6} (?:restrictive|restriction|accommodative|accommodation|neutral)\b'
     r'|\b(?:restrictive|accommodative)(?: [a-z]+){0,3} (?:policy|stance)\b'
     r'|\bmonetary accommodation\b|\bpolicy accommodation\b',
     '货币政策语境：restrictive stance 为限制性政策立场，accommodative / accommodation 为宽松。'
     '减少宽松不自动等于某次加息，仍有限制性不等于将加息；向中性靠近不等于已经中性。保留程度词。'),
    ('inflation_direction',
     r'\b(?:disinflation(?:ary)?|deflation(?:ary)?|inflation expectations)\b',
     'disinflation 为通胀放缓，即物价涨幅下降，不是通缩。deflation 为通缩。'
     '通胀预期与实际通胀分清；appears / may 及否定须保留，不把涨幅放缓译为物价下跌。'),
    ('labor',
     r'\b(?:labor (?:market|demand|supply|force)|labour (?:market|demand|supply|force)|payrolls?|hiring|unemployment|participation rate|employment population ratio)\b',
     'labor demand softening 为劳动力需求减弱，labor market cooling 为劳动力市场降温；'
     '招聘放缓不等于净裁员。劳动参与率、就业人口比率、失业率分母不同；退出劳动力市场不等于失业。'
     '岗位数、就业人数、增速按原文区分，不补写原因或衰退判断。'),
    ('rate_units',
     r'\b(?:basis points?|percentage points?|percent|per cent)\b',
     '百分比是水平或比例，百分点是两个百分比的差，基点是利率变化单位。'
     '区分 by（变动幅度）、to（变动后水平）、from（原水平）；保留区间两端、正负和单位，不擅自算出未说的数。'),
    ('pce',
     r'\bpce\b|\bpersonal consumption expenditures\b',
     'PCE 本义是个人消费支出；PCE price index 为个人消费支出价格指数，PCE inflation 为 PCE 通胀。'
     '实际消费支出增长不是物价上涨。core 只译核心，未说排除项目时不展开解释。'),
    ('measurement_basis',
     r'\b(?:annualized|annualised|year over year|year on year|quarter over quarter|month over month|real gdp|nominal gdp)\b',
     '区分同比、环比、年化增速；annualized 不能译为同比。real / nominal 为实际 / 名义。'
     '按原文时间范围和统计口径翻译，不自行换算。'),
)
_COMPILED = tuple((key, re.compile(pattern), note) for key, pattern, note in _RULES)


def fed_usage_hints(source: str, profile: str = 'fed') -> dict[str, str]:
    """Current-only, bounded hints; prior topic cannot force a finance reading."""
    if profile not in ('fed', 'fomc'):
        return {}
    text = ' '.join(re.findall(r'[a-z0-9]+', source.casefold()))
    selected: dict[str, str] = {}
    for key, pattern, note in _COMPILED:
        if not pattern.search(text):
            continue
        candidate = {**selected, key: note}
        if len(json.dumps(candidate, ensure_ascii=False)) <= MAX_HINT_CHARS:
            selected = candidate
        if len(selected) >= MAX_HINTS:
            break
    return selected


def augment_prompt(prompt: str, profile: str = 'fed') -> str:
    """Wrap an already built prompt; never mutate source, glossary or speaker data."""
    if profile not in ('fed', 'fomc'):
        return prompt
    instruction, payload = prompt.split(MARKER, 1)
    data = json.loads(payload)
    data['fed_usage'] = fed_usage_hints(data['current'], profile)
    return instruction + FED_STYLE_INSTRUCTION + MARKER + json.dumps(data, ensure_ascii=False)


def build_prompt(source, context, glossary, profile='fed', *, base_builder):
    return augment_prompt(base_builder(source, context, glossary, profile), profile)

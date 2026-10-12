"""domain 规则层：第 10 章业务规则 + 第 12.7 条拦截 + 话术模板（全部纯函数）。

这些函数不碰网络、不碰数据库、不 import 任何 SDK，因此可以 100% 单测；
调用方（领域服务 / 应用层 / 兜底链）负责把 I/O 结果喂进来。
"""

from xinglin.domain.rules.answer_template import (
    ASPECT_TEXT,
    DEFAULT_LIMIT,
    dedup_values,
    render_facts,
)
from xinglin.domain.rules.default_intent import (
    SYMPTOM_HINTS,
    default_qa_type,
    has_symptom_expression,
)
from xinglin.domain.rules.diet_rule import (
    DIRECTION_RECOMMEND,
    DIRECTION_RESTRICT,
    RESTRICT_WORDS,
    adjust_food_qa_type,
    judge_diet_direction,
)
from xinglin.domain.rules.insufficiency import INSUFFICIENT_ANSWER, is_insufficient
from xinglin.domain.rules.keyword_intent import KEYWORD_RULES, match_keyword
from xinglin.domain.rules.openness import (
    OPEN_MARKERS,
    SMALL_TALK_MARKERS,
    is_open_ended,
    is_small_talk,
)
from xinglin.domain.rules.query_guard import (
    ILLEGAL_PATTERNS,
    ILLEGAL_REPLY,
    is_illegal_query,
)
from xinglin.domain.rules.risk_notice import (
    RISK_NOTICE,
    TREATMENT_HINTS,
    build_risk_notice,
    needs_risk_notice,
)

__all__ = [
    # 话术模板
    "ASPECT_TEXT", "DEFAULT_LIMIT", "dedup_values", "render_facts",
    # 10.1 宜忌方向
    "DIRECTION_RECOMMEND", "DIRECTION_RESTRICT", "RESTRICT_WORDS",
    "adjust_food_qa_type", "judge_diet_direction",
    # 10.2 默认意图
    "SYMPTOM_HINTS", "default_qa_type", "has_symptom_expression",
    # 10.3 信息不足
    "INSUFFICIENT_ANSWER", "is_insufficient",
    # 10.4 风险提示
    "RISK_NOTICE", "TREATMENT_HINTS", "build_risk_notice", "needs_risk_notice",
    # 共享关键词表
    "KEYWORD_RULES", "match_keyword",
    # FR-024 开放式判定 + 寒暄判定
    "OPEN_MARKERS", "is_open_ended",
    "SMALL_TALK_MARKERS", "is_small_talk",
    # 12.7 非法拦截
    "ILLEGAL_PATTERNS", "is_illegal_query", "ILLEGAL_REPLY",
]

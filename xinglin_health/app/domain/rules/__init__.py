"""domain 规则层：第 10 章业务规则的纯函数实现。"""

from app.domain.rules.default_intent import default_qa_type, has_symptom_expression
from app.domain.rules.diet_rule import (
    DIRECTION_RECOMMEND,
    DIRECTION_RESTRICT,
    adjust_food_qa_type,
    judge_diet_direction,
)
from app.domain.rules.insufficiency import (
    INSUFFICIENT_ANSWER,
    insufficient_reason,
    is_insufficient,
)
from app.domain.rules.query_guard import is_illegal_query
from app.domain.rules.risk_notice import build_risk_notice, needs_risk_notice

__all__ = [
    "DIRECTION_RECOMMEND",
    "DIRECTION_RESTRICT",
    "INSUFFICIENT_ANSWER",
    "adjust_food_qa_type",
    "build_risk_notice",
    "default_qa_type",
    "has_symptom_expression",
    "insufficient_reason",
    "is_illegal_query",
    "is_insufficient",
    "judge_diet_direction",
    "needs_risk_notice",
]

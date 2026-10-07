"""第 10.2 条业务规则：默认问题处理规则（纯函数）。

- 只提供症状、无其他意图 → 优先提供相关疾病信息（症状—疾病）
- 只提供疾病名称、无其他意图 → 优先提供基本描述（疾病—描述）
"""

from app.domain.values import QAType

SYMPTOM_HINTS = (
    "疼", "痛", "痒", "咳嗽", "发烧", "发热", "流鼻涕", "鼻塞", "头晕", "头痛",
    "恶心", "呕吐", "腹泻", "便秘", "乏力", "失眠", "心慌", "胸闷", "气短", "水肿",
    "皮疹", "出血", "麻木", "抽搐", "食欲不振", "消瘦", "多饮", "多尿",
)


def has_symptom_expression(question: str) -> bool:
    """问题中是否出现症状性表述。"""
    return any(w in (question or "") for w in SYMPTOM_HINTS)


def default_qa_type(question: str, entity_type: str | None) -> QAType | None:
    """意图无法明确分类时的默认路由（10.2）。

    返回 None 表示不适用默认规则（交由开放式问答处理）。
    """
    if entity_type == "症状" or (entity_type is None and has_symptom_expression(question)):
        return QAType.SYMPTOM_DISEASE
    if entity_type == "疾病":
        return QAType.DISEASE_DESC
    return None

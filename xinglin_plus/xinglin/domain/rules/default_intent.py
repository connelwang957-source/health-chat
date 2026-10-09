"""第 10.2 条业务规则：默认问题处理规则（纯函数，无 I/O）。

当问题无法明确归入某一固定类型时，按"给了什么、没给什么"给一个安全默认：

- 只提供**症状**（或症状性表述）、别无他意 → 优先给相关疾病（症状—疾病）；
- 只提供**疾病名**、别无他意 → 优先给基本描述（疾病—描述）；
- 其余 → 返回 None，交给开放式问答处理。
"""

from xinglin.domain.values import QAType

# 症状性表述（问题里出现这些词，即使没识别出实体也按"症状"理解）
SYMPTOM_HINTS: tuple[str, ...] = (
    "疼", "痛", "痒", "咳嗽", "发烧", "发热", "流鼻涕", "鼻塞", "头晕", "头痛",
    "恶心", "呕吐", "腹泻", "便秘", "乏力", "失眠", "心慌", "胸闷", "气短", "水肿",
    "皮疹", "出血", "麻木", "抽搐", "食欲不振", "消瘦", "多饮", "多尿",
)


def has_symptom_expression(question: str) -> bool:
    """问题中是否出现症状性表述。"""
    return any(w in (question or "") for w in SYMPTOM_HINTS)


def default_qa_type(question: str, entity_type: str | None) -> QAType | None:
    """意图无法明确分类时的默认路由（10.2）。

    ``entity_type`` 为实体角色中文名（``EntityRole.value``，如「症状」「疾病」）。
    返回 None 表示默认规则不适用，交由开放式问答处理。
    """
    if entity_type == "症状" or (entity_type is None and has_symptom_expression(question)):
        return QAType.SYMPTOM_DISEASE
    if entity_type == "疾病":
        return QAType.DISEASE_DESC
    return None


__all__ = ["SYMPTOM_HINTS", "has_symptom_expression", "default_qa_type"]

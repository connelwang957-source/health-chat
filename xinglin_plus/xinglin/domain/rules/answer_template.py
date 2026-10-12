"""答案话术模板（domain 纯函数）——「事实 → 中文回答」的唯一实现。

两条链路共用同一份话术，避免两套模板漂移：

    ① `fallback/answer_search_v2`（第 1 代规则链，手上已有 `QAType`，措辞精确）；
    ② 生成服务的模板兜底（护栏退回 / LLM 不可用时，只有事实、没有 `QAType`）。

零 LLM、零 I/O，可脱离网络单测。
"""

from xinglin.domain.entities import Fact
from xinglin.domain.values import QAType

# 18 类问答的答案话术（名词短语，拼进「{entity}的{aspect}：{values}」）
ASPECT_TEXT: dict[QAType, str] = {
    QAType.DISEASE_SYMPTOM: "常见症状",
    QAType.SYMPTOM_DISEASE: "可能对应的疾病",
    QAType.DISEASE_CAUSE: "常见病因",
    QAType.DISEASE_PREVENT: "预防措施",
    QAType.DISEASE_TREAT_PERIOD: "治疗周期",
    QAType.DISEASE_TREAT_METHOD: "常见治疗方式",
    QAType.DISEASE_CURE: "治愈相关情况",
    QAType.DISEASE_SUSCEPTIBLE: "易感人群",
    QAType.DISEASE_DESC: "基本介绍",
    QAType.DISEASE_COMPLICATION: "可能的并发症",
    QAType.DISEASE_FOOD_AVOID: "不宜食用的食品",
    QAType.DISEASE_FOOD_RECOMMEND: "推荐食用的食品",
    QAType.FOOD_DISEASE_AVOID: "需要限制该食品的疾病",
    QAType.FOOD_DISEASE_RECOMMEND: "推荐食用该食品的疾病",
    QAType.DISEASE_DRUG: "常用药品",
    QAType.DRUG_DISEASE: "主要针对的疾病",
    QAType.DISEASE_EXAM: "相关检查项目",
    QAType.EXAM_DISEASE: "相关疾病",
    QAType.DISEASE_DEPARTMENT: "就诊科室",
    QAType.DEPARTMENT_DISEASE: "主要诊治的疾病",
}

DEFAULT_LIMIT = 10


def dedup_values(facts: list[Fact], limit: int = DEFAULT_LIMIT) -> list[str]:
    """取事实值：去重保序并截断。"""
    seen: set[str] = set()
    out: list[str] = []
    for f in facts:
        value = (f.value or "").strip()
        if value and value != "None" and value not in seen:
            seen.add(value)
            out.append(value)
    return out[:limit]


def render_facts(entity: str, facts: list[Fact], qa_type: QAType | None = None,
                 limit: int = DEFAULT_LIMIT) -> str:
    """把图谱事实组织成中文回答；无事实返回空串（交由上层降级）。

    - 给出 ``qa_type``（规则链）→ 用 18 类话术，措辞精确；
    - 未给出（模板兜底）→ 按关系分组给出，保证可读。
    """
    values = dedup_values(facts, limit)
    if not values:
        return ""
    joined = "、".join(values)

    # 科室端：用"诊治范围"表述，比「{实体}的{方面}：」更自然
    if qa_type is QAType.DEPARTMENT_DISEASE:
        return f"根据健康知识库，{entity}主要诊治以下疾病：{joined}。"

    # 食品端关系用"限制/推荐"措辞（第 10.1 条方向校正后的类型）
    if qa_type in (QAType.FOOD_DISEASE_AVOID, QAType.FOOD_DISEASE_RECOMMEND):
        relation = "限制" if qa_type is QAType.FOOD_DISEASE_AVOID else "推荐"
        return f"根据健康知识库，{entity}与以下疾病存在饮食{relation}关系：{joined}。"

    if qa_type is not None and (aspect := ASPECT_TEXT.get(qa_type)):
        return f"根据健康知识库，{entity}的{aspect}：{joined}。"

    # 无 QAType：按关系分组
    grouped: dict[str, list[str]] = {}
    for f in facts:
        value = (f.value or "").strip()
        if value and value != "None":
            grouped.setdefault(f.relation, []).append(value)
    if not grouped:
        return ""
    return "\n".join(
        f"根据健康知识库，与「{entity}」相关的{rel}信息包括："
        + "、".join(list(dict.fromkeys(vals))[:limit]) + "。"
        for rel, vals in grouped.items())


__all__ = ["ASPECT_TEXT", "DEFAULT_LIMIT", "dedup_values", "render_facts"]

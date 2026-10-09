"""规则问题分类（第 1 代兜底链，零 LLM、零网络）。

比"纯关键词匹配"多一层能力：**先用词典判定实体角色**，再结合问题里的意图词选类型，
因此「螃蟹不能吃吗」（食品端）与「感冒不能吃什么」（疾病端）能被正确区分——
这是第 1 代流水线相对关键词表的增量价值。

判定顺序：

    ① 实体角色 + 意图词（角色来自词典：Food / Symptom / Drug / Check / Disease …）
    ② 共享关键词表 `domain.rules.match_keyword`（与 LLM 降级通道同一张表）
    ③ 第 10.2 条默认规则（只给症状 → 症状-疾病；只给疾病名 → 疾病描述）
"""

from xinglin.domain.rules import adjust_food_qa_type, default_qa_type, match_keyword
from xinglin.domain.values import EntityRole, QAType

# 词典角色（= 图谱标签）→ 中文业务名，用于第 10.2 条默认规则
LABEL_TO_CN: dict[str, str] = {role.node_label: role.value for role in EntityRole}

# 「询问该角色对应什么疾病」类问题的目标类型
DISEASE_OF_ROLE: dict[str, QAType] = {
    "Symptom": QAType.SYMPTOM_DISEASE,
    "Drug": QAType.DRUG_DISEASE,
    "Check": QAType.EXAM_DISEASE,
}

# 出现这些字眼时才把「药品/检查」理解为「查它对应的疾病」
DISEASE_OF_HINTS: tuple[str, ...] = (
    "哪些疾病", "什么病", "对应", "治疗什么", "治什么", "用于哪些",
    "相关疾病", "可能是什么", "能查出",
)

# 疾病端按属性/关系问法（按顺序命中即用）
DISEASE_INTENT_RULES: tuple[tuple[tuple[str, ...], QAType], ...] = (
    (("症状", "表现"), QAType.DISEASE_SYMPTOM),
    (("并发症", "并发"), QAType.DISEASE_COMPLICATION),
    (("病因", "原因", "引起"), QAType.DISEASE_CAUSE),
    (("预防",), QAType.DISEASE_PREVENT),
    (("周期", "多久"), QAType.DISEASE_TREAT_PERIOD),
    (("治疗", "怎么治"), QAType.DISEASE_TREAT_METHOD),
    (("治愈", "治好"), QAType.DISEASE_CURE),
    (("易感", "人群", "哪些人"), QAType.DISEASE_SUSCEPTIBLE),
    (("检查",), QAType.DISEASE_EXAM),
    (("药",), QAType.DISEASE_DRUG),
)

# 出现这些字眼时，把问题理解为「饮食关系」
FOOD_HINTS: tuple[str, ...] = ("吃", "食", "忌口", "饮食", "喝")

# 非疾病角色：问「某物对应什么疾病」时，锚点应优先取它们
NON_DISEASE_ROLES: tuple[str, ...] = ("Symptom", "Drug", "Food", "Check")


def preferred_roles(question: str) -> tuple[str, ...] | None:
    """按问题意图给出「优先匹配的角色」。

    医学图谱里存在**同名节点跨角色**（例如「咳嗽」既是 Disease 也是 Symptom）。
    当问题问的是「某物对应什么疾病」时，锚点显然不是疾病本身，
    因此优先在非疾病角色里找实体，避免「咳嗽」被当成疾病去做疾病—描述查询。
    """
    q = question or ""
    if any(h in q for h in DISEASE_OF_HINTS):
        return NON_DISEASE_ROLES
    return None


def classify(question: str, entity: str | None, role: str | None,
             denied: bool = False) -> QAType | None:
    """规则判定问答类型；无法判定返回 None（交由上层降级 / 兜底）。

    ``denied``：问题是否含否定 / 限制表述（由词典的否定词表判定后传入，保持本函数纯函数）。
    """
    q = question or ""

    # ① 实体角色优先
    if role == "Food":
        qa_type = QAType.FOOD_DISEASE_AVOID if denied else QAType.FOOD_DISEASE_RECOMMEND
        return adjust_food_qa_type(q, qa_type)
    if role in DISEASE_OF_ROLE:
        target = DISEASE_OF_ROLE[role]
        if role == "Symptom" or any(h in q for h in DISEASE_OF_HINTS):
            return target
    if role == "Disease":
        if any(h in q for h in FOOD_HINTS):            # 疾病端饮食问法（10.1 定方向）
            qa_type = QAType.DISEASE_FOOD_AVOID if denied else QAType.DISEASE_FOOD_RECOMMEND
            return adjust_food_qa_type(q, qa_type)
        for keywords, qa_type in DISEASE_INTENT_RULES:
            if any(k in q for k in keywords):
                return adjust_food_qa_type(q, qa_type)
        return QAType.DISEASE_DESC                     # 只给疾病名 → 10.2 描述

    # ② 共享关键词表（与 LLM 降级通道一致，避免两套规则漂移）
    if (matched := match_keyword(q)) is not None:
        return adjust_food_qa_type(q, matched[0])

    # ③ 第 10.2 条默认规则
    return default_qa_type(q, LABEL_TO_CN.get(role or ""))


__all__ = ["classify", "preferred_roles", "DISEASE_OF_ROLE", "DISEASE_INTENT_RULES",
           "LABEL_TO_CN", "FOOD_HINTS", "NON_DISEASE_ROLES"]

"""领域值对象与枚举（纯数据，无 I/O）。

- ``EntityRole``：健康对象角色 ↔ 图谱节点标签（FR-002）；
- ``Mode``：一次问答**实际走通**的检索通路；
- ``Reliability`` / ``SourceType``：FR-022/023 的来源标识与可靠性分级；
- ``QAType``：**第 9 章固定问答类型的唯一事实源**（挂载 Cypher 模板元数据）。

> **关于「药品厂商」（FR-002 的 7 类健康对象之一）**：既有 `medical` 库的数据不可用——
> ``Producer`` 节点名是「厂商 + 药名」的拼接串（如「999华蟾素口服液」，共 17201 条），
> 且 ``drugs_of`` 关系只有 251 条并指向**同名节点**（药名 == 厂商名）。
> 因此本枚举**暂不声明** ``PRODUCER``，词典侧也不加载 ``producer.txt``：
> 那些脏名字**更长**，在「最长优先匹配」里会压过正确实体
> （实测「太极阿胶能吃吗」被识别成 Producer，而非食品「阿胶」）。
> 待数据修复（根因是 `build_graph.parse_drug_detail` 的括号内外配对颠倒）后再启用。
"""

from enum import Enum


class EntityRole(str, Enum):
    """健康对象角色。value 为中文业务名（对用户/意图识别可见），node_label 为图谱真实标签。"""

    DISEASE = "疾病"
    SYMPTOM = "症状"
    DRUG = "药品"
    FOOD = "食品"
    EXAM = "检查"
    DEPARTMENT = "科室"

    @property
    def node_label(self) -> str:
        """已校准：与 medical 库实际标签一致。

        覆盖 Disease / Symptom / Drug / Food / Check / Department。
        末端追加的 ``DEPARTMENT`` 是需求 14.7 的科室数据（`belongs_to` 关系，
        实测覆盖 8807/8808 疾病），用于「疾病→就诊科室 / 科室→诊治疾病」两类问答。
        """
        return {
            EntityRole.DISEASE: "Disease",
            EntityRole.SYMPTOM: "Symptom",
            EntityRole.DRUG: "Drug",
            EntityRole.FOOD: "Food",
            EntityRole.EXAM: "Check",
            EntityRole.DEPARTMENT: "Department",
        }[self]

    @classmethod
    def from_node_label(cls, label: str | None) -> "EntityRole | None":
        """图谱标签 → 角色（英文标签转中文业务名；未识别返回 None）。"""
        if not label:
            return None
        return next((r for r in cls if r.node_label == label), None)


class Mode(str, Enum):
    """检索通路（系统自选，FR-024；用户不可指定）。"""

    DIRECT = "direct"     # 不检索，直接回答（寒暄/常识）
    KG = "kg"             # 知识图谱
    RAG = "rag"           # 文献检索
    HYBRID = "hybrid"     # 双路召回


class Reliability(str, Enum):
    """回答可靠性分级（FR-023）。"""

    HIGH = "high"         # 仅结构化知识，依据充分
    PARTIAL = "partial"   # 含文献或多来源综合
    LOW = "low"           # 无检索依据 / 依据不足


class SourceType(str, Enum):
    """来源类型（FR-022：每条来源必须标注类型）。"""

    KG = "kg"             # 结构化知识
    LIT = "lit"           # 医学文献

    @property
    def label(self) -> str:
        return {SourceType.KG: "结构化知识", SourceType.LIT: "医学文献"}[self]


class QAType(Enum):
    """固定问答类型（路由与 KG 查询的唯一依据）。

    **第 9 章的 18 类**逐条对应（编号 1~18）；编号 19~20 是需求 14.7「科室数据」的扩展——
    该章要求"科室名称 + 相关疾病"，原 18 类未覆盖。需求原文是"**至少**支持以下 18 类"，
    因此扩展不与之冲突。

    ``kind``：property=读节点属性 ｜ relation=正向关系 ｜ reverse=反向关系
    ``source_role``：问题中给定实体的角色（Cypher 锚点节点）
    ``key``：关系类型或属性名
    ``target_role``：关系指向的节点角色
    """

    # ---- 第 9 章 1~18 ----
    DISEASE_SYMPTOM = (1, "疾病—症状", "查询疾病有哪些症状", EntityRole.DISEASE, "relation", "has_symptom", EntityRole.SYMPTOM)
    SYMPTOM_DISEASE = (2, "症状—疾病", "查询某症状可能对应哪些疾病", EntityRole.SYMPTOM, "reverse", "has_symptom", EntityRole.DISEASE)
    DISEASE_CAUSE = (3, "疾病—病因", "查询疾病产生的原因", EntityRole.DISEASE, "property", "cause", None)
    DISEASE_PREVENT = (4, "疾病—预防", "查询疾病如何预防", EntityRole.DISEASE, "property", "prevent", None)
    DISEASE_TREAT_PERIOD = (5, "疾病—治疗周期", "查询疾病治疗通常需要多长时间", EntityRole.DISEASE, "property", "cure_lasttime", None)
    DISEASE_TREAT_METHOD = (6, "疾病—治疗方式", "查询疾病如何治疗", EntityRole.DISEASE, "property", "cure_way", None)
    DISEASE_CURE = (7, "疾病—治愈相关", "查询疾病治愈概率等信息", EntityRole.DISEASE, "property", "cure_prob", None)
    DISEASE_SUSCEPTIBLE = (8, "疾病—易感人群", "查询哪些人容易患该疾病", EntityRole.DISEASE, "property", "easy_get", None)
    DISEASE_DESC = (9, "疾病—描述", "查询疾病基本信息", EntityRole.DISEASE, "property", "desc", None)
    # ⚠ 关系名是 `acompany_with`（**不是** accompany_with）：沿用源数据 `medical.json`
    # 的字段名 `acompany`，图谱里就是这么建的。写错一个字母，模板查询会永远查空
    # —— 这条由 `tests/test_graph_schema.py` 与 schema 的一致性断言守住。
    DISEASE_COMPLICATION = (10, "疾病—并发症", "查询疾病可能产生的并发症", EntityRole.DISEASE, "relation", "acompany_with", EntityRole.DISEASE)
    DISEASE_FOOD_AVOID = (11, "疾病—忌吃食品", "查询患病后不适合食用的食品", EntityRole.DISEASE, "relation", "no_eat", EntityRole.FOOD)
    DISEASE_FOOD_RECOMMEND = (12, "疾病—宜吃食品", "查询患病后适合食用的食品", EntityRole.DISEASE, "relation", "do_eat", EntityRole.FOOD)
    FOOD_DISEASE_AVOID = (13, "食品—疾病（限制）", "查询某食品与哪些疾病存在限制关系", EntityRole.FOOD, "reverse", "no_eat", EntityRole.DISEASE)
    FOOD_DISEASE_RECOMMEND = (14, "食品—疾病（推荐）", "查询某食品与哪些疾病存在推荐关系", EntityRole.FOOD, "reverse", "do_eat", EntityRole.DISEASE)
    DISEASE_DRUG = (15, "疾病—药品", "查询疾病相关药品", EntityRole.DISEASE, "relation", "recommand_drug", EntityRole.DRUG)
    DRUG_DISEASE = (16, "药品—疾病", "查询药品主要用于哪些疾病", EntityRole.DRUG, "reverse", "recommand_drug", EntityRole.DISEASE)
    DISEASE_EXAM = (17, "疾病—检查", "查询疾病相关检查项目", EntityRole.DISEASE, "relation", "need_check", EntityRole.EXAM)
    EXAM_DISEASE = (18, "检查—疾病", "查询某检查可能对应的疾病", EntityRole.EXAM, "reverse", "need_check", EntityRole.DISEASE)

    # ---- 科室扩展（需求 14.7；图谱 belongs_to 关系，覆盖 8807/8808 疾病）----
    DISEASE_DEPARTMENT = (19, "疾病—科室", "查询疾病应该去哪个科室就诊", EntityRole.DISEASE, "relation", "belongs_to", EntityRole.DEPARTMENT)
    DEPARTMENT_DISEASE = (20, "科室—疾病", "查询某科室主要诊治哪些疾病", EntityRole.DEPARTMENT, "reverse", "belongs_to", EntityRole.DISEASE)

    def __init__(self, code: int, cn_name: str, intent: str,
                 source_role: EntityRole, kind: str, key: str,
                 target_role: EntityRole | None):
        self.code = code
        self.cn_name = cn_name
        self.intent = intent
        self.source_role = source_role
        self.kind = kind
        self.key = key
        self.target_role = target_role

    @classmethod
    def by_code(cls, code: int | None) -> "QAType | None":
        if code is None:
            return None
        for t in cls:
            if t.code == code:
                return t
        raise ValueError(f"未知的固定问答类型编号: {code}")

    @classmethod
    def food_types(cls) -> tuple["QAType", ...]:
        """涉及疾病-食品关系的 4 类（第 10.1 条宜忌判定作用对象）。"""
        return (cls.DISEASE_FOOD_AVOID, cls.DISEASE_FOOD_RECOMMEND,
                cls.FOOD_DISEASE_AVOID, cls.FOOD_DISEASE_RECOMMEND)


__all__ = ["EntityRole", "Mode", "Reliability", "SourceType", "QAType"]

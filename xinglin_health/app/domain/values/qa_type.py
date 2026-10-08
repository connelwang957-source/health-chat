"""QAType：第 9 章定义的 18 类固定问答类型（领域枚举，路由与 KG 查询的唯一依据）。

✅ 已对齐实际 KG（medical 库，liuhuanyong 医疗知识图谱模式）：
  标签 Disease/Symptom/Drug/Food/Check/Department/Producer
  关系 has_symptom/acompany_with/no_eat/do_eat/recommand_drug/need_check/belongs_to
  属性 cause/prevent/cure_lasttime/cure_way/cure_prob/easy_get/desc
"""

from enum import Enum

from app.domain.values.entities_role import EntityRole


class QAType(Enum):
    """18 类固定问答。

    kind: property=读取节点属性 | relation=正向关系 | reverse=反向关系
    source_role: 用户问题中给定实体的角色（Cypher 里的锚点节点）
    key: 关系类型或属性名
    target_role: 关系指向的节点角色
    """

    DISEASE_SYMPTOM = (1, "疾病—症状", "查询疾病有哪些症状", EntityRole.DISEASE, "relation", "has_symptom", EntityRole.SYMPTOM)
    SYMPTOM_DISEASE = (2, "症状—疾病", "查询某症状可能对应哪些疾病", EntityRole.SYMPTOM, "reverse", "has_symptom", EntityRole.DISEASE)
    DISEASE_CAUSE = (3, "疾病—病因", "查询疾病产生的原因", EntityRole.DISEASE, "property", "cause", None)
    DISEASE_PREVENT = (4, "疾病—预防", "查询疾病如何预防", EntityRole.DISEASE, "property", "prevent", None)
    DISEASE_TREAT_PERIOD = (5, "疾病—治疗周期", "查询疾病治疗通常需要多长时间", EntityRole.DISEASE, "property", "cure_lasttime", None)
    DISEASE_TREAT_METHOD = (6, "疾病—治疗方式", "查询疾病如何治疗", EntityRole.DISEASE, "property", "cure_way", None)
    DISEASE_CURE = (7, "疾病—治愈相关", "查询疾病治愈概率等信息", EntityRole.DISEASE, "property", "cure_prob", None)
    DISEASE_SUSCEPTIBLE = (8, "疾病—易感人群", "查询哪些人容易患该疾病", EntityRole.DISEASE, "property", "easy_get", None)
    DISEASE_DESC = (9, "疾病—描述", "查询疾病基本信息", EntityRole.DISEASE, "property", "desc", None)
    DISEASE_COMPLICATION = (10, "疾病—并发症", "查询疾病可能产生的并发症", EntityRole.DISEASE, "relation", "acompany_with", EntityRole.DISEASE)
    DISEASE_FOOD_AVOID = (11, "疾病—忌吃食品", "查询患病后不适合食用的食品", EntityRole.DISEASE, "relation", "no_eat", EntityRole.FOOD)
    DISEASE_FOOD_RECOMMEND = (12, "疾病—宜吃食品", "查询患病后适合食用的食品", EntityRole.DISEASE, "relation", "do_eat", EntityRole.FOOD)
    FOOD_DISEASE_AVOID = (13, "食品—疾病（限制）", "查询某食品与哪些疾病存在限制关系", EntityRole.FOOD, "reverse", "no_eat", EntityRole.DISEASE)
    FOOD_DISEASE_RECOMMEND = (14, "食品—疾病（推荐）", "查询某食品与哪些疾病存在推荐关系", EntityRole.FOOD, "reverse", "do_eat", EntityRole.DISEASE)
    DISEASE_DRUG = (15, "疾病—药品", "查询疾病相关药品", EntityRole.DISEASE, "relation", "recommand_drug", EntityRole.DRUG)
    DRUG_DISEASE = (16, "药品—疾病", "查询药品主要用于哪些疾病", EntityRole.DRUG, "reverse", "recommand_drug", EntityRole.DISEASE)
    DISEASE_EXAM = (17, "疾病—检查", "查询疾病相关检查项目", EntityRole.DISEASE, "relation", "need_check", EntityRole.EXAM)
    EXAM_DISEASE = (18, "检查—疾病", "查询某检查可能对应的疾病", EntityRole.EXAM, "reverse", "need_check", EntityRole.DISEASE)

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

"""健康对象角色（FR-002：系统可能识别的主要健康对象）。

value 为中文业务名（对用户/意图识别可见）；node_label 为已建 KG 的真实节点标签
（已对齐：medical 库，英文标签）。
"""

from enum import Enum


class EntityRole(str, Enum):
    DISEASE = "疾病"
    SYMPTOM = "症状"
    DRUG = "药品"
    FOOD = "食品"
    EXAM = "检查"

    @property
    def node_label(self) -> str:
        """已校准：与 medical 库实际标签一致（Disease/Symptom/Drug/Food/Check）。"""
        return {
            EntityRole.DISEASE: "Disease",
            EntityRole.SYMPTOM: "Symptom",
            EntityRole.DRUG: "Drug",
            EntityRole.FOOD: "Food",
            EntityRole.EXAM: "Check",
        }[self]

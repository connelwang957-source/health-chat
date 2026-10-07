"""健康对象角色（FR-002：系统可能识别的主要健康对象）。

值即 Neo4j 节点标签【待对齐】：假设 KG 节点标签与中文名一致。
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
        """KG 节点标签【待对齐】。"""
        return self.value

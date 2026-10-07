"""来源类型（FR-022/FR-023）：回答引用信息时必须标识。"""

from enum import Enum


class SourceType(str, Enum):
    KG = "kg"    # 结构化知识（知识图谱）
    LIT = "lit"  # 医学文献

    @property
    def label(self) -> str:
        return "结构化知识" if self is SourceType.KG else "医学文献"

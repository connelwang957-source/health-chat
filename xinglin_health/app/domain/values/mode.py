"""检索模式（FR-024）：系统自动选择，咨询人员不可指定。"""

from enum import Enum


class Mode(str, Enum):
    DIRECT = "direct"    # 直接回答，不查询资料
    KG = "kg"            # 仅查询结构化知识（知识图谱）
    RAG = "rag"          # 仅查询医学资料（文献检索）
    HYBRID = "hybrid"    # 混合检索（结构化知识与医学资料综合）

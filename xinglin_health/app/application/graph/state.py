"""LangGraph 主图状态（GraphState）。"""

from typing import TypedDict

from langchain_core.documents import Document

from app.domain.entities import Answer, Fact, Intent
from app.domain.values import Mode


class GraphState(TypedDict, total=False):
    question: str
    normalized: str
    intent: Intent | None
    mode: Mode | None
    rejected: bool                     # 12.7 非法查询拦截
    kg_facts: list[Fact]
    kg_failed: bool                    # KG 通路失败/查空
    lit_docs: list[Document] | list[dict]
    lit_failed: bool                   # RAG 通路失败/查空
    answer: Answer | None
    reliability_done: bool
    retries: int                       # FR-026 备用处理计数（≤2）
    tried_modes: list[str]             # 已尝试过的检索模式
    fallback_done: bool                # 备用处理终止信号
    notes: list[str]                   # 降级/路由说明（进入响应 meta）

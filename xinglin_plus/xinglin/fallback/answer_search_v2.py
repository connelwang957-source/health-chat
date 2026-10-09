"""查询执行与答案组织（第 1 代兜底链，对应文档的 `answer_search_v2`）。

零 LLM：图谱结果按 `QAType` 的话术组织成中文回答，保证**任何模型都不可用时图谱通路仍可读**
（降级链的最后一环）。

本模块只负责"执行 + 转发"：Fact 转换复用 `domain.services.rows_to_facts`，
话术复用 `domain.rules.render_facts` —— 三处口径统一，不会各写一套。
"""

from xinglin.domain.entities import Fact
from xinglin.domain.ports import GraphStore
from xinglin.domain.rules import render_facts
from xinglin.domain.services import rows_to_facts
from xinglin.domain.values import QAType

DEFAULT_LIMIT = 10


class AnswerSearchV2:
    """执行参数化 Cypher → Fact 列表 → 模板化中文回答。"""

    def __init__(self, graph: GraphStore, limit: int = DEFAULT_LIMIT):
        self._graph = graph
        self._limit = limit

    def search(self, cypher: str, params: dict | None = None) -> list[Fact]:
        rows = self._graph.query(cypher, params or {})
        entity = (params or {}).get("entity", "")
        return rows_to_facts(rows, entity, "kg")

    def render(self, entity: str, qa_type: QAType | None, facts: list[Fact]) -> str:
        """把事实组织成中文回答；无事实返回空串（交由上层降级）。"""
        return render_facts(entity, facts, qa_type, self._limit)


__all__ = ["AnswerSearchV2", "DEFAULT_LIMIT"]

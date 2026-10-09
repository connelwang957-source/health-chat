"""RAGAgent：文献召回 + 生成（对应文档 §5.4 的 `application/rag_agent.py`）。

薄编排：`chat_main` 只做"召回 → 生成 → 收尾"三件事，所有业务能力都在 domain。
检索组件不可用时**不抛错**，退化为无依据回答（由上层护栏与降级链处理）。
"""

import logging

from xinglin.application.runtime import (
    finalize_answer,
    get_generation_service,
    get_intent_service,
    get_retrieval_service,
)
from xinglin.domain.entities import Answer
from xinglin.domain.values import Mode

logger = logging.getLogger(__name__)


class RAGAgent:
    """仅走文献通路的问答 Agent。"""

    def __init__(self, intent=None, retrieval=None, generation=None):
        self._intent = intent or get_intent_service()
        self._retrieval = retrieval or get_retrieval_service()
        self._generation = generation or get_generation_service()

    # -- 给 HybridAgent 复用的取证据接口 --------------------------------------
    def collect_docs(self, question: str, k: int | None = None) -> list[dict]:
        """文献路取证据（失败只降级为空，不阻断）。"""
        try:
            return self._retrieval.retrieve(question, k)
        except Exception as e:      # noqa: BLE001 —— 12.2 检索失败降级
            logger.warning("文献检索失败（已降级）: %s", e)
            return []

    def recall(self, question: str, k: int | None = None) -> str:
        """文献召回，返回**拼接好的上下文文本**（文档 §7.3.1 的 `RAGAgent.recall`）。

        每个片段都带「来源文件 + 页码」——文档 §11.1.8：健康 RAG 必须保留出处，
        可追溯、可审计。ReAct 工具需要结构化证据时用 `collect_docs`。
        """
        docs = self.collect_docs(question, k)
        blocks: list[str] = []
        for i, d in enumerate(docs, start=1):
            meta = d.get("metadata") or {}
            source = meta.get("doc_title") or meta.get("source") or "未知文献"
            page = meta.get("page_num") if meta.get("page_num") is not None else meta.get("page")
            loc = f"，第{page}页" if page is not None else ""
            blocks.append(f"【{i}】(来源：{source}{loc})\n{d.get('text', '')}")
        return "\n\n".join(blocks)

    # -- 主入口 -------------------------------------------------------------
    def chat_main(self, question: str) -> Answer:
        docs = self.collect_docs(question)
        answer = self._generation.generate(question, Mode.RAG, [], docs)
        return finalize_answer(question, answer, [], docs)


__all__ = ["RAGAgent"]

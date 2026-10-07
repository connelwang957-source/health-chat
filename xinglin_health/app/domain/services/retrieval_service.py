"""RetrievalService：文献混合检索（领域服务）。

封装 LangChain EnsembleRetriever（Milvus 稠密 + BM25 稀疏，内置 RRF）。
infrastructure 不可用时不抛出到图外，由 availability 标记 + 节点降级处理。
"""

from langchain_core.documents import Document


class RetrievalUnavailable(Exception):
    """文献检索通路不可用（12.2：尝试其他可用信息来源）。"""


class RetrievalService:
    def __init__(self, ensemble_retriever=None):
        self._retriever = ensemble_retriever  # LangChain EnsembleRetriever | None

    @property
    def available(self) -> bool:
        return self._retriever is not None

    def retrieve(self, question: str, top_k: int = 8) -> list[dict]:
        """返回 [{text, metadata}]，metadata 含 doc_title/page_num 等定位信息。"""
        if not self.available:
            raise RetrievalUnavailable("文献检索组件未就绪（Milvus/BM25 未就绪）")
        docs: list[Document] = self._retriever.invoke(question)[:top_k]
        return [{"text": d.page_content, "metadata": dict(d.metadata or {})} for d in docs]

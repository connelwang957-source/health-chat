"""RetrievalService：文献混合检索（domain 领域服务，经 `LiteratureSearch` 端口）。

只做三件事：可用性判定、top-k 兜底、把"组件不可用"翻译成领域异常，
让上层（应用层）能据此走降级链，而不是让第三方异常一路冒泡。
"""

from xinglin.config import RETRIEVAL_TOP_K
from xinglin.domain.ports import LiteratureSearch


class RetrievalUnavailable(Exception):
    """文献检索组件不可用（Milvus / BM25 未就绪）。"""


class RetrievalService:
    def __init__(self, search: LiteratureSearch, top_k: int = RETRIEVAL_TOP_K):
        self._search = search
        self._top_k = top_k

    @property
    def available(self) -> bool:
        return self._search is not None and getattr(self._search, "available", False)

    def retrieve(self, question: str, k: int | None = None) -> list[dict]:
        """返回 ``[{"text": ..., "metadata": {...}}, ...]``（纯 dict，不外泄 langchain 类型）。"""
        if not self.available:
            raise RetrievalUnavailable("文献检索组件未就绪（Milvus/BM25 未就绪）")
        return self._search.search(question, k or self._top_k)


__all__ = ["RetrievalService", "RetrievalUnavailable"]

"""混合检索（infrastructure）：langchain EnsembleRetriever（内置 RRF）。

可用路由：
  - Milvus 稠密 + BM25 稀疏 → EnsembleRetriever（两路 RRF 融合）
  - 仅其中一路可用 → 直接用单路
  - 全部不可用 → None（RAG 通路降级，12.2）
"""

import logging
from functools import lru_cache

from app.infrastructure.bm25_store import get_bm25_retriever
from app.infrastructure.config import get_settings
from app.infrastructure.milvus_retriever import get_milvus_retriever

logger = logging.getLogger(__name__)


@lru_cache
def get_ensemble_retriever():
    k = get_settings().retrieval_top_k
    retrievers, names = [], []
    if (r := get_milvus_retriever(k)) is not None:
        retrievers.append(r)
        names.append("milvus")
    if (r := get_bm25_retriever(k)) is not None:
        retrievers.append(r)
        names.append("bm25")

    if not retrievers:
        logger.warning("无任何可用检索路，RAG 通路降级")
        return None
    if len(retrievers) == 1:
        logger.info("混合检索退化为单路: %s", names[0])
        return retrievers[0]

    from langchain.retrievers import EnsembleRetriever
    logger.info("EnsembleRetriever 就绪: %s（内置 RRF 融合）", "+".join(names))
    return EnsembleRetriever(retrievers=retrievers, weights=[0.6, 0.4])

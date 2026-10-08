"""混合检索（infrastructure）：langchain EnsembleRetriever（内置 RRF）。

稠密路优先级：
  1. Milvus（生产形态，需 Docker）
  2. InMemoryVectorStore（演示/开发回退：直接用 data/bm25_docs.json 语料 +
     本地向量化模型内存构建，无需 Docker——19 篇量级秒级建库）
稀疏路：BM25 内存索引。
两路都可用 → EnsembleRetriever（内置 RRF 融合）；单路可用 → 直接单路；全不可用 → None。
"""

import json
import logging
from functools import lru_cache
from pathlib import Path

from app.infrastructure.bm25_store import get_bm25_retriever
from app.infrastructure.config import get_settings
from app.infrastructure.milvus_retriever import get_milvus_retriever

logger = logging.getLogger(__name__)


def _inmemory_dense_retriever(k: int):
    """无 Milvus 时的稠密检索回退：内存向量库（同一段语料、同一 Embedding 模型）。"""
    try:
        from langchain_core.documents import Document
        from langchain_core.vectorstores import InMemoryVectorStore

        from app.infrastructure.embedder import get_embeddings
        path = Path(get_settings().bm25_docs_path)
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        docs = [Document(page_content=d["text"], metadata=d.get("metadata", {})) for d in raw]
        vs = InMemoryVectorStore(embedding=get_embeddings())
        vs.add_documents(docs)
        logger.info("内存稠密索引构建完成: %d chunks", len(docs))
        return vs.as_retriever(search_kwargs={"k": k})
    except Exception as e:  # noqa: BLE001
        logger.warning("内存稠密检索不可用: %s", e)
        return None


@lru_cache
def get_ensemble_retriever():
    k = get_settings().retrieval_top_k
    retrievers, names = [], []

    dense = get_milvus_retriever(k) or _inmemory_dense_retriever(k)
    if dense is not None:
        retrievers.append(dense)
        names.append("milvus" if get_milvus_retriever(k) else "inmemory-dense")
    if (r := get_bm25_retriever(k)) is not None:
        retrievers.append(r)
        names.append("bm25")

    if not retrievers:
        logger.warning("无任何可用检索路，RAG 通路降级")
        return None
    if len(retrievers) == 1:
        logger.info("混合检索退化为单路: %s", names[0])
        return retrievers[0]

    from langchain_classic.retrievers import EnsembleRetriever
    logger.info("EnsembleRetriever 就绪: %s（内置 RRF 融合）", "+".join(names))
    return EnsembleRetriever(retrievers=retrievers, weights=[0.6, 0.4])

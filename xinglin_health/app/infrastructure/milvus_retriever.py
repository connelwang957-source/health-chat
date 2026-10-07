"""Milvus 稠密检索器（infrastructure）：经 langchain-milvus 接入。

惰性构建；Embedder 或 Milvus 不可用时返回 None（RAG 通路降级，12.2）。
"""

import logging
from functools import lru_cache

from app.infrastructure.config import get_settings

logger = logging.getLogger(__name__)


class MilvusUnavailable(Exception):
    pass


def _build(k: int):
    from langchain_milvus import Milvus

    from app.infrastructure.embedder import get_embeddings
    s = get_settings()
    vs = Milvus(
        embedding_function=get_embeddings(),
        collection_name=s.milvus_collection,
        connection_args={"uri": s.milvus_uri},
        auto_id=True,
    )
    return vs.as_retriever(search_kwargs={"k": k})


@lru_cache
def get_milvus_retriever(k: int = 8):
    """返回 LangChain Retriever；不可用返回 None（调用方降级）。"""
    try:
        retriever = _build(k)
        _ = retriever.invoke("健康")[:0]  # 触发一次连接校验（取0条不产生实际检索开销）
        return retriever
    except Exception as e:  # noqa: BLE001 —— Milvus 未启动/Embedder 未装 → 降级
        logger.warning("Milvus retriever unavailable: %s", e)
        return None


def milvus_health() -> bool:
    try:
        from pymilvus import connections, utility

        from app.infrastructure.config import get_settings as gs
        c = gs()
        connections.connect(alias="health_check", uri=c.milvus_uri, timeout=2)
        utility.list_collections(using="health_check")
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        try:
            from pymilvus import connections
            connections.disconnect("health_check")
        except Exception:  # noqa: BLE001
            pass

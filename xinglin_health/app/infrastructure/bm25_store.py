"""BM25 稀疏检索（infrastructure）：langchain-community BM25Retriever + jieba 中文分词。

语料为 19 篇量级，启动时从 data/bm25_docs.json 全量内存重建（毫秒级）；
该文件由 scripts/ingest_docs.py 在入库时同步产出。语料到万篇级后演进为
Milvus sparse 混合检索（接口不变，见技术文档 6.2 演进路径）。
"""

import json
import logging
from functools import lru_cache
from pathlib import Path

from app.infrastructure.config import get_settings

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> list[str]:
    import jieba
    return [t for t in jieba.cut_for_search(text) if t.strip()]


@lru_cache
def get_bm25_retriever(k: int = 8):
    """返回 BM25Retriever；语料文件缺失时返回 None。"""
    path = Path(get_settings().bm25_docs_path)
    if not path.exists():
        logger.warning("BM25 语料文件不存在（先运行 scripts/ingest_docs.py）: %s", path)
        return None
    try:
        from langchain_community.retrievers import BM25Retriever
        from langchain_core.documents import Document

        raw = json.loads(path.read_text(encoding="utf-8"))
        docs = [Document(page_content=d["text"], metadata=d.get("metadata", {})) for d in raw]
        retriever = BM25Retriever.from_documents(docs, preprocess_func=_tokenize, k=k)
        logger.info("BM25 index rebuilt: %d chunks", len(docs))
        return retriever
    except Exception as e:  # noqa: BLE001
        logger.warning("BM25 retriever unavailable: %s", e)
        return None

"""domain/rag：向量检索能力（本地 HuggingFace 嵌入 + 既有 Milvus 集合检索）。

对应《项目开发指导》§4.2/§4.4 的 `domain/rag/{embeddings,vectorstore}.py`。

**数据形态**：直连既有 Milvus 集合 ``medical_lit``（762 条切片，已就绪），
不重新切片/灌库；稀疏路 BM25 语料由 `export_bm25_docs_from_milvus` 从同一集合导出。
"""

from xinglin.domain.rag.embeddings import create_embeddings
from xinglin.domain.rag.vectorstore import (
    DENSE_INDEX,
    META_KEYS,
    META_MAP,
    PK_FIELD,
    TEXT_FIELD,
    VECTOR_FIELD,
    VECTOR_FIELDS,
    HybridRetriever,
    MilvusVectorStore,
    export_bm25_docs,
    export_bm25_docs_from_milvus,
    normalize_metadata,
    prepare_documents,
)

__all__ = [
    "create_embeddings", "MilvusVectorStore", "HybridRetriever",
    "prepare_documents", "export_bm25_docs", "export_bm25_docs_from_milvus",
    "normalize_metadata", "META_KEYS", "META_MAP",
    "DENSE_INDEX", "VECTOR_FIELDS", "TEXT_FIELD", "PK_FIELD", "VECTOR_FIELD",
]

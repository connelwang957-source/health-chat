"""本地向量模型工厂（对应《项目开发指导》§4.4 的 `xinglin/infrastructure/embeddings.py`）。

本项目沿用**自有的 HuggingFace 模型**（384 维多语言 MiniLM，已在本机 HF 缓存），
不用 BGE-M3；离线加载，避免联网与版本漂移。

`encode_kwargs={"normalize_embeddings": True}` 让向量归一化，
于是 Milvus 侧的 IP（内积）打分等价于余弦相似度。
"""

import os
from functools import lru_cache

from xinglin.config import EMBEDDING_DIM, EMBEDDING_MODEL, HF_HUB_OFFLINE


@lru_cache
def create_embeddings():
    """创建句向量模型（进程内单例）。

    供 `domain/rag/vectorstore.py` 的建库与检索共用。
    """
    if HF_HUB_OFFLINE:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


__all__ = ["create_embeddings", "EMBEDDING_DIM"]

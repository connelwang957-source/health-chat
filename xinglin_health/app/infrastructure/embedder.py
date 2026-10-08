"""Embedder（infrastructure）：BGE-M3 本地向量化，经 langchain-huggingface。

torch/sentence-transformers 体积大，惰性导入；未安装时报告不可用（RAG 通路降级，
KG 通路与 LLM 通路不受影响）。安装：pip install langchain-huggingface sentence-transformers
"""

import logging
from functools import lru_cache

from app.infrastructure.config import get_settings

logger = logging.getLogger(__name__)


class EmbedderUnavailable(Exception):
    pass


@lru_cache
def get_embeddings():
    """返回 langchain HuggingFaceEmbeddings 实例；不可用抛 EmbedderUnavailable。"""
    import os

    s = get_settings()
    # 模型已在本地 HF 缓存时离线加载，避免代理/网络问题（可用 HF_HUB_OFFLINE 外部覆盖）
    os.environ.setdefault("HF_HUB_OFFLINE", "1" if s.hf_hub_offline else "0")
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
    except ImportError as e:
        raise EmbedderUnavailable(
            "langchain-huggingface / sentence-transformers 未安装，无法本地向量化") from e
    logger.info("loading embeddings: %s", s.embedding_model)
    return HuggingFaceEmbeddings(model_name=s.embedding_model)

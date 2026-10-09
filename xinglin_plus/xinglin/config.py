"""全局配置（按《项目开发指导》§2.3/§4 的组织方式：模块级常量字典）。

设计要点：
- 密钥一律从环境变量读（需求 13.3：密钥不进代码、不进库）；
- 数据/模型资源路径集中在此（文档 §3.5：资源归领域层所有，路径由 config 统一给出）；
- 本文件不 import 任何业务模块，是全项目的最底层依赖。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent          # → xinglin_plus/
load_dotenv(BASE_DIR / ".env")


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default) or default


# ---------------------------------------------------------------- Neo4j
# 沿用既有 medical 库（8808 疾病 / 7 类节点 / 10 类关系）；13.1/13.2 建议只读账户
NEO4J_CONFIG: dict = {
    "uri": _env("NEO4J_URI", "neo4j://127.0.0.1:7687"),
    "user": _env("NEO4J_USER", "neo4j"),
    "password": _env("NEO4J_PASSWORD", "12345678"),
    "database": _env("NEO4J_DATABASE", "medical"),
}

# ---------------------------------------------------------------- LLM
# DeepSeek（OpenAI 兼容）。密钥优先 LLM_API_KEY，其次系统变量 DEEPSEEK_API_KEY
_DEEPSEEK_KEY = _env("LLM_API_KEY") or _env("DEEPSEEK_API_KEY")

# NL2Cypher 用：低温度、长输出（生成结构化查询语句）
NL2CYPHER_LLM_CONFIG: dict = {
    "api_key": _DEEPSEEK_KEY,
    "base_url": _env("LLM_BASE_URL", "https://api.deepseek.com/v1"),
    "model": _env("LLM_MODEL", "deepseek-chat"),
    "temperature": 0.1,
    "max_tokens": 2048,
}

# RAG / 生成用：略高温度、常规长度
RAG_LLM_CONFIG: dict = {
    "api_key": _DEEPSEEK_KEY,
    "base_url": _env("LLM_BASE_URL", "https://api.deepseek.com/v1"),
    "model": _env("LLM_MODEL", "deepseek-chat"),
    "temperature": 0.3,
    "max_tokens": 800,
}

# 第一代兜底链的 Qwen 兜底（可选，默认关闭，避免用错 Key 空转）
AI_API_CONFIG: dict = {
    "api_key": _env("FALLBACK_LLM_API_KEY") or _env("DASHSCOPE_API_KEY")
    or _env("OPENAI_API_KEY") or _env("QWEN_API_KEY"),
    "base_url": _env("FALLBACK_LLM_BASE_URL",
                     "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    "model": _env("FALLBACK_LLM_MODEL", "qwen-plus"),
    "enabled": _env("FALLBACK_QWEN_ENABLED", "false").lower() == "true",
}

# False = 绕过系统代理直连（国内 API 必需；被代理劫持会连接失败）
LLM_TRUST_ENV: bool = _env("LLM_TRUST_ENV", "false").lower() == "true"

# ---------------------------------------------------------------- 向量库
# 沿用既有 Milvus **服务**（非指导文档示例里的 Milvus Lite 嵌入式文件）
MILVUS_CONFIG: dict = {
    "uri": _env("MILVUS_URI", "http://localhost:19530"),
    "collection": _env("MILVUS_COLLECTION", "medical_lit"),
}

# 本地 HuggingFace 向量模型（384 维多语言 MiniLM，已在本机 HF 缓存）
EMBEDDING_MODEL: str = _env(
    "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
EMBEDDING_DIM: int = int(_env("EMBEDDING_DIM", "384"))
HF_HUB_OFFLINE: bool = _env("HF_HUB_OFFLINE", "true").lower() == "true"
RETRIEVAL_TOP_K: int = int(_env("RETRIEVAL_TOP_K", "8"))
RERANK_ENABLED: bool = _env("RERANK_ENABLED", "false").lower() == "true"
# 稠密路相似度阈值（余弦，向量已归一化）：低于它的片段直接丢弃（文档 §11.1.1）
# 注意：该阈值只适用于**单路**的绝对分；融合后的分数是相对分，量纲不同、不可套用。
SEARCH_SCORE_THRESHOLD: float = float(_env("SEARCH_SCORE_THRESHOLD", "0.65"))

# ---------------------------------------------------------------- Redis
REDIS_CONFIG: dict = {
    "url": _env("REDIS_URL", "redis://localhost:6379/0"),
    "cache_ttl_hours": int(_env("CACHE_TTL_HOURS", "24")),
}

# ---------------------------------------------------------------- 数据 / 资源路径
# 图谱侧数据源（原始医疗数据，8808 疾病，已放入 data/）
MEDICAL_DATA_PATH: str = _env("MEDICAL_DATA_PATH", str(BASE_DIR / "data" / "medical.json"))
# 文献侧数据源：沿用既有语料（D:\project_phase\medical\medical\knowledge_base.txt）
KNOWLEDGE_TXT_PATH: str = _env(
    "KNOWLEDGE_TXT_PATH", str(BASE_DIR.parent / "medical" / "knowledge_base.txt"))
PDF_DATA_DIR: str = _env("PDF_DATA_DIR", str(BASE_DIR / "data" / "pdfs"))
BM25_DOCS_PATH: str = _env("BM25_DOCS_PATH", str(BASE_DIR / "data" / "bm25_docs.json"))
DICT_DIR: str = _env("DICT_DIR", str(BASE_DIR / "dict"))
CHUNK_SIZE: int = int(_env("CHUNK_SIZE", "600"))
CHUNK_OVERLAP: int = int(_env("CHUNK_OVERLAP", "100"))

# ---------------------------------------------------------------- 护栏 / 日志
GUARDRAIL_ENABLED: bool = _env("GUARDRAIL_ENABLED", "true").lower() == "true"
GUARDRAIL_MAX_UNSUPPORTED_RATIO: float = float(_env("GUARDRAIL_MAX_UNSUPPORTED_RATIO", "0.4"))
LOG_DIR: str = _env("LOG_DIR", str(BASE_DIR / "logs"))

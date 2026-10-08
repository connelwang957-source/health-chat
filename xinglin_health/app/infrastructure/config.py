"""全局配置（pydantic-settings）：密钥只从这里读，.env 不入库。"""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # Neo4j（已建 KG：medical 库；问答链路建议使用只读账户，13.1/13.2）
    neo4j_uri: str = "neo4j://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "12345678"
    neo4j_database: str = "medical"

    # Milvus / Redis
    milvus_uri: str = "http://localhost:19530"
    milvus_collection: str = "medical_lit"
    redis_url: str = "redis://localhost:6379/0"

    # LLM（OpenAI 兼容，langchain-openai ChatOpenAI）
    # API Key 优先读 LLM_API_KEY，其次读系统环境变量 DEEPSEEK_API_KEY
    llm_provider: str = "deepseek"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = Field(
        "", validation_alias=AliasChoices("LLM_API_KEY", "DEEPSEEK_API_KEY"))
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 800
    llm_trust_env: bool = False   # False=绕过系统代理直连（国内 API）；需要代理时设 true

    # Embedding（本地 HF 模型：384 维多语言 MiniLM）
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    hf_hub_offline: bool = True   # 模型已在本地 HF 缓存，离线加载避免网络问题
    rerank_enabled: bool = False
    retrieval_top_k: int = 8

    # 缓存 / 日志
    cache_ttl_hours: int = 24
    log_dir: str = "./logs"

    # 数据源
    knowledge_txt_path: str = str(BASE_DIR.parent / "medical" / "knowledge_base.txt")
    bm25_docs_path: str = str(BASE_DIR / "data" / "bm25_docs.json")

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"), env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

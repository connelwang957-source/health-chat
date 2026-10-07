"""组合根（composition root）：把 infrastructure 适配器注入 domain 服务，
组装 LangGraph 主图与用例。全项目唯一的"知道所有具体实现"的模块。
"""

from functools import lru_cache

from app.application.graph.build import build_graph
from app.application.graph.nodes import make_nodes
from app.application.prompts import build_generation_messages
from app.application.usecases.ask_usecase import AskUseCase
from app.domain.services import (
    CacheService, GenerationService, IntentService, KGQueryService,
    ReliabilityService, RetrievalService,
)
from app.infrastructure.config import get_settings
from app.infrastructure.hybrid_retriever import get_ensemble_retriever
from app.infrastructure.llm.gateway import get_llm_gateway
from app.infrastructure.neo4j_repo import get_neo4j_repo
from app.infrastructure.redis_cache import get_redis_cache


@lru_cache
def get_intent_service() -> IntentService:
    return IntentService(get_llm_gateway())


@lru_cache
def get_kg_query_service() -> KGQueryService:
    return KGQueryService(get_neo4j_repo())


@lru_cache
def get_retrieval_service() -> RetrievalService:
    return RetrievalService(get_ensemble_retriever())


@lru_cache
def get_generation_service() -> GenerationService:
    return GenerationService(get_llm_gateway(), build_generation_messages)


@lru_cache
def get_reliability_service() -> ReliabilityService:
    return ReliabilityService()


@lru_cache
def get_cache_service() -> CacheService:
    return CacheService(get_redis_cache(), get_settings().cache_ttl_hours)


@lru_cache
def get_ask_usecase() -> AskUseCase:
    nodes = make_nodes(get_intent_service(), get_kg_query_service(),
                       get_retrieval_service(), get_generation_service(),
                       get_reliability_service())
    return AskUseCase(get_cache_service(), build_graph(nodes),
                      get_settings().cache_ttl_hours)

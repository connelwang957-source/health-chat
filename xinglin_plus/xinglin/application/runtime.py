"""运行时装配（应用层组合根）：把适配器注入领域服务，供 4 个 Agent 共享。

对应文档 §5.4「application 依赖具体实现 + 是一次用例编排」——本模块就是"依赖具体实现"
的那一层；用 ``@lru_cache`` 保证重对象（Neo4j driver / Milvus / Redis / LLM 客户端）
在进程内**只建一次**。

⚠ 本模块与 `fallback/robot_qwen.py::xing_lin()` 的自动装配分支，是全项目仅有的两处
允许 import `xinglin.infrastructure` 的地方（由 `tests/test_architecture.py` 固化）。
"""

from functools import lru_cache

from xinglin.config import (
    BM25_DOCS_PATH,
    DICT_DIR,
    REDIS_CONFIG,
    RETRIEVAL_TOP_K,
)
from xinglin.domain.entities import Answer, Fact
from xinglin.domain.graph import NL2Cypher
from xinglin.domain.guardrail import FactGuardrail
from xinglin.domain.rag import HybridRetriever, MilvusVectorStore
from xinglin.domain.services import (
    CacheService,
    GenerationService,
    IntentService,
    KGQueryService,
    ReliabilityService,
    RetrievalService,
)
from xinglin.domain.values import Mode
from xinglin.fallback import MedicalDictionary, RobotQwen, load_words, xing_lin
from xinglin.infrastructure import Neo4jGraph, OpenAILlm, RedisManager, create_llm


# ---------------------------------------------------------------- 基础设施适配器
@lru_cache
def get_graph() -> Neo4jGraph:
    return Neo4jGraph()


@lru_cache
def get_llm() -> OpenAILlm:
    """领域层用的 LLM 端口适配器（OpenAI 兼容 → DeepSeek）。"""
    return OpenAILlm()


@lru_cache
def get_chat_model():
    """LangChain ChatOpenAI（给 `create_react_agent` 与 LCEL 链用）。"""
    return create_llm()


@lru_cache
def get_redis() -> RedisManager:
    return RedisManager()


@lru_cache
def get_dictionary() -> MedicalDictionary:
    return MedicalDictionary(load_words(DICT_DIR))


# ---------------------------------------------------------------- 领域服务
@lru_cache
def get_intent_service() -> IntentService:
    return IntentService(get_llm(), get_dictionary())


@lru_cache
def get_kg_query_service() -> KGQueryService:
    return KGQueryService(get_graph())


@lru_cache
def get_nl2cypher() -> NL2Cypher:
    return NL2Cypher(get_llm(), get_graph())


@lru_cache
def get_literature_search() -> HybridRetriever:
    """文献混合检索适配器（dense + BM25 → RRF），实现 LiteratureSearch 端口。"""
    return HybridRetriever(get_vector_store(), BM25_DOCS_PATH, RETRIEVAL_TOP_K)


@lru_cache
def get_retrieval_service() -> RetrievalService:
    return RetrievalService(get_literature_search(), RETRIEVAL_TOP_K)


@lru_cache
def get_generation_service() -> GenerationService:
    from xinglin.application.prompts import build_generation_prompt
    return GenerationService(get_llm(), build_generation_prompt)


@lru_cache
def get_reliability_service() -> ReliabilityService:
    return ReliabilityService()


@lru_cache
def get_fact_guardrail() -> FactGuardrail:
    """事实护栏（文档 §9.1）：用 LLM **二次核查**答案是否被参考上下文支撑。

    它只依赖 `domain.ports.LLM`，不碰基础设施——所以住在 domain 层。
    """
    return FactGuardrail(get_llm())


@lru_cache
def get_cache_service() -> CacheService:
    return CacheService(get_redis(), REDIS_CONFIG["cache_ttl_hours"])


@lru_cache
def get_fallback_robot() -> RobotQwen:
    """第 1 代零 LLM 规则兜底链（`xing_lin()` 工厂，照文档用法）。"""
    return xing_lin(get_dictionary(), get_graph())


@lru_cache
def get_vector_store() -> MilvusVectorStore:
    return MilvusVectorStore()


@lru_cache
def get_default_agent():
    """默认问答 Agent（接口层用）。

    模式在**启动时**通过 `XINGLIN_WEB_MODE` 固定（`python -m xinglin.interfaces.web --mode X`），
    请求侧不暴露任何模式参数（FR-024/6.2 用户不可指定）。
    """
    import os

    mode = os.getenv("XINGLIN_WEB_MODE", "hybrid")
    if mode == "agent":
        from xinglin.application.tool_agent import ToolCallingAgent
        return ToolCallingAgent()
    if mode == "rag":
        from xinglin.application.rag_agent import RAGAgent
        return RAGAgent()
    if mode == "nl2cypher":
        from xinglin.application.nl2cypher_agent import NL2CypherAgent
        return NL2CypherAgent()
    from xinglin.application.hybrid_agent import HybridAgent
    return HybridAgent()


# ---------------------------------------------------------------- 公共收尾
def finalize_answer(question: str, answer: Answer,
                    kg_facts: list[Fact], docs: list[dict]) -> Answer:
    """所有 Agent 共用的收尾：依据分级（FR-023）。

    事实护栏**不在这里**——按文档 §9 的数据流，它是「答案 + 参考上下文」的
    独立核查步骤，由各 Agent 拿到最终答案后调用（见 `HybridAgent._guard`）。
    """
    reliability_service = get_reliability_service()
    answer.reliability = reliability_service.check(answer.mode, kg_facts, docs)
    return answer


def needs_retry(answer: Answer) -> bool:
    """是否需要换检索通路重试（FR-026）：**完全没有依据**（low）时才换。

    注意：事实护栏"未通过"（答案里出现了证据中没有的数字）**刻意不触发换路**——
    换另一条通路同样拿不到那些数字，只会让 `mode` 漂移、答案更差。
    这类情况如实记录在 `meta.grounding`，由展示层提示用户谨慎参考。
    """
    if answer.status != "ok" or answer.mode is Mode.DIRECT:
        return False
    return answer.reliability is not None and answer.reliability.value == "low"


__all__ = [
    "get_graph", "get_llm", "get_chat_model", "get_redis", "get_dictionary",
    "get_intent_service", "get_kg_query_service", "get_nl2cypher",
    "get_retrieval_service", "get_generation_service", "get_reliability_service",
    "get_fact_guardrail",
    "get_cache_service", "get_fallback_robot", "get_vector_store", "get_default_agent",
    "finalize_answer", "needs_retry",
]

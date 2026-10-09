"""domain 服务层：承载业务动作的领域服务。

只依赖 `xinglin.domain.ports` 里的端口抽象（依赖倒置），具体技术实现由
`xinglin.infrastructure` 的适配器提供、由组合根（`application/*_agent.py` 的 `__init__`）注入。
"""

from xinglin.domain.services.cache_service import CacheService, normalize_question
from xinglin.domain.services.generation_service import GenerationService
from xinglin.domain.services.intent_service import IntentOut, IntentService, parse_intent_json
from xinglin.domain.services.kg_query_service import KGQueryService, build_cypher, rows_to_facts
from xinglin.domain.services.reliability_service import ReliabilityService
from xinglin.domain.services.retrieval_service import RetrievalService, RetrievalUnavailable

__all__ = [
    "CacheService", "normalize_question",
    "GenerationService",
    "IntentService", "IntentOut", "parse_intent_json",
    "KGQueryService", "build_cypher", "rows_to_facts",
    "ReliabilityService",
    "RetrievalService", "RetrievalUnavailable",
]

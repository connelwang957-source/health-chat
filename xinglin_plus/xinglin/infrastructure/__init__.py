"""infrastructure：基础设施层（唯一碰具体技术的地方）。

    llm.py       LLM 端口适配器（OpenAILlm，OpenAI 兼容 → DeepSeek/Qwen）+ create_llm 工厂
    graph.py     GraphStore 端口适配器（Neo4jGraph，只读会话 + 参数化 Cypher + EXPLAIN）
    cache.py     CacheStore 端口适配器（RedisManager，JSON + SETNX 幂等锁）

本层实现 `xinglin.domain.ports` 的端口契约，由应用层的组合根（各 Agent 的 `__init__`）装配。
"""

from xinglin.infrastructure.cache import RedisManager, redis_manager
from xinglin.infrastructure.graph import Neo4jGraph
from xinglin.infrastructure.llm import OpenAILlm, create_llm

__all__ = ["OpenAILlm", "create_llm", "Neo4jGraph", "RedisManager", "redis_manager"]

"""领域层端口（Ports）——依赖倒置的抽象契约。

照《项目开发指导》§5.1：定义领域层所需的抽象接口（``Protocol``），由基础设施层的适配器
实现，从而把依赖方向从「领域 → 基础设施」倒置为「基础设施 → 领域」。

为什么用 ``Protocol`` 而不是 ``ABC + @abstractmethod``：

- ``Protocol`` 是**隐式抽象**——不强制子类显式继承，Python 也不在实例化时报错；
- 好处是适配器可以是对第三方 SDK 的薄包装（如 ``ChatOpenAI`` 的封装），
  不必为了"实现接口"去改动继承链；
- 代价是**契约靠约定与测试保证**（本项目用 ``tests/test_ports.py`` 做类型契约检查）。

领域层只依赖本文件里的抽象，绝不 import 任何具体 SDK。
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLM(Protocol):
    """LLM 端口：领域层需要的文本生成能力。"""

    @property
    def available(self) -> bool:
        """配置是否齐全（**不做网络探测**，避免健康检查产生费用）。"""
        ...

    def complete(self, system: str, user: str,
                 temperature: float = 0.0, max_tokens: int = 2048) -> str:
        """system + user 两段式补全（NL2Cypher 生成语句、ReAct 决策用）。"""
        ...


@runtime_checkable
class GraphStore(Protocol):
    """图存储端口：只读 Cypher 查询与 EXPLAIN 校验能力。"""

    def query(self, cypher: str, params: dict | None = None) -> list[dict[str, Any]]:
        """执行只读 Cypher，返回记录列表。"""
        ...

    def explain(self, cypher: str, params: dict | None = None) -> None:
        """``EXPLAIN`` 预检：只生成执行计划，不执行原查询（校验语句是否合法）。

        参数化语句（``$entity``）在 EXPLAIN 时同样需要绑定参数，故带上 ``params``。
        """
        ...

    def close(self) -> None:
        ...


@runtime_checkable
class LiteratureSearch(Protocol):
    """文献检索端口：稠密向量 + 稀疏关键词的混合检索能力。"""

    @property
    def available(self) -> bool:
        ...

    def search(self, query: str, k: int = 8) -> list[dict]:
        """返回 ``[{"text": ..., "metadata": {...}}, ...]``（纯 dict，不外泄 langchain 类型）。"""
        ...


@runtime_checkable
class CacheStore(Protocol):
    """缓存端口：JSON 读写 + SETNX 幂等锁（FR-028/029）。"""

    @property
    def available(self) -> bool:
        ...

    def get_json(self, key: str) -> dict | None:
        ...

    def set_json(self, key: str, value: dict, ttl_seconds: int) -> None:
        ...

    def acquire_lock(self, key: str, ttl_seconds: int) -> bool:
        """SETNX 抢锁；拿到锁说明本次请求由自己处理（FR-029）。"""
        ...

    def release_lock(self, key: str) -> None:
        ...


@runtime_checkable
class EntityRecognizer(Protocol):
    """实体识别端口：医学词典最长优先匹配（第 1 代规则链与意图降级共用）。"""

    @property
    def available(self) -> bool:
        ...

    def find_entity(self, text: str, roles: tuple[str, ...] | None = None
                    ) -> tuple[str, str] | None:
        """返回 ``(实体, 角色标签)``；角色标签与图谱节点标签一致。"""
        ...


__all__ = ["LLM", "GraphStore", "LiteratureSearch", "CacheStore", "EntityRecognizer"]

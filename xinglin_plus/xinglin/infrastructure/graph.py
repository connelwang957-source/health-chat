"""基础设施层：图数据库适配器（Neo4j），实现领域层的 `GraphStore` 端口。

对应文档 §5.2 的 `xinglin/infrastructure/graph.py`。安全约定（需求 13.1/13.2）：

- 问答链路一律走**只读会话**（``default_access_mode="READ"``）；
- Cypher 全部**参数化**（``session.run(cypher, params)``），不做字符串拼接；
- ``explain`` 只让服务端生成执行计划，**不执行原查询**。
"""

import logging

from neo4j import GraphDatabase

from xinglin.config import NEO4J_CONFIG
from xinglin.domain.ports import GraphStore

logger = logging.getLogger(__name__)


class Neo4jGraph(GraphStore):
    """`GraphStore` 端口适配器：封装 Neo4j Driver（惰性连接）。"""

    def __init__(self, config: dict | None = None):
        self._config = config or NEO4J_CONFIG
        self._driver = None

    @property
    def database(self) -> str:
        return self._config["database"]

    @property
    def driver(self):
        """惰性建立驱动：import 时不连库，方便干跑与单测。"""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self._config["uri"],
                auth=(self._config["user"], self._config["password"]),
                connection_timeout=5,
            )
        return self._driver

    # -- 端口实现 -----------------------------------------------------------
    def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        """只读会话执行参数化 Cypher。"""
        with self.driver.session(database=self.database,
                                 default_access_mode="READ") as session:
            return session.run(cypher, params or {}).data()

    def explain(self, cypher: str, params: dict | None = None) -> None:
        """``EXPLAIN`` 预检：只规划、不执行原查询。"""
        with self.driver.session(database=self.database,
                                 default_access_mode="READ") as session:
            session.run(f"EXPLAIN {cypher}", params or {})

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    # -- 健康探针（供 /health 使用） -----------------------------------------
    def health(self) -> bool:
        try:
            with self.driver.session(database=self.database,
                                     default_access_mode="READ") as session:
                session.run("RETURN 1 AS ok").data()
            return True
        except Exception as e:      # noqa: BLE001 —— 探针失败即视为不健康
            logger.warning("Neo4j 健康检查失败: %s", e)
            return False


__all__ = ["Neo4jGraph"]

"""Neo4j 只读仓储（infrastructure）。

问答链路使用只读会话（default_access_mode=READ）+ 参数化 Cypher（13.1/13.2）。
连接惰性建立，任何失败由调用方捕获进入降级链（12.1）。
"""

import logging
from functools import lru_cache

from neo4j import GraphDatabase

from app.infrastructure.config import get_settings

logger = logging.getLogger(__name__)


class Neo4jRepo:
    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        self._uri, self._user, self._password = uri, user, password
        self._database = database
        self._driver = None

    def _ensure_driver(self):
        if self._driver is None:
            # NEO4J_AUTH=none 部署形态（无密码）时不传账密
            if self._password:
                auth = (self._user, self._password)
            else:
                auth = None
            self._driver = GraphDatabase.driver(
                self._uri, auth=auth, connection_timeout=3)
        return self._driver

    def run_read(self, cypher: str, params: dict | None = None) -> list[dict]:
        """只读执行参数化 Cypher，返回 [{'value': ...}, ...]。"""
        driver = self._ensure_driver()
        with driver.session(database=self._database,
                            default_access_mode="READ") as session:
            result = session.run(cypher, params or {})
            return [r.data() for r in result]

    def health(self) -> bool:
        try:
            self.run_read("RETURN 1 AS ok")
            return True
        except Exception as e:  # noqa: BLE001 —— 健康检查吞掉一切，只报告状态
            logger.warning("Neo4j health failed: %s", e)
            return False

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None


@lru_cache
def get_neo4j_repo() -> Neo4jRepo:
    s = get_settings()
    return Neo4jRepo(s.neo4j_uri, s.neo4j_user, s.neo4j_password, s.neo4j_database)

"""基础设施层：Redis 缓存适配器，实现领域层的 `CacheStore` 端口（FR-028/029）。

对应文档 §5.4 中 `from xinglin.infrastructure.cache import redis_manager` 的用法：
本模块提供一个**模块级实例** ``redis_manager``，同时类本身可用于注入（便于单测替换）。

Redis 是**可选**依赖：连不上时 ``available`` 为 False，上层照常问答（只是没了秒回）。
"""

import json
import logging

import redis as redis_lib

from xinglin.config import REDIS_CONFIG
from xinglin.domain.ports import CacheStore

logger = logging.getLogger(__name__)


class RedisManager(CacheStore):
    """JSON 读写 + SETNX 幂等锁。"""

    def __init__(self, url: str | None = None, ttl_hours: int | None = None):
        self._url = url or REDIS_CONFIG["url"]
        self._default_ttl = int((ttl_hours or REDIS_CONFIG["cache_ttl_hours"]) * 3600)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = redis_lib.Redis.from_url(
                self._url, decode_responses=True,
                socket_connect_timeout=2, socket_timeout=2)
        return self._client

    @property
    def available(self) -> bool:
        """真实 ping 一次（2 秒超时）；失败即视为不可用。"""
        try:
            return bool(self.client.ping())
        except Exception as e:      # noqa: BLE001
            logger.debug("Redis 不可用: %s", e)
            return False

    # -- JSON 读写 -----------------------------------------------------------
    def get_json(self, key: str) -> dict | None:
        try:
            raw = self.client.get(key)
        except Exception as e:      # noqa: BLE001 —— 缓存异常不影响主流程
            logger.debug("缓存读取失败: %s", e)
            return None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    def set_json(self, key: str, value: dict, ttl_seconds: int | None = None) -> None:
        try:
            self.client.set(key, json.dumps(value, ensure_ascii=False),
                            ex=ttl_seconds or self._default_ttl)
        except Exception as e:      # noqa: BLE001
            logger.debug("缓存写入失败: %s", e)

    # -- 幂等锁（FR-029） ----------------------------------------------------
    def acquire_lock(self, key: str, ttl_seconds: int) -> bool:
        """SETNX 抢锁：拿到说明本次请求由自己处理。"""
        try:
            return bool(self.client.set(key, "1", nx=True, ex=ttl_seconds))
        except Exception as e:      # noqa: BLE001 —— 缓存不可用时不阻塞问答
            logger.debug("抢锁失败（放行）: %s", e)
            return True

    def release_lock(self, key: str) -> None:
        try:
            self.client.delete(key)
        except Exception as e:      # noqa: BLE001
            logger.debug("释放锁失败: %s", e)

    # -- 便捷方法（文档 cli.py 的用法） ---------------------------------------
    def get_or_compute(self, key: str, compute, ttl_seconds: int | None = None):
        """缓存命中直接返回，否则计算并回写（``compute`` 为无参可调用对象）。"""
        if (hit := self.get_json(key)) is not None:
            return hit
        value = compute()
        self.set_json(key, value, ttl_seconds)
        return value


# 模块级实例（文档风格：`from xinglin.infrastructure.cache import redis_manager`）
redis_manager = RedisManager()

__all__ = ["RedisManager", "redis_manager"]

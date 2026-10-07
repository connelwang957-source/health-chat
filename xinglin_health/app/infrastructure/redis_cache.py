"""Redis 缓存（infrastructure）：JSON 读写 + SETNX 幂等锁（FR-028/029）。"""

import json
import logging
from functools import lru_cache

import redis as redis_lib

from app.infrastructure.config import get_settings

logger = logging.getLogger(__name__)


class RedisCache:
    def __init__(self, url: str):
        self._url = url
        self._client = None

    def _ensure(self):
        if self._client is None:
            self._client = redis_lib.Redis.from_url(
                self._url, socket_connect_timeout=1, socket_timeout=1,
                decode_responses=True)
        return self._client

    @property
    def available(self) -> bool:
        try:
            return self._ensure().ping()
        except Exception:  # noqa: BLE001 —— 12.4：缓存故障不阻断问答
            return False

    def get_json(self, key: str) -> dict | None:
        try:
            raw = self._ensure().get(key)
            return json.loads(raw) if raw else None
        except Exception as e:  # noqa: BLE001
            logger.warning("redis get failed: %s", e)
            return None

    def set_json(self, key: str, payload: dict, ttl_hours: int) -> None:
        try:
            self._ensure().set(key, json.dumps(payload, ensure_ascii=False),
                               ex=max(60, ttl_hours * 3600))
        except Exception as e:  # noqa: BLE001
            logger.warning("redis set failed: %s", e)

    def acquire_lock(self, key: str, ttl_seconds: int) -> bool:
        try:
            return bool(self._ensure().set(key, "1", nx=True, ex=ttl_seconds))
        except Exception:  # noqa: BLE001
            return True  # 缓存故障时不因锁失败而阻断（12.4）

    def release_lock(self, key: str) -> None:
        try:
            self._ensure().delete(key)
        except Exception:  # noqa: BLE001
            pass


@lru_cache
def get_redis_cache() -> RedisCache:
    return RedisCache(get_settings().redis_url)

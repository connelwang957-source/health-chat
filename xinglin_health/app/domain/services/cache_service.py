"""CacheService：FR-028 重复问题快速返回 / FR-029 重复请求保护（领域服务）。"""

import hashlib
import re
import unicodedata


def normalize_question(question: str) -> str:
    """规范化问题 → 缓存 Key 素材：全角转半角、去空白与标点、转小写。"""
    q = unicodedata.normalize("NFKC", question or "")
    q = re.sub(r"[\s，。？！、：；“”‘’（）【】,.?!:;\"'()\[\]~～]+", "", q)
    return q.lower()


def cache_key(question: str) -> str:
    return "kb:ans:" + hashlib.sha256(normalize_question(question).encode("utf-8")).hexdigest()


class CacheService:
    def __init__(self, redis_cache, ttl_hours: int = 24):
        self._redis = redis_cache  # infrastructure.redis_cache.RedisCache
        self._ttl_hours = ttl_hours

    @property
    def available(self) -> bool:
        return self._redis is not None and self._redis.available

    def get(self, question: str) -> dict | None:
        if not self.available:
            return None
        return self._redis.get_json(cache_key(question))

    def put(self, question: str, payload: dict) -> None:
        if self.available:
            self._redis.set_json(cache_key(question), payload, ttl_hours=self._ttl_hours)

    def try_lock(self, question: str, ttl_seconds: int = 60) -> bool:
        """FR-029：同一问题重复请求只放行一个（SET NX EX）。"""
        if not self.available:
            return True
        return self._redis.acquire_lock("kb:lock:" + cache_key(question), ttl_seconds)

    def release_lock(self, question: str) -> None:
        if self.available:
            self._redis.release_lock("kb:lock:" + cache_key(question))

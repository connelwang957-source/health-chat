"""CacheService：缓存 Key 规范化 + 幂等锁（FR-028/029，domain 领域服务）。

缓存分两层，各自解决一个问题：

    kb:ans:{hash}    答案 JSON，TTL 24h —— FR-028「重复问题秒回」
    kb:lock:{hash}   SETNX 60s         —— FR-029「同问题只算一次」

Key 里带 **mode**：同一个问题在不同检索形态下 mode 与来源都不同，不带会互相污染。
"""

import hashlib
import re
import unicodedata

from xinglin.domain.ports import CacheStore

LOCK_TTL_SECONDS = 60
KEY_PREFIX = "kb"


def normalize_question(question: str) -> str:
    """问题规范化：全角→半角、转小写、去标点与空白（用于生成稳定的缓存 Key）。"""
    text = unicodedata.normalize("NFKC", question or "").lower()
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text)


class CacheService:
    def __init__(self, store: CacheStore, ttl_hours: int = 24):
        self._store = store
        self._ttl = int(ttl_hours * 3600)

    @property
    def available(self) -> bool:
        return self._store is not None and getattr(self._store, "available", False)

    # -- Key 规范 -----------------------------------------------------------
    @staticmethod
    def cache_key(question: str, mode: str | None = None) -> str:
        """``kb:ans:{sha256(mode::规范化问题)}``。"""
        raw = f"{mode or 'auto'}::{normalize_question(question)}"
        return f"{KEY_PREFIX}:ans:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"

    @staticmethod
    def lock_key(question: str, mode: str | None = None) -> str:
        raw = f"{mode or 'auto'}::{normalize_question(question)}"
        return f"{KEY_PREFIX}:lock:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"

    # -- 读写 ---------------------------------------------------------------
    def get(self, question: str, mode: str | None = None) -> dict | None:
        if not self.available:
            return None
        return self._store.get_json(self.cache_key(question, mode))

    def put(self, question: str, payload: dict, mode: str | None = None) -> None:
        if self.available:
            self._store.set_json(self.cache_key(question, mode), payload, self._ttl)

    # -- 幂等锁（FR-029） ----------------------------------------------------
    def try_lock(self, question: str, mode: str | None = None) -> bool:
        """拿到锁说明本次请求由自己处理；缓存不可用时直接放行（不阻断问答）。"""
        if not self.available:
            return True
        return self._store.acquire_lock(self.lock_key(question, mode), LOCK_TTL_SECONDS)

    def release_lock(self, question: str, mode: str | None = None) -> None:
        if self.available:
            self._store.release_lock(self.lock_key(question, mode))


__all__ = ["CacheService", "normalize_question", "LOCK_TTL_SECONDS", "KEY_PREFIX"]

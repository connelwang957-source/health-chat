"""AskUseCase：提问用例（application 层）。

编排：缓存查询（FR-028）→ LangGraph 主图 → 回写缓存；
FR-029 重复请求用 SETNX 锁保护；任何未捕获异常收敛为统一兜底响应（12.3）。
"""

import logging
import time

from app.domain.rules import INSUFFICIENT_ANSWER

logger = logging.getLogger(__name__)

BUSY_ANSWER = "相同问题正在处理中，请稍候后重试。"


class AskUseCase:
    def __init__(self, cache_service, graph, cache_ttl_hours: int = 24):
        self._cache = cache_service
        self._graph = graph
        self._ttl = cache_ttl_hours

    def execute(self, question: str) -> dict:
        # ① 缓存查询（FR-028）
        if (hit := self._cache.get(question)) is not None:
            hit["cached"] = True
            return hit

        # ② 重复请求保护（FR-029）：拿不到锁说明同问题在处理中
        if not self._cache.try_lock(question):
            for _ in range(3):                      # 等待在途请求写入缓存
                time.sleep(1.5)
                if (hit := self._cache.get(question)) is not None:
                    hit["cached"] = True
                    return hit
            return self._payload(status="service_unavailable", answer=BUSY_ANSWER)

        try:
            # ③ 执行主图
            final = self._graph.invoke({
                "question": question, "normalized": question,
                "retries": 0, "tried_modes": [], "notes": [],
            }, config={"recursion_limit": 25})
            answer = final["answer"]
            payload = answer.model_dump()
            payload["cached"] = False
            # ④ 回写缓存（仅成功回答；12.3 兜底不缓存以免污染）
            if payload["status"] == "ok":
                self._cache.put(question, payload)
            return payload
        except Exception as e:  # noqa: BLE001 —— 12.3：任何内部失败收敛为服务提示
            logger.exception("ask pipeline failed")
            return self._payload(status="service_unavailable",
                                 answer=INSUFFICIENT_ANSWER,
                                 notes=["问答服务暂时不可用，请稍后再试"])
        finally:
            self._cache.release_lock(question)

    @staticmethod
    def _payload(status: str, answer: str, notes: list[str] | None = None) -> dict:
        return {"status": status, "mode": "direct", "answer": answer,
                "sources": [], "reliability": "low", "risk_notice": None,
                "cached": False, "meta": {"notes": notes or []}}

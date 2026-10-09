"""NL2CypherAgent：图谱问答（对应文档 §5.4 的 `application/nl2cypher_agent.py`）。

文档里的形态是「主路径 NL2Cypher + 旧流水线兜底」；本项目在此基础上**前接一层模板**，
形成图谱通路的**三层递进**（同时也是 FR-025「多次信息查询」的落点）：

    ① 模板精确查询（`QAType` 元数据，零 LLM、结果确定）—— 18 类固定问答的主路径
    ② NL2Cypher（LLM 生成语句 + 规则/EXPLAIN 校验）—— 覆盖模板外的关系
    ③ 第 1 代规则链（`xing_lin()`，零 LLM）—— 模型挂了也保住图谱能力

任一层拿到事实即返回，因此成本从低到高、可用性从高到低。
"""

import logging

from xinglin.application.runtime import (
    finalize_answer,
    get_fallback_robot,
    get_generation_service,
    get_intent_service,
    get_kg_query_service,
    get_nl2cypher,
)
from xinglin.domain.entities import Answer, Fact
from xinglin.domain.values import Mode

logger = logging.getLogger(__name__)


class NL2CypherAgent:
    """走知识图谱通路的问答 Agent。"""

    def __init__(self, intent=None, kg_query=None, nl2cypher=None,
                 fallback=None, generation=None):
        self._intent = intent or get_intent_service()
        self._kg_query = kg_query or get_kg_query_service()
        self._nl2cypher = nl2cypher or get_nl2cypher()
        self._fallback = fallback or get_fallback_robot()
        self._generation = generation or get_generation_service()

    # -- 给 HybridAgent 复用的取证据接口 --------------------------------------
    def collect_facts(self, question: str, intent=None) -> list[Fact]:
        """图谱路三层递进取证据（返回事实列表；全程不抛错）。"""
        intent = intent if intent is not None else self._intent.classify(question)

        # ① 模板精确查询
        if intent.qa_type is not None and intent.entity:
            try:
                facts = self._kg_query.query(intent.qa_type, intent.entity)
                if facts:
                    return facts
            except Exception as e:      # noqa: BLE001 —— 12.1 KG 不可用
                logger.warning("模板查询失败（继续降级）: %s", e)

        # ② NL2Cypher 补充
        if self._nl2cypher.available:
            try:
                if facts := self._nl2cypher.answer(question).get("facts"):
                    return facts
            except Exception as e:      # noqa: BLE001
                logger.warning("NL2Cypher 失败（继续降级）: %s", e)

        # ③ 第 1 代规则链（零 LLM）
        try:
            if self._fallback.available:
                return self._fallback.chat_main(question).facts
        except Exception as e:          # noqa: BLE001
            logger.warning("规则兜底链失败: %s", e)
        return []

    # -- 主入口 -------------------------------------------------------------
    def chat_main(self, question: str) -> Answer:
        facts = self.collect_facts(question)
        answer = self._generation.generate(question, Mode.KG, facts, [])
        return finalize_answer(question, answer, facts, [])


__all__ = ["NL2CypherAgent"]

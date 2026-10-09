"""HybridAgent：双路融合（**默认模式**，FR-024 / FR-026 的落点）。

对应文档 §6 的**外层多路召回**：RAG（文本语义）+ 图谱（结构化关系）两路合起来，
覆盖"语义相似"与"关系精确"两类信息需求；一路失败另一路兜住（容错）。

它还承担两个关键职责：

- **FR-024 自动判断检索模式**：按意图与开放程度选 direct / kg / rag / hybrid ——
  咨询人员不需要（也不允许）自己指定；
- **FR-026 备用处理**：依据不足或**事实护栏未通过**时，换一条还没走过的通路重试（≤2 次），
  重试仍不行就按失败形态给"信息不足"话术。
"""

import logging

from xinglin.application.nl2cypher_agent import NL2CypherAgent
from xinglin.application.rag_agent import RAGAgent
from xinglin.application.runtime import (
    finalize_answer,
    get_fact_guardrail,
    get_generation_service,
    get_intent_service,
    needs_retry,
)
from xinglin.config import GUARDRAIL_ENABLED
from xinglin.domain.entities import Answer, Fact
from xinglin.domain.guardrail import add_unsupported_note
from xinglin.domain.values import Mode

logger = logging.getLogger(__name__)

MAX_RETRY = 2


class HybridAgent:
    """默认问答 Agent：双路召回 + 自动选路 + 备用处理。"""

    def __init__(self, intent=None, nl2cypher_agent=None, rag_agent=None,
                 generation=None, enable_guardrail: bool = True, guardrail=None):
        self._intent = intent or get_intent_service()
        self._nl2 = nl2cypher_agent or NL2CypherAgent()
        self._rag = rag_agent or RAGAgent()
        self._generation = generation or get_generation_service()
        # 事实护栏（文档 §9）：独立的一次 LLM 核查；`enable_guardrail` 可整体关闭
        self._enable_guardrail = enable_guardrail and GUARDRAIL_ENABLED
        self._guardrail = guardrail or (get_fact_guardrail()
                                        if self._enable_guardrail else None)

    # -- 主入口 -------------------------------------------------------------
    def chat_main(self, question: str) -> Answer:
        intent = self._intent.classify(question)
        mode = self._route(intent)

        answer = self._answer_with(question, intent, mode)

        # FR-026：依据不足 / 护栏未过 → 换一条没走过的通路重试（≤2 次）
        tried = {mode}
        for attempt in range(MAX_RETRY):
            if not needs_retry(answer):
                break
            next_mode = self._next_mode(tried)
            if next_mode is None:
                break
            logger.info("依据不足或护栏未过，换通路重试：%s → %s", mode.value, next_mode.value)
            tried.add(next_mode)
            mode = next_mode
            answer = self._answer_with(question, intent, mode)

        return answer

    # -- 内部 ---------------------------------------------------------------
    def _answer_with(self, question: str, intent, mode: Mode) -> Answer:
        """按指定通路取证据 → 融合生成 → 事实护栏（文档 §7.3.1 的三个阶段）。"""
        facts, docs = self._gather(question, intent, mode)
        answer = finalize_answer(
            question, self._generation.generate(question, mode, facts, docs), facts, docs)
        answer.answer = self._guard(answer.answer, self._fuse(facts, docs))
        return answer

    @staticmethod
    def _fuse(facts: list[Fact], docs: list[dict]) -> str:
        """拼接两路上下文，作为护栏核查的依据（文档 §9 `_fuse`）。"""
        parts: list[str] = []
        if facts:
            parts.append("【知识图谱事实】\n"
                         + "\n".join(f"{f.entity} {f.relation} {f.value}" for f in facts))
        if docs:
            parts.append("【检索文档】\n"
                         + "\n".join(str(d.get("text", "")) for d in docs))
        return "\n\n".join(parts)

    def _guard(self, answer: str, context: str) -> str:
        """事实护栏：无依据时在答案后追加提醒——**不拦截、只提醒**（文档 §9 `_guard`）。

        无上下文（如 direct 通路）时跳过；核查失败时护栏自身降级放行。
        """
        if not self._enable_guardrail or self._guardrail is None or not context:
            return answer
        verdict = self._guardrail.check(answer, context)
        if verdict.get("grounded"):
            return answer
        return add_unsupported_note(answer, verdict.get("unsupported") or [])

    def _gather(self, question: str, intent, mode: Mode) -> tuple[list[Fact], list[dict]]:
        """按通路取证据（图谱 / 文献 / 双路）。"""
        facts: list[Fact] = []
        docs: list[dict] = []
        if mode in (Mode.KG, Mode.HYBRID):
            facts, _ = self._graph_recall(question, intent)
        if mode in (Mode.RAG, Mode.HYBRID):
            docs = self._rag.collect_docs(question)
        return facts, docs

    def _graph_recall(self, question: str, intent=None) -> tuple[list[Fact], bool]:
        """图谱召回：返回 (结构化事实, 是否可用)；失败时降级为空（文档 §7.3.1）。"""
        try:
            facts = self._nl2.collect_facts(question, intent)
            return facts, bool(facts)
        except Exception as e:      # noqa: BLE001 —— 图谱不可用时只降级，不阻塞
            logger.warning("[图谱召回失败] %s", e)
            return [], False

    @staticmethod
    def _route(intent) -> Mode:
        """FR-024 自动选路（对应 4.3 策略表）。

        顺序即优先级：**开放程度**优先于"命中了哪一类"——
        "2型糖尿病药物治疗有哪些新进展"虽然沾了"药物治疗"的边，
        也应当去查文献，而不是被模板问题抢走、答一句"资料未收录"。
        """
        if intent.open_ended:
            return Mode.HYBRID if intent.entity else Mode.RAG
        if intent.qa_type is not None or intent.entity:
            return Mode.KG                # 可枚举的信息需求 → 结构化知识
        return Mode.DIRECT                # 寒暄/常识：无实体、无类型 → 不检索

    @staticmethod
    def _next_mode(tried: set[Mode]) -> Mode | None:
        """FR-026：挑一条还没走过的检索通路（direct 无检索，不参与重试）。"""
        for candidate in (Mode.HYBRID, Mode.RAG, Mode.KG):
            if candidate not in tried:
                return candidate
        return None


__all__ = ["HybridAgent", "MAX_RETRY"]

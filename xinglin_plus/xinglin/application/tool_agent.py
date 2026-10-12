"""ToolCallingAgent：工具调用 ReAct Agent（LLM 自主决策）。

对应文档 §5.4 的说明 —— 四个 Agent 里**只有它名副其实**：
内部是 `create_react_agent` 的 ReAct 循环，**控制权在 LLM 手里**，
由模型自己决定调 `graph_search` 还是 `literature_search`、以及调几次，
而不是由代码写死"先图谱后文献"。

工具取到的证据经 `collector` 回传，用于**来源标识**（FR-022）与**事实护栏**核对。
ReAct 失败（超步数 / LLM 异常）时回落 `HybridAgent` 的自动路由，保证不空手而归。
"""

import logging

from langgraph.prebuilt import create_react_agent

from xinglin.application.nl2cypher_agent import NL2CypherAgent
from xinglin.application.rag_agent import RAGAgent
from xinglin.application.runtime import (
    finalize_answer,
    get_chat_model,
    get_generation_service,
    guarded,
)
from xinglin.application.tools import build_tools
from xinglin.domain.entities import Answer, Fact
from xinglin.domain.values import Mode

logger = logging.getLogger(__name__)

RECURSION_LIMIT = 10        # ReAct 步数上限（含工具调用），防止无限循环

REACT_SYSTEM = """你是杏林大健康问答系统的推理代理。你可以调用工具收集证据，然后给出回答。

可用工具：
- graph_search：查询结构化健康知识图谱，适合疾病/症状/药品/食品/检查之间已建模的关系；
- literature_search_tool：检索医学文献库，适合诊疗进展、机制、指南等图谱未覆盖的内容。

作答要求：
1. 只能依据工具返回的证据作答，不得编造数字、剂量、比例或结论；
2. 证据不足时如实说明"依据不足"，不得给出确诊结论或用药处方；
3. 涉及诊疗时提示遵医嘱；中文作答，分点简洁，不超过 400 字。"""


class ToolCallingAgent:
    """ReAct 工具调用 Agent（LLM 自主决定检索策略）。"""

    def __init__(self, model=None, generation=None, nl2cypher_agent=None,
                 rag_agent=None, recursion_limit: int = RECURSION_LIMIT):
        self._model = model or get_chat_model()
        self._generation = generation or get_generation_service()
        self._nl2 = nl2cypher_agent or NL2CypherAgent()
        self._rag = rag_agent or RAGAgent()
        self._recursion_limit = recursion_limit

    # -- 主入口 -------------------------------------------------------------
    @guarded                        # 12.7：非法查询在入口就被拦住
    def chat_main(self, question: str) -> Answer:
        collector: dict = {"facts": [], "docs": []}
        tools = build_tools(self._nl2.collect_facts, self._rag.collect_docs, collector)

        try:
            agent = create_react_agent(self._model, tools, prompt=REACT_SYSTEM)
            result = agent.invoke({"messages": [("user", question)]},
                                  config={"recursion_limit": self._recursion_limit})
            text = (result["messages"][-1].content or "").strip()
        except Exception as e:      # noqa: BLE001 —— ReAct 失败回落自动路由
            logger.warning("ReAct 执行失败，回落 HybridAgent: %s", e)
            return self._fallback(question)

        facts: list[Fact] = collector.get("facts", [])
        docs: list[dict] = collector.get("docs", [])
        if not text:
            return self._fallback(question)

        answer = self._generation.compose(question, _mode_of(facts, docs), text, facts, docs)
        return finalize_answer(question, answer, facts, docs)

    def _fallback(self, question: str) -> Answer:
        """ReAct 失败 → 回落默认 Agent（双路 + 自动路由），保证有答案。"""
        from xinglin.application.hybrid_agent import HybridAgent
        return HybridAgent(nl2cypher_agent=self._nl2, rag_agent=self._rag,
                           generation=self._generation).chat_main(question)


def _mode_of(facts: list[Fact], docs: list[dict]) -> Mode:
    """按实际用到的工具推断通路（证据来源决定 mode）。"""
    if facts and docs:
        return Mode.HYBRID
    if facts:
        return Mode.KG
    if docs:
        return Mode.RAG
    return Mode.DIRECT


__all__ = ["ToolCallingAgent", "REACT_SYSTEM", "RECURSION_LIMIT"]

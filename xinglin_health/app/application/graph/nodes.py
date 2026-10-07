"""LangGraph 图节点工厂（application 层）。

每个节点接收/返回 GraphState；所有技术访问经 domain 服务
（依赖链：application → domain → infrastructure）。降级逻辑集中在 route/fallback。
"""

import logging

from app.domain.rules import (
    INSUFFICIENT_ANSWER,
    build_risk_notice,
    is_insufficient,
    needs_risk_notice,
)
from app.domain.rules.query_guard import is_illegal_query
from app.domain.values import Mode

logger = logging.getLogger(__name__)

REFUSAL_ANSWER = "该请求可能影响系统数据安全，已被拒绝执行。请咨询健康相关问题。"


def _new_answer():
    from app.domain.entities import Answer
    return Answer()


def make_nodes(intent_service, kg_query_service, retrieval_service,
               generation_service, reliability_service):
    """闭包注入领域服务，返回 节点名 → 节点函数。"""

    # -- 意图识别（FR-002/003） ------------------------------------------
    def classify_intent(state: dict) -> dict:
        return {"intent": intent_service.classify(state["question"])}

    # -- 路由（FR-024 策略表 + 12.7 guard） --------------------------------
    def route(state: dict) -> dict:
        notes = list(state.get("notes", []))
        if is_illegal_query(state["question"]):
            logger.warning("非法查询被拦截: %s", state["question"][:50])
            return {"rejected": True, "mode": None, "notes": notes}

        intent = state.get("intent")
        # FR-024 策略（4.3 表）；fallback 已给出替代模式时直接采用
        if state.get("mode") is not None and state.get("retries", 0) > 0:
            return {"notes": notes}                       # fallback 换路后重入
        if intent is not None and intent.qa_type is not None:
            mode = Mode.KG
        elif intent is not None and intent.open_ended and intent.entity:
            mode = Mode.HYBRID
        elif intent is not None and intent.open_ended:
            mode = Mode.RAG
        else:
            mode = Mode.DIRECT

        # 检索通路可用性降级（12.2/12.3）：不可用则退化，不阻断
        if mode in (Mode.RAG, Mode.HYBRID) and not retrieval_service.available:
            notes.append("文献检索通路不可用，降级处理")
            mode = Mode.KG if (intent is not None and intent.qa_type is not None) else Mode.DIRECT
        return {"mode": mode, "notes": notes}

    # -- KG 通路（固定问答） ------------------------------------------------
    def kg_retrieve(state: dict) -> dict:
        intent = state["intent"]
        try:
            facts = kg_query_service.query(intent.qa_type, intent.entity or "")
            return {"kg_facts": facts,
                    "kg_failed": is_insufficient(len(facts), 0)}
        except Exception as e:  # noqa: BLE001 —— 12.1 KG 不可用（细节只进日志，ACC-031）
            logger.warning("KG retrieve failed: %s", e)
            return {"kg_facts": [], "kg_failed": True,
                    "notes": list(state.get("notes", [])) + ["知识图谱服务暂不可用，已按备用流程处理"]}

    # -- RAG 通路（文献混合检索） -------------------------------------------
    def rag_retrieve(state: dict) -> dict:
        try:
            docs = retrieval_service.retrieve(state["question"])
            return {"lit_docs": docs, "lit_failed": len(docs) == 0}
        except Exception as e:  # noqa: BLE001 —— 12.2 检索失败（细节只进日志）
            logger.warning("RAG retrieve failed: %s", e)
            return {"lit_docs": [], "lit_failed": True,
                    "notes": list(state.get("notes", [])) + ["文献检索服务暂不可用，已按备用流程处理"]}

    # -- 生成（FR-022 来源标识 + 10.4 风险提示） ------------------------------
    def generate(state: dict) -> dict:
        answer = generation_service.generate(
            question=state["question"], mode=state["mode"],
            kg_facts=state.get("kg_facts", []), lit_docs=state.get("lit_docs", []))
        if answer.risk_notice is None and needs_risk_notice(state["question"], answer.answer):
            answer.risk_notice = build_risk_notice()
        return {"answer": answer}

    # -- 可靠性检查（FR-023 分来源类型） --------------------------------------
    def reliability_check(state: dict) -> dict:
        answer = state["answer"]
        answer.reliability = reliability_service.check(
            state["mode"], state.get("kg_facts", []), state.get("lit_docs", []))
        return {"answer": answer, "reliability_done": True}

    # -- 备用处理（FR-026/027：换路重试 ≤2 次，最终兜底） ----------------------
    def fallback(state: dict) -> dict:
        retries = state.get("retries", 0) + 1
        notes = list(state.get("notes", []))
        tried = list(state.get("tried_modes", [])) + [state.get("mode").value if state.get("mode") else "none"]
        answer = state.get("answer") or _new_answer()

        # 重试预算用尽：按失败形态给兜底（查空→信息不足；故障→服务不可用）
        if retries >= 2:
            a = answer or _new_answer()
            a.status = "insufficient_info" if is_insufficient(
                len(state.get("kg_facts", [])), len(state.get("lit_docs", []))) else "service_unavailable"
            a.answer = a.answer or INSUFFICIENT_ANSWER
            return {"answer": a, "retries": retries, "tried_modes": tried,
                    "fallback_done": True, "notes": notes}

        # 换通路：走一次还没走过的可用检索路
        intent = state.get("intent")
        candidates: list[Mode] = []
        if retrieval_service.available:
            candidates += [Mode.RAG, Mode.HYBRID]
        if intent is not None and intent.qa_type is not None:
            candidates += [Mode.KG]
        for m in candidates:
            if m.value in tried:
                continue
            if m is Mode.HYBRID and not intent.entity:
                continue
            notes.append(f"备用切换检索模式 {mode} → {m}（FR-026）")
            return {"mode": m, "retries": retries, "tried_modes": tried,
                    "kg_failed": False, "lit_failed": False,
                    "fallback_done": False, "notes": notes}

        a = answer or _new_answer()
        a.status = "insufficient_info" if is_insufficient(
            len(state.get("kg_facts", [])), len(state.get("lit_docs", []))) else "service_unavailable"
        a.answer = a.answer or INSUFFICIENT_ANSWER
        return {"answer": a, "retries": retries, "tried_modes": tried,
                "fallback_done": True, "notes": notes}

    # -- 终节点：组装最终 Answer（拒绝/兜底话术在此落地） -----------------------
    def respond(state: dict) -> dict:
        answer = state.get("answer") or _new_answer()
        if state.get("rejected"):
            answer.status = "rejected"
            answer.answer = REFUSAL_ANSWER
            answer.sources = []
        if answer.risk_notice is None and needs_risk_notice(state["question"], answer.answer):
            answer.risk_notice = build_risk_notice()
        answer.meta = {"notes": state.get("notes", [])}
        return {"answer": answer}

    return {
        "classify_intent": classify_intent,
        "route": route,
        "kg_retrieve": kg_retrieve,
        "rag_retrieve": rag_retrieve,
        "generate": generate,
        "reliability_check": reliability_check,
        "fallback": fallback,
        "respond": respond,
    }

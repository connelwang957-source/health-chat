"""LangGraph 主图组装（技术文档 4.2 节拓扑）。"""

from langgraph.graph import END, START, StateGraph

from app.application.graph.state import GraphState
from app.domain.values import Mode


def build_graph(nodes: dict):
    g = StateGraph(GraphState)

    g.add_node("classify_intent", nodes["classify_intent"])
    g.add_node("route", nodes["route"])
    g.add_node("kg_retrieve", nodes["kg_retrieve"])
    g.add_node("rag_retrieve", nodes["rag_retrieve"])
    g.add_node("generate", nodes["generate"])
    g.add_node("reliability_check", nodes["reliability_check"])
    g.add_node("fallback", nodes["fallback"])
    g.add_node("respond", nodes["respond"])

    g.add_edge(START, "classify_intent")
    g.add_edge("classify_intent", "route")

    def route_branch(state: GraphState) -> str:
        if state.get("rejected"):
            return "rejected"
        return {Mode.KG: "kg", Mode.RAG: "rag", Mode.HYBRID: "kg",
                Mode.DIRECT: "direct"}.get(state.get("mode"), "direct")

    g.add_conditional_edges("route", route_branch, {
        "rejected": "respond", "kg": "kg_retrieve",
        "rag": "rag_retrieve", "direct": "generate"})

    def kg_branch(state: GraphState) -> str:
        if state.get("mode") is Mode.HYBRID:
            return "rag"           # FR-025 串行：KG 定位实体后继续查文献
        return "fallback" if state.get("kg_failed") else "generate"

    g.add_conditional_edges("kg_retrieve", kg_branch, {
        "rag": "rag_retrieve", "generate": "generate", "fallback": "fallback"})

    def rag_branch(state: GraphState) -> str:
        return "fallback" if state.get("lit_failed") else "generate"

    g.add_conditional_edges("rag_retrieve", rag_branch, {
        "generate": "generate", "fallback": "fallback"})

    g.add_edge("generate", "reliability_check")

    def rel_branch(state: GraphState) -> str:
        answer = state.get("answer")
        if answer is None or answer.status != "ok":
            return "respond"
        if answer.reliability is not None and answer.reliability.value == "low" \
                and state.get("mode") is not Mode.DIRECT:
            return "fallback"      # 依据不足 → 尝试其他来源（12.6）
        return "respond"

    g.add_conditional_edges("reliability_check", rel_branch, {
        "respond": "respond", "fallback": "fallback"})

    def fb_branch(state: GraphState) -> str:
        if state.get("fallback_done"):          # 重试预算用尽 → 终止
            return "respond"
        return {Mode.KG: "kg", Mode.RAG: "rag", Mode.HYBRID: "kg",
                Mode.DIRECT: "generate"}.get(state.get("mode"), "respond")

    g.add_conditional_edges("fallback", fb_branch, {
        "kg": "kg_retrieve", "rag": "rag_retrieve", "generate": "generate",
        "respond": "respond"})

    g.add_edge("respond", END)
    return g.compile()


def route_to_node_name(mode: Mode) -> str:
    return {Mode.KG: "kg_retrieve", Mode.RAG: "rag_retrieve",
            Mode.DIRECT: "generate", Mode.HYBRID: "kg_retrieve"}[mode]

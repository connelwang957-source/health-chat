"""工具集（对应文档 §5.4 的 `application/tools.py` 的 `build_tools`）。

给 `ToolCallingAgent` 的 ReAct 循环用：**由 LLM 自己决定调哪个工具、调几次**。

工具是薄封装 —— 真正的能力在 domain（图谱三层递进 / 文献混合检索），
这里只做"调用 + 记录观测 + 文本化"，因此不会出现第二套检索逻辑。

``collector`` 是调用方传入的字典，用来把工具实际取到的证据（facts / docs）回传，
以便上层做**来源标识**（FR-022）与**事实护栏**核对。
"""

from langchain_core.tools import tool

from xinglin.domain.entities import Fact


def _facts_to_text(facts: list[Fact]) -> str:
    if not facts:
        return "（图谱未返回任何结果）"
    return "\n".join(f"- {f.entity} [{f.relation}] {f.value}" for f in facts[:20])


def _docs_to_text(docs: list[dict]) -> str:
    if not docs:
        return "（文献未检索到相关片段）"
    lines: list[str] = []
    for i, d in enumerate(docs[:8], 1):
        meta = d.get("metadata") or {}
        title = meta.get("doc_title") or meta.get("source") or "未知文献"
        page = f"（第{meta['page']}页）" if meta.get("page") else ""
        lines.append(f"[{i}]《{title}》{page} {str(d.get('text', ''))[:200]}")
    return "\n".join(lines)


def build_tools(graph_query, literature_search, collector: dict | None = None) -> list:
    """构造 ReAct 可用的工具列表。

    :param graph_query: 可调用对象 ``(question) -> list[Fact]``，通常是图谱三层递进
    :param literature_search: 可调用对象 ``(query) -> list[dict]``，文献混合检索
    :param collector: 证据收集器（``{"facts": [], "docs": []}``），可为 None
    """
    bucket = collector if collector is not None else {}

    @tool
    def graph_search(question: str) -> str:
        """查询结构化健康知识图谱。

        输入一句自然语言问题（例：感冒有哪些症状），返回实体—关系—值形式的确定事实。
        适合疾病/症状/药品/食品/检查之间已建模的关系。
        """
        facts = graph_query(question) or []
        bucket.setdefault("facts", []).extend(facts)
        return _facts_to_text(facts)

    @tool
    def literature_search_tool(query: str) -> str:
        """检索医学文献库。

        输入检索式或疑问句（例：2型糖尿病 药物治疗 最新进展），返回相关文献片段。
        适合诊疗进展、机制、指南等图谱未覆盖的内容。
        """
        docs = literature_search(query) or []
        bucket.setdefault("docs", []).extend(docs)
        return _docs_to_text(docs)

    return [graph_search, literature_search_tool]


__all__ = ["build_tools"]

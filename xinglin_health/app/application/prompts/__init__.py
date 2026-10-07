"""prompts：回答模板（应用层资产，domain 不持有）。

模板文件独立存放便于版本管理与评审；loader 负责装配。
"""

from pathlib import Path

from app.domain.entities import Fact
from app.domain.values import Mode

PROMPT_DIR = Path(__file__).resolve().parent


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")


def build_intent_system_prompt() -> str:
    from app.domain.services import QA_TYPE_LIST
    return load_prompt("intent_system").format(qa_types=QA_TYPE_LIST)


def _kg_block(kg_facts: list[Fact]) -> str:
    if not kg_facts:
        return ""
    lines = [f"- {f.entity} ——[{f.relation}]→ {f.value}" for f in kg_facts]
    return "【结构化知识】（来源类型：结构化知识，优先采信）\n" + "\n".join(lines) + "\n"


def _lit_block(lit_docs: list[dict]) -> str:
    if not lit_docs:
        return ""
    lines = []
    for i, d in enumerate(lit_docs, 1):
        m = d.get("metadata", {})
        head = f"[{i}] 《{m.get('doc_title', '未知文献')}》"
        if m.get("page_num"):
            head += f"（第{m.get('page_num')}页）"
        lines.append(f"{head}\n{d['text']}")
    return "【医学文献资料】（来源类型：医学文献，引用时标注编号）\n" + "\n".join(lines) + "\n"


def build_generation_messages(question: str, kg_facts: list[Fact],
                              lit_docs: list[dict], mode: Mode) -> list:
    """组装生成节点的完整消息（system + human）。"""
    system = load_prompt("answer_system")
    context = _kg_block(kg_facts) + "\n" + _lit_block(lit_docs)
    human = f"用户问题：{question}\n\n{context}\n请按系统规则回答。"
    if mode is Mode.DIRECT:
        human = f"用户问题：{question}\n（本次为直接回答模式：不引用检索资料，谨慎给一般性建议并说明局限性）"
    return [("system", system), ("human", human)]

"""生成提示词（application 层资产，供 `GenerationService` 注入）。

prompt 单独成文件便于评审与版本管理；domain 不持有话术。

`build_generation_prompt` 的契约（与领域服务约定）：

    (question, kg_facts, docs, mode) -> (system, user)
"""

from xinglin.domain.entities import Fact
from xinglin.domain.values import Mode

ANSWER_SYSTEM = """你是杏林大健康的健康信息咨询助手，服务对象是健康咨询人员。

回答纪律：
1. 只能依据「结构化知识」与「医学文献资料」作答，不得编造数字、剂量、比例或结论；
2. 资料里没有的，明确说明"依据不足"，不要用常识补齐；
3. 引用文献时标注编号（如 [1][2]），便于回溯；
4. 不得给出确诊结论或用药处方；涉及诊疗时提示遵医嘱；
5. 中文作答，分点简洁，不超过 600 字。"""

DIRECT_SYSTEM = """你是杏林大健康的健康信息咨询助手。

本次是**直接回答**（不检索资料、不使用文献）：请用一般性健康常识谨慎作答，
明确说明这只是科普信息、不能替代医生面诊，涉及具体病情请建议就医。"""


def _kg_block(kg_facts: list[Fact]) -> str:
    if not kg_facts:
        return ""
    lines = [f"- {f.entity} ——[{f.relation}]→ {f.value}" for f in kg_facts]
    return ("【结构化知识】（来源类型：结构化知识，优先采信）\n"
            + "\n".join(lines) + "\n")


def _docs_block(docs: list[dict]) -> str:
    if not docs:
        return ""
    lines = []
    for i, d in enumerate(docs, 1):
        meta = d.get("metadata") or {}
        title = meta.get("doc_title") or meta.get("source") or "未知文献"
        head = f"[{i}]《{title}》"
        if meta.get("page"):
            head += f"（第{meta['page']}页）"
        lines.append(f"{head}\n{d.get('text', '')}")
    return ("【医学文献资料】（来源类型：医学文献，引用时标注编号）\n"
            + "\n".join(lines) + "\n")


def build_generation_prompt(question: str, kg_facts: list[Fact],
                            docs: list[dict], mode: Mode) -> tuple[str, str]:
    """组装生成的 (system, user) 两段消息。"""
    if mode is Mode.DIRECT:
        return DIRECT_SYSTEM, (
            f"用户问题：{question}\n"
            "（本次为直接回答模式：不引用检索资料，谨慎给一般性建议并说明局限性）")

    context = _kg_block(kg_facts) + "\n" + _docs_block(docs)
    return ANSWER_SYSTEM, f"用户问题：{question}\n\n{context}\n请按系统规则回答。"


__all__ = ["ANSWER_SYSTEM", "DIRECT_SYSTEM", "build_generation_prompt"]

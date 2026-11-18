# -*- coding: utf-8 -*-
"""
事实护栏（防幻觉后处理）：答案输出前，用 LLM 核查答案中的关键医学陈述
是否都能在参考上下文中找到依据。核查失败时降级放行，不阻塞主流程。
"""

import json
from typing import Any, Dict

from xinglin.domain.entities import Fact
from xinglin.domain.ports import LLM

FACT_CHECK_SYSTEM = (
    "你是一个严格的医学事实核查员。你的唯一任务是判断「待核查答案」中的关键医学陈述"
    "是否都能在「参考上下文」中找到依据，从而防止模型编造不真实的信息。"
)

FACT_CHECK_USER = """请核查下面答案的事实性。
<参考上下文>
{context}
</参考上下文>

<待核查答案>
{answer}
</待核查答案>

要求：
1. 提取答案中所有关键的事实性陈述（疾病名称、症状、病因、治疗方式、药品、就诊科室、检查项目、预防措施等）。
2. 逐条判断是否能在参考上下文中找到依据。
3. 只输出一个 JSON 对象，不要输出任何多余文字，格式如下：
{{"grounded": true 或 false, "unsupported": ["无依据的陈述1", "无依据的陈述2"], "reason": "一句话说明"}}
"""


def _strip_fence(text: str) -> str:
    """清理 LLM 可能输出的 markdown 代码块包裹。"""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
        t = t.strip()
    return t


class FactGuardrail:
    """事实护栏：基于上下文核查答案，返回 {grounded, unsupported, reason}。"""

    def __init__(self, llm: LLM):
        self.llm = llm

    def check(self, answer: str, context: str) -> Dict[str, Any]:
        """核查答案是否有据可依。无上下文或解析失败时降级为放行（grounded=True）。"""
        if not context:
            return {
                "grounded": True,
                "unsupported": [],
                "reason": "无参考上下文，跳过核查",
            }

        raw = ""
        try:
            user_prompt = FACT_CHECK_USER.format(context=context, answer=answer)
            raw = self.llm.complete(FACT_CHECK_SYSTEM, user_prompt, temperature=0.0)
            parsed = json.loads(_strip_fence(raw))
            grounded = bool(parsed.get("grounded", True))
            unsupported = parsed.get("unsupported", []) or []
            reason = parsed.get("reason", "")
            return {
                "grounded": grounded,
                "unsupported": unsupported,
                "reason": reason,
                "raw": raw,
            }
        except Exception as e:      # noqa: BLE001 —— 护栏只降级、不阻塞
            return {
                "grounded": True,
                "unsupported": [],
                "reason": f"核查解析失败，跳过（{e}）",
                "raw": raw,
            }


def add_unsupported_note(answer: str, unsupported: list[str]) -> str:
    """无依据时在答案末尾追加提醒（文档 §9 `_guard` 的原文措辞）。

    医疗场景选「提醒不拦截」：追加说明而不是撤下回答，责任边界更清楚。
    """
    items = "、".join(unsupported[:5])
    note = "\n\n（提醒：以上回答中部分内容"
    if items:
        note += f"（{items}）"
    note += "在当前知识库中未找到直接依据，请谨慎参考。）"
    return answer + note


def build_context(facts: list[Fact] | None, docs: list[dict] | None) -> str:
    """拼接护栏核查用的**证据上下文**（两类证据合起来作为"参考依据"）。

    这是护栏的输入之一，与"答案"配对送去核查。图谱事实给出确定关系，
    文献片段给出论述依据——核查判的是"答案能否被这份上下文支撑"。
    """
    parts: list[str] = []
    if facts:
        parts.append("【知识图谱事实】\n"
                     + "\n".join(f"{f.entity} {f.relation} {f.value}" for f in facts))
    if docs:
        parts.append("【检索文档】\n"
                     + "\n".join(str(d.get("text", "")) for d in docs))
    return "\n\n".join(parts)


def guard_answer(answer_text: str, context: str,
                 guardrail: "FactGuardrail | None") -> str:
    """对答案执行事实护栏，返回**最终要交付给用户的文本**。

    「提醒不拦截」：核查未通过时**保留原答案**，只在末尾追加"请谨慎参考"提醒
    （理由与措辞见 `add_unsupported_note`）。

    以下情况原样返回（护栏自身降级，不阻塞主流程）：
    - 护栏未装配或已关闭；
    - 证据上下文为空（如纯寒暄的通路，本就没有可核查的依据）。

    **任何对话链路都应经过本函数**——它是"答案级"的最后一关，
    与生成逻辑无关，所以放在护栏模块里供各链路复用。
    """
    if guardrail is None or not context:
        return answer_text
    verdict = guardrail.check(answer_text, context)
    if verdict.get("grounded"):
        return answer_text
    return add_unsupported_note(answer_text, verdict.get("unsupported") or [])


__all__ = ["FactGuardrail", "add_unsupported_note", "build_context", "guard_answer",
           "FACT_CHECK_SYSTEM", "FACT_CHECK_USER"]

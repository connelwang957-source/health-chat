# -*- coding: utf-8 -*-
"""
事实护栏（防幻觉后处理）：答案输出前，用 LLM 核查答案中的关键医学陈述
是否都能在参考上下文中找到依据。核查失败时降级放行，不阻塞主流程。
"""

import json
from typing import Any, Dict

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


__all__ = ["FactGuardrail", "add_unsupported_note",
           "FACT_CHECK_SYSTEM", "FACT_CHECK_USER"]

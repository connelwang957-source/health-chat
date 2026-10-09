# -*- coding: utf-8 -*-
"""domain/guardrail：事实护栏（防幻觉后处理）。

对应《项目开发指导》§9.1 的 `domain/guardrail/fact_guardrail.py`：
只依赖 `domain/ports.py` 的 `LLM` 协议，是医疗问答的领域约束——
「答案必须能在参考上下文里找到依据，否则标注出来」。
"""

from xinglin.domain.guardrail.fact_guardrail import (
    FactGuardrail,
    add_unsupported_note,
)

__all__ = ["FactGuardrail", "add_unsupported_note"]

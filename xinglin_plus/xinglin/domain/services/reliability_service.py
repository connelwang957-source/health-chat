"""ReliabilityService：FR-023 依据分级（domain 领域服务）。

只做一件事：按证据来源类型给 `high / partial / low`。

**事实护栏不在本类**——按文档 §9.1，它是独立的 `domain.guardrail.FactGuardrail`
（用 LLM 二次核查），不属于"依据分级"。
"""

from xinglin.domain.entities import Fact
from xinglin.domain.values import Mode, Reliability


class ReliabilityService:

    # -- FR-023 依据分级 -----------------------------------------------------
    def check(self, mode: Mode | None, kg_facts: list[Fact], docs: list[dict]) -> Reliability:
        value = getattr(mode, "value", mode)
        if value == Mode.DIRECT.value:
            return Reliability.LOW
        has_kg, has_lit = bool(kg_facts), bool(docs)
        if has_kg and not has_lit:
            return Reliability.HIGH          # 结构化精确知识，依据充分
        if has_lit:
            return Reliability.PARTIAL       # 含文献（多来源综合 / 仅文献）
        return Reliability.LOW               # 无依据 → 10.3 信息不足

    # -- 提示语（可选接入） --------------------------------------------------
    @staticmethod
    def reliability_notice(reliability: Reliability) -> str:
        """按可靠性级别生成给用户看的提示语（FR-023：避免让用户误认为已确认为事实）。"""
        return {
            Reliability.HIGH: "以上内容来自结构化健康知识库，依据充分。",
            Reliability.PARTIAL: "以上内容综合了知识库与文献资料，部分内容仅供参考。",
            Reliability.LOW: "以上内容依据不足，仅供参考，请勿作为诊疗依据。",
        }[reliability]


__all__ = ["ReliabilityService"]

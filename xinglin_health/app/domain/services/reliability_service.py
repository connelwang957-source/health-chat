"""ReliabilityService：FR-023 回答可靠性判断（分来源类型）。"""

from app.domain.entities import Fact
from app.domain.values import Reliability, SourceType


class ReliabilityService:
    """V1 采用确定性规则；LLM 自检通道（per FR-023 提示语）预留为 P1 增强。"""

    def check(self, mode, kg_facts: list[Fact], lit_docs: list[dict]) -> Reliability:
        if mode is not None and getattr(mode, "value", mode) == "direct":
            return Reliability.LOW
        has_kg, has_lit = bool(kg_facts), bool(lit_docs)
        if has_kg and not has_lit:
            return Reliability.HIGH      # 结构化精确知识，依据充分
        if has_lit and has_kg:
            return Reliability.PARTIAL   # 多来源综合，提示按类型区分
        if has_lit:
            return Reliability.PARTIAL
        return Reliability.LOW           # 无依据 → 10.3 信息不足

    @staticmethod
    def reliability_notice(reliability: Reliability) -> str:
        """按可靠性级别生成给用户看的提示语（FR-023：避免让用户误认为已确认为事实）。"""
        return {
            Reliability.HIGH: "以上内容来自结构化健康知识库，依据充分。",
            Reliability.PARTIAL: "以上内容综合了知识库与文献资料，部分内容仅供参考。",
            Reliability.LOW: "以上内容依据不足，仅供参考，请勿作为诊疗依据。",
        }[reliability]

    @staticmethod
    def source_type_breakdown(sources) -> dict[str, int]:
        """来源类型计数（FR-022/FR-023：分类型可见）。"""
        from collections import Counter
        return {SourceType(t).label: n for t, n in Counter(s.type for s in sources).items()}

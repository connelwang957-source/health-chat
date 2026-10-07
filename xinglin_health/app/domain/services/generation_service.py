"""GenerationService：回答生成（领域服务）。

LLM 不可用时退化为模板组装（开发/降级形态），保证管道完整可跑。
来源标识（FR-022）与风险提示（10.4）在此强制落地。
"""

from app.domain.entities import Answer, Fact, Source
from app.domain.rules import build_risk_notice, needs_risk_notice
from app.domain.values import Mode, SourceType


class GenerationService:
    def __init__(self, llm_gateway=None, prompt_builder=None):
        # prompt_builder: application.prompts.build_generation_messages（应用层资产）
        self._llm = llm_gateway
        self._prompt_builder = prompt_builder

    def generate(self, question: str, mode: Mode,
                 kg_facts: list[Fact], lit_docs: list[dict]) -> Answer:
        sources = self._build_sources(kg_facts, lit_docs)

        if mode is Mode.DIRECT or self._llm is None or not self._llm.available:
            answer = self._template_answer(question, mode, kg_facts, lit_docs)
        else:
            messages = self._prompt_builder(
                question=question, kg_facts=kg_facts, lit_docs=lit_docs, mode=mode)
            answer = self._llm.generate(messages).strip()

        risk = build_risk_notice() if needs_risk_notice(question, answer) else None
        reliability = self._default_reliability(mode, kg_facts, lit_docs)
        return Answer(status="ok", mode=mode, answer=answer, sources=sources,
                      reliability=reliability, risk_notice=risk)

    # -- 来源构建（FR-022：来源类型必标） -----------------------------------
    @staticmethod
    def _build_sources(kg_facts, lit_docs) -> list[Source]:
        out: list[Source] = []
        for f in kg_facts:
            out.append(Source(type=SourceType.KG, label=SourceType.KG.label,
                              relation=f.relation, entity=f.entity))
        seen_titles: set[str] = set()
        for i, d in enumerate(lit_docs, 1):
            m = d.get("metadata", {})
            title = m.get("doc_title") or f"文献片段{i}"
            if title in seen_titles:
                continue
            seen_titles.add(title)
            out.append(Source(type=SourceType.LIT, label=SourceType.LIT.label,
                              title=title, journal=m.get("journal"),
                              year=m.get("year"), doi=m.get("doi"),
                              url=m.get("url"),
                              loc=f"第{m.get('page_num')}页" if m.get("page_num") else None))
        return out

    @staticmethod
    def _default_reliability(mode, kg_facts, lit_docs):
        from app.domain.values import Reliability
        if mode is Mode.DIRECT:
            return Reliability.LOW  # direct 无检索依据，提示由前端展示
        if kg_facts and not lit_docs:
            return Reliability.HIGH
        if lit_docs:
            return Reliability.PARTIAL
        return Reliability.LOW

    # -- LLM 不可用时的模板组装（12.3 备用回答形态之一） --------------------
    @staticmethod
    def _template_answer(question, mode, kg_facts, lit_docs) -> str:
        parts: list[str] = []
        if kg_facts:
            grouped: dict[str, list[str]] = {}
            for f in kg_facts:
                grouped.setdefault(f.relation, []).append(f.value)
            for rel, values in grouped.items():
                parts.append(f"根据健康知识库，与「{kg_facts[0].entity}」相关的{rel}信息包括："
                             + "、".join(values[:10]) + "。")
        if lit_docs:
            refs = "；".join(
                f"《{d['metadata'].get('doc_title', '文献')}"
                f"（{d['metadata'].get('page_num', '') and '第%s页' % d['metadata']['page_num']}）》"
                for d in lit_docs[:3])
            parts.append(f"以下资料可供参考：{refs}。")
        if not parts:
            parts.append("当前未检索到足够依据，无法给出有把握的回答。")
            parts.append("建议您补充问题细节或咨询专业医生。")
        return "\n".join(parts)

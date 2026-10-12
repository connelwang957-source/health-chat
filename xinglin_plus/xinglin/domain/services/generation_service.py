"""GenerationService：回答生成（domain 领域服务）。

职责：
- 把图谱事实 + 文献片段交给 LLM 组织成中文回答；
- **强制来源标识**（FR-022：每条来源标 `kg` / `lit`）；
- **风险提示**（第 10.4 条）；
- LLM 不可用时退化为模板组装（内容 100% 来自证据，零幻觉）。

prompt 属于应用层资产，由组合根以 ``prompt_builder`` 注入（domain 不持有）。
`prompt_builder(question=..., kg_facts=..., docs=..., mode=...) -> (system, user)`。
"""

import logging

from xinglin.domain.entities import Answer, Fact, Source
from xinglin.domain.ports import LLM
from xinglin.domain.rules import build_risk_notice, needs_risk_notice, render_facts
from xinglin.domain.values import Mode, Reliability, SourceType

logger = logging.getLogger(__name__)


class GenerationService:
    def __init__(self, llm: LLM | None = None, prompt_builder=None):
        self._llm = llm
        self._prompt_builder = prompt_builder

    # -- 主入口 -------------------------------------------------------------
    def generate(self, question: str, mode: Mode,
                 kg_facts: list[Fact], docs: list[dict]) -> Answer:
        sources = self._build_sources(kg_facts, docs)

        if mode is Mode.DIRECT or self._llm is None or not getattr(self._llm, "available", False):
            text = self.template_answer(question, mode, kg_facts, docs)
        else:
            # 12.3 回答生成失败 / Key 失效：**绝不能把异常抛给用户**。
            # 失败（含返回空内容）一律降级为模板组装——内容 100% 来自证据、零幻觉。
            try:
                system, user = self._prompt_builder(question=question, kg_facts=kg_facts,
                                                    docs=docs, mode=mode)
                text = self._llm.complete(system, user,
                                          temperature=0.3, max_tokens=800).strip()
            except Exception as exc:        # noqa: BLE001 —— 降级链路的一部分
                logger.warning("[生成失败] 降级为模板回答：%s: %s", type(exc).__name__, exc)
                text = ""
            if not text:
                text = self.template_answer(question, mode, kg_facts, docs)

        return self.compose(question, mode, text, kg_facts, docs)

    def compose(self, question: str, mode: Mode, answer_text: str,
                kg_facts: list[Fact], docs: list[dict]) -> Answer:
        """用**外部已生成**的答案文本组装 Answer（来源标识 / 风险提示 / 默认分级复用）。"""
        risk = build_risk_notice() if needs_risk_notice(question, answer_text) else None
        return Answer(status="ok", mode=mode, answer=answer_text,
                      sources=self._build_sources(kg_facts, docs),
                      reliability=self._default_reliability(mode, kg_facts, docs),
                      risk_notice=risk)

    # -- 来源构建（FR-022） --------------------------------------------------
    @staticmethod
    def _build_sources(kg_facts: list[Fact], docs: list[dict]) -> list[Source]:
        out: list[Source] = []
        for f in kg_facts:
            out.append(Source(type=SourceType.KG, label=SourceType.KG.label,
                              relation=f.relation, entity=f.entity))
        seen_titles: set[str] = set()
        for i, d in enumerate(docs, 1):
            meta = d.get("metadata") or {}
            title = meta.get("doc_title") or meta.get("source") or f"文献片段{i}"
            if title in seen_titles:
                continue
            seen_titles.add(title)
            out.append(Source(type=SourceType.LIT, label=SourceType.LIT.label,
                              title=title, journal=meta.get("journal"),
                              year=meta.get("year"), doi=meta.get("doi"),
                              url=meta.get("url"),
                              loc=f"第{meta['page']}页" if meta.get("page") else None))
        return out

    @staticmethod
    def _default_reliability(mode: Mode, kg_facts, docs) -> Reliability:
        if mode is Mode.DIRECT:
            return Reliability.LOW
        if kg_facts and not docs:
            return Reliability.HIGH
        if docs:
            return Reliability.PARTIAL
        return Reliability.LOW

    # -- 模板化回答（护栏兜底 / LLM 不可用） ---------------------------------
    @classmethod
    def template_answer(cls, question: str, mode: Mode,
                        kg_facts: list[Fact], docs: list[dict]) -> str:
        """内容 100% 来自证据，零幻觉；话术实现唯一在 `domain.rules.render_facts`。"""
        parts: list[str] = []
        if kg_facts:
            text = render_facts(kg_facts[0].entity, kg_facts)
            if text:
                parts.append(text)
        if docs:
            refs = "；".join(
                f"《{(d.get('metadata') or {}).get('doc_title') or (d.get('metadata') or {}).get('source') or '文献'}"
                f"{'第%s页' % (d.get('metadata') or {}).get('page') if (d.get('metadata') or {}).get('page') else ''}》"
                for d in docs[:3])
            parts.append(f"以下资料可供参考：{refs}。")
        if not parts:
            parts.append("当前未检索到足够依据，无法给出有把握的回答。")
            parts.append("建议您补充问题细节或咨询专业医生。")
        return "\n".join(parts)


__all__ = ["GenerationService"]

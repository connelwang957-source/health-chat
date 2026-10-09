"""Agent 编排：证据收集、FR-026 备用处理（换通路重试）、降级不抛出。

全部用替身注入，不连 Neo4j / Milvus / LLM。
"""

from xinglin.application.hybrid_agent import HybridAgent
from xinglin.domain.entities import Answer, Fact, Intent
from xinglin.domain.values import Mode, QAType, Reliability


class _StubIntent:
    def __init__(self, intent: Intent):
        self._intent = intent

    def classify(self, question: str) -> Intent:
        return self._intent


class _StubCollector:
    """KG 证据替身。"""

    def __init__(self, facts: list[Fact] | None = None):
        self.facts = facts if facts is not None else []
        self.calls = 0

    def collect_facts(self, question: str, intent=None) -> list[Fact]:
        self.calls += 1
        return self.facts


class _StubRag:
    """文献证据替身。"""

    def __init__(self, docs: list[dict] | None = None):
        self.docs = docs if docs is not None else []

    def collect_docs(self, question: str) -> list[dict]:
        return self.docs


class _StubGeneration:
    def __init__(self, text: str = "答案"):
        self.text = text
        self.calls: list[tuple] = []

    def generate(self, question, mode, kg_facts, docs) -> Answer:
        self.calls.append((mode, list(kg_facts), list(docs)))
        return Answer(mode=mode, answer=self.text)

    def compose(self, question, mode, answer_text, kg_facts, docs) -> Answer:
        return Answer(mode=mode, answer=answer_text)


class _StubGuardrail:
    """事实护栏替身：避免单测里真调 LLM（文档 §9 的护栏另有专门测试）。"""

    def __init__(self, grounded: bool = True, unsupported: list[str] | None = None):
        self.grounded = grounded
        self.unsupported = unsupported or []
        self.calls: list[tuple[str, str]] = []

    def check(self, answer: str, context: str) -> dict:
        self.calls.append((answer, context))
        return {"grounded": self.grounded, "unsupported": self.unsupported,
                "reason": "", "raw": ""}


_FACT = Fact(entity="感冒", relation="has_symptom", value="咳嗽")
_DOC = {"text": "感冒以对症支持为主。", "metadata": {"source": "A.pdf", "page": 1}}


def _agent(intent: Intent, facts=None, docs=None, generation=None,
           guardrail=None) -> tuple[HybridAgent, _StubGeneration]:
    gen = generation or _StubGeneration()
    agent = HybridAgent(intent=_StubIntent(intent),
                        nl2cypher_agent=_StubCollector(facts),
                        rag_agent=_StubRag(docs),
                        generation=gen,
                        guardrail=guardrail or _StubGuardrail())
    return agent, gen


class TestGather:
    def test_kg_mode_collects_only_facts(self):
        agent, _ = _agent(Intent(qa_type=QAType.DISEASE_SYMPTOM, entity="感冒"),
                          facts=[_FACT], docs=[_DOC])
        facts, docs = agent._gather("感冒有什么症状", None, Mode.KG)
        assert facts and not docs

    def test_rag_mode_collects_only_docs(self):
        agent, _ = _agent(Intent(open_ended=True), facts=[_FACT], docs=[_DOC])
        facts, docs = agent._gather("随便问问", None, Mode.RAG)
        assert docs and not facts

    def test_hybrid_mode_collects_both(self):
        agent, _ = _agent(Intent(open_ended=True, entity="糖尿病"), facts=[_FACT], docs=[_DOC])
        facts, docs = agent._gather("糖尿病新进展", None, Mode.HYBRID)
        assert facts and docs

    def test_direct_mode_collects_nothing(self):
        agent, _ = _agent(Intent(), facts=[_FACT], docs=[_DOC])
        facts, docs = agent._gather("你好", None, Mode.DIRECT)
        assert not facts and not docs


class TestAnswerPath:
    def test_answer_is_finalised_with_reliability(self):
        agent, _ = _agent(Intent(qa_type=QAType.DISEASE_SYMPTOM, entity="感冒"), facts=[_FACT])
        answer = agent.chat_main("感冒有什么症状？")
        assert answer.mode is Mode.KG
        assert answer.reliability is Reliability.HIGH       # 仅结构化知识 → 依据充分

    def test_literature_lowers_reliability_to_partial(self):
        agent, _ = _agent(Intent(open_ended=True), docs=[_DOC])
        answer = agent.chat_main("高血压怎么办")
        assert answer.reliability is Reliability.PARTIAL


class TestRetry:
    def test_retries_when_evidence_is_empty(self):
        """首次 KG 无证据（low）→ 应换通路重试（FR-026）。"""
        agent, gen = _agent(Intent(qa_type=QAType.DISEASE_SYMPTOM, entity="感冒"),
                            facts=[], docs=[_DOC])
        answer = agent.chat_main("感冒有什么症状？")
        assert len(gen.calls) > 1, "依据不足时应换通路重试"
        assert answer.mode in (Mode.RAG, Mode.HYBRID)

    def test_no_retry_when_evidence_sufficient(self):
        agent, gen = _agent(Intent(qa_type=QAType.DISEASE_SYMPTOM, entity="感冒"), facts=[_FACT])
        agent.chat_main("感冒有什么症状？")
        assert len(gen.calls) == 1


class TestGuardrailApplied:
    """护栏在 Agent 内落地（文档 §9 数据流：召回 → 生成 → 事实护栏）。"""

    def test_unsupported_note_is_appended(self):
        guardrail = _StubGuardrail(grounded=False, unsupported=["编造内容"])
        agent, _ = _agent(Intent(qa_type=QAType.DISEASE_SYMPTOM, entity="感冒"),
                          facts=[_FACT], guardrail=guardrail)
        answer = agent.chat_main("感冒有什么症状？")
        assert "请谨慎参考" in answer.answer
        assert "编造内容" in answer.answer

    def test_guardrail_receives_fused_context(self):
        guardrail = _StubGuardrail()
        agent, _ = _agent(Intent(qa_type=QAType.DISEASE_SYMPTOM, entity="感冒"),
                          facts=[_FACT], guardrail=guardrail)
        agent.chat_main("感冒有什么症状？")
        assert guardrail.calls, "拿到证据后必须核查一次"
        _, context = guardrail.calls[0]
        assert "咳嗽" in context, "护栏依据应是拼接后的证据文本"

    def test_grounded_answer_untouched(self):
        agent, _ = _agent(Intent(qa_type=QAType.DISEASE_SYMPTOM, entity="感冒"), facts=[_FACT])
        assert agent.chat_main("感冒有什么症状？").answer == "答案"

    def test_no_context_skips_guardrail(self):
        """direct 通路没有证据 → 护栏自动跳过（文档 §9：未调工具则 context 为空）。"""
        guardrail = _StubGuardrail()
        agent, _ = _agent(Intent(), guardrail=guardrail)
        agent.chat_main("你好")
        assert guardrail.calls == []

    def test_guardrail_can_be_disabled(self):
        guardrail = _StubGuardrail(grounded=False, unsupported=["x"])
        agent = HybridAgent(intent=_StubIntent(Intent(qa_type=QAType.DISEASE_SYMPTOM,
                                                      entity="感冒")),
                            nl2cypher_agent=_StubCollector([_FACT]),
                            rag_agent=_StubRag(), generation=_StubGeneration(),
                            enable_guardrail=False, guardrail=guardrail)
        assert "请谨慎参考" not in agent.chat_main("感冒有什么症状？").answer

"""意图分类（LLM 通道 + 规则通道）与 FR-024 自动选路。

这里固化两条**回归要点**：
1. 开放式信号不能被关键词抢走（否则"有哪些新进展"会答"资料未收录"）；
2. 寒暄 / 常识（无实体、无类型、非开放式）必须走 `direct`，不去空检索。
"""

import pytest

from xinglin.application.hybrid_agent import HybridAgent
from xinglin.application.runtime import needs_retry
from xinglin.domain.entities import Answer, Intent
from xinglin.domain.services.intent_service import IntentService
from xinglin.domain.values import Mode, QAType, Reliability
from tests.conftest import FakeLLM, FakeRecognizer


def _rule_service() -> IntentService:
    """不传 LLM → 强制走规则通道。"""
    return IntentService(llm=None, recognizer=FakeRecognizer({"感冒": "Disease"}))


class TestRuleChannel:
    def test_keyword_hit_gives_qa_type(self):
        intent = _rule_service().classify("感冒有什么症状？")
        assert intent.qa_type is QAType.DISEASE_SYMPTOM
        assert intent.open_ended is False
        assert intent.decided_by == "rule"

    def test_open_question_is_not_hijacked_by_keyword(self):
        intent = _rule_service().classify("2型糖尿病的药物治疗有哪些新进展？")
        assert intent.open_ended is True

    def test_greeting_is_not_open_ended(self):
        """"你好"没有类型也没有实体，但**不是**开放式问题。"""
        assert _rule_service().classify("你好").open_ended is False

    def test_entity_comes_from_dictionary(self):
        intent = _rule_service().classify("感冒有什么症状？")
        assert intent.entity == "感冒"
        assert intent.entity_type == "疾病"


class TestLLMChannel:
    def test_json_intent_is_parsed(self):
        llm = FakeLLM(reply='{"entity":"感冒","entity_type":"疾病",'
                            '"qa_type_code":1,"open_ended":false}')
        intent = IntentService(llm=llm, recognizer=FakeRecognizer()).classify("感冒有什么症状")
        assert intent.qa_type is QAType.DISEASE_SYMPTOM
        assert intent.decided_by == "llm"

    def test_model_declared_open_ended(self):
        llm = FakeLLM(reply='{"entity":"糖尿病","entity_type":"疾病",'
                            '"qa_type_code":null,"open_ended":true}')
        intent = IntentService(llm=llm, recognizer=FakeRecognizer()).classify("随便问问")
        assert intent.open_ended is True

    def test_bad_json_degrades_to_rules(self):
        llm = FakeLLM(reply="这不是 JSON")
        intent = IntentService(llm=llm,
                               recognizer=FakeRecognizer({"感冒": "Disease"})
                               ).classify("感冒有什么症状？")
        assert intent.decided_by == "rule"
        assert intent.qa_type is QAType.DISEASE_SYMPTOM

    def test_unavailable_llm_goes_rules(self):
        llm = FakeLLM(reply="{}", available=False)
        intent = IntentService(llm=llm, recognizer=FakeRecognizer()).classify("感冒有什么症状？")
        assert intent.decided_by == "rule"


class TestRouting:
    @pytest.mark.parametrize("intent,expected", [
        (Intent(open_ended=True, entity="糖尿病"), Mode.HYBRID),      # 开放式 + 实体 → 双路
        (Intent(open_ended=True), Mode.RAG),                          # 开放式无实体 → 文献
        (Intent(qa_type=QAType.DISEASE_SYMPTOM, entity="感冒"), Mode.KG),
        (Intent(entity="感冒"), Mode.KG),                              # 非开放式有实体 → 结构化
        (Intent(), Mode.DIRECT),                                      # 寒暄/常识 → 不检索
        (Intent(qa_type=QAType.DISEASE_SYMPTOM, entity="感冒",
                open_ended=True), Mode.HYBRID),                       # 开放式优先
    ])
    def test_route(self, intent, expected):
        assert HybridAgent._route(intent) is expected

    def test_next_mode_skips_tried(self):
        assert HybridAgent._next_mode({Mode.HYBRID, Mode.RAG}) is Mode.KG
        assert HybridAgent._next_mode({Mode.HYBRID, Mode.RAG, Mode.KG}) is None


class TestNeedsRetry:
    def test_low_reliability_triggers_retry(self):
        answer = Answer(mode=Mode.KG, reliability=Reliability.LOW)
        assert needs_retry(answer) is True

    def test_sufficient_reliability_does_not_retry(self):
        assert needs_retry(Answer(mode=Mode.KG, reliability=Reliability.HIGH)) is False

    def test_direct_never_retries(self):
        assert needs_retry(Answer(mode=Mode.DIRECT, reliability=Reliability.LOW)) is False

    def test_non_ok_status_never_retries(self):
        answer = Answer(status="insufficient_info", mode=Mode.KG, reliability=Reliability.LOW)
        assert needs_retry(answer) is False

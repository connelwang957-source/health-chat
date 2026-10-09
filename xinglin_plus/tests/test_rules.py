"""第 10 章业务规则 + 开放式判定：纯函数、零 I/O，可完全离线验证。"""

import pytest

from xinglin.domain.entities import Fact
from xinglin.domain.rules import (
    OPEN_MARKERS,
    adjust_food_qa_type,
    build_risk_notice,
    default_qa_type,
    dedup_values,
    has_symptom_expression,
    is_illegal_query,
    is_insufficient,
    is_open_ended,
    judge_diet_direction,
    match_keyword,
    needs_risk_notice,
    render_facts,
)
from xinglin.domain.values import QAType


def _fact(value: str, relation: str = "has_symptom") -> Fact:
    return Fact(entity="感冒", relation=relation, value=value)


class TestDedupValues:
    def test_dedup_keeps_order(self):
        assert dedup_values([_fact("咳嗽"), _fact("发热"), _fact("咳嗽")]) == ["咳嗽", "发热"]

    def test_drops_blank_and_none_literal(self):
        assert dedup_values([_fact("None"), _fact(" "), _fact("咳嗽")]) == ["咳嗽"]

    def test_respects_limit(self):
        assert len(dedup_values([_fact(f"v{i}") for i in range(20)], limit=3)) == 3

    def test_empty_input(self):
        assert dedup_values([]) == []


class TestRenderFacts:
    def test_mentions_entity_and_value(self):
        text = render_facts("感冒", [_fact("咳嗽")], QAType.DISEASE_SYMPTOM)
        assert "感冒" in text and "咳嗽" in text

    def test_empty_facts_returns_empty_string(self):
        assert render_facts("感冒", [], QAType.DISEASE_SYMPTOM) == ""

    def test_renders_without_qa_type(self):
        assert render_facts("感冒", [_fact("咳嗽")]) != ""


class TestKeywordIntent:
    def test_hits_symptom_type(self):
        matched = match_keyword("感冒有什么症状")
        assert matched is not None
        assert matched[0] is QAType.DISEASE_SYMPTOM

    def test_empty_question_matches_nothing(self):
        assert match_keyword("") is None


class TestOpenness:
    @pytest.mark.parametrize("question", [
        "2型糖尿病的药物治疗有哪些新进展？",
        "这两种降压药有什么区别？",
        "为什么会得高血压？",
        "高血压的发病机制是什么？",
    ])
    def test_open_questions(self, question):
        assert is_open_ended(question) is True

    @pytest.mark.parametrize("question", [
        "感冒有什么症状？",          # 固定问答常用"有哪些"，不能当开放信号
        "糖尿病不能吃什么？",
        "阿莫西林主要用于哪些疾病？",
    ])
    def test_fixed_questions_are_not_open(self, question):
        assert is_open_ended(question) is False

    def test_marker_table_is_not_empty(self):
        assert OPEN_MARKERS


class TestDietRule:
    def test_restrict_direction(self):
        assert judge_diet_direction("螃蟹不能吃吗") == "restrict"

    def test_adjust_returns_food_type(self):
        adjusted = adjust_food_qa_type("螃蟹能吃吗", QAType.FOOD_DISEASE_RECOMMEND)
        assert adjusted in QAType.food_types()

    def test_non_food_type_untouched(self):
        assert adjust_food_qa_type("感冒", QAType.DISEASE_SYMPTOM) is QAType.DISEASE_SYMPTOM


class TestInsufficiency:
    def test_both_empty_is_insufficient(self):
        assert is_insufficient(0, 0) is True

    @pytest.mark.parametrize("facts,docs", [(1, 0), (0, 1), (2, 3)])
    def test_any_evidence_is_enough(self, facts, docs):
        assert is_insufficient(facts, docs) is False


class TestQueryGuard:
    def test_illegal_write_query_blocked(self):
        assert is_illegal_query("drop table users") is True

    def test_normal_health_question_allowed(self):
        assert is_illegal_query("感冒有什么症状") is False


class TestRiskNotice:
    def test_treatment_question_needs_notice(self):
        assert needs_risk_notice("这个病怎么治") is True

    def test_plain_chat_needs_no_notice(self):
        assert needs_risk_notice("谢谢", "不客气") is False

    def test_notice_text_is_stable(self):
        assert build_risk_notice() == build_risk_notice()
        assert build_risk_notice()


class TestDefaultIntent:
    def test_symptom_expression_detected(self):
        assert has_symptom_expression("头疼怎么办") is True

    def test_default_for_disease_entity(self):
        assert default_qa_type("感冒", "疾病") is QAType.DISEASE_DESC

    def test_default_for_symptom_text(self):
        assert default_qa_type("头疼", None) is QAType.SYMPTOM_DISEASE

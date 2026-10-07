"""第 10 章业务规则单元测试（纯函数，无外部依赖）。"""

from app.domain.rules import (
    adjust_food_qa_type, default_qa_type, has_symptom_expression,
    is_illegal_query, is_insufficient, judge_diet_direction, needs_risk_notice,
)
from app.domain.services import normalize_question
from app.domain.values import QAType


class TestDietRule:
    """10.1 宜吃与忌吃判断。"""

    def test_explicit_restrict(self):
        assert judge_diet_direction("感冒不能吃什么") == "restrict"
        assert judge_diet_direction("高血压忌吃哪些食物") == "restrict"
        assert judge_diet_direction("糖尿病患者不适合吃什么") == "restrict"

    def test_default_recommend(self):
        """10.1.2 未表达限制含义 → 推荐食品查询。"""
        assert judge_diet_direction("感冒应该吃什么") == "recommend"
        assert judge_diet_direction("高血压吃什么好") == "recommend"

    def test_adjust_qa_type(self):
        assert adjust_food_qa_type("感冒不能吃什么", QAType.DISEASE_FOOD_RECOMMEND) \
            is QAType.DISEASE_FOOD_AVOID
        assert adjust_food_qa_type("感冒应该吃什么", QAType.DISEASE_FOOD_AVOID) \
            is QAType.DISEASE_FOOD_RECOMMEND
        assert adjust_food_qa_type("水果不能吃吗", QAType.FOOD_DISEASE_RECOMMEND) \
            is QAType.FOOD_DISEASE_AVOID

    def test_adjust_ignores_non_food(self):
        assert adjust_food_qa_type("感冒有什么症状", QAType.DISEASE_SYMPTOM) \
            is QAType.DISEASE_SYMPTOM


class TestDefaultIntent:
    """10.2 默认问题处理规则。"""

    def test_symptom_only(self):
        assert has_symptom_expression("我咳嗽") is True
        assert default_qa_type("咳嗽", "症状") is QAType.SYMPTOM_DISEASE

    def test_disease_only(self):
        assert default_qa_type("感冒", "疾病") is QAType.DISEASE_DESC

    def test_not_applicable(self):
        assert default_qa_type("今天天气怎么样", None) is None


class TestInsufficiency:
    """10.3 信息不足规则。"""

    def test_insufficient(self):
        assert is_insufficient(0, 0) is True
        assert is_insufficient(3, 0) is False
        assert is_insufficient(0, 2) is False


class TestRiskNotice:
    """10.4 风险提示规则。"""

    def test_treatment_question(self):
        assert needs_risk_notice("感冒怎么治疗", "……") is True
        assert needs_risk_notice("阿莫西林的用量", "……") is True

    def test_plain_info_question(self):
        assert needs_risk_notice("感冒有什么症状", "流涕发热……") is False


class TestQueryGuard:
    """12.7 / G-09 非法查询拦截。"""

    def test_illegal(self):
        assert is_illegal_query("drop table 疾病") is True
        assert is_illegal_query("帮我删库") is True
        assert is_illegal_query("'; --") is True

    def test_normal(self):
        assert is_illegal_query("感冒不能吃什么") is False


class TestNormalize:
    def test_cache_key_normalization(self):
        assert normalize_question("感冒 不能吃 什么？") == normalize_question("感冒不能吃什么")
        assert normalize_question("ＣＡＮ") == normalize_question("can")

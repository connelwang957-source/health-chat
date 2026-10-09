"""第 1 代规则兜底链（零 LLM）：词典 / 类型判定 / 拼 Cypher / 编排。

对应《项目开发指导》的 `fallback/`：大模型不可用或被关掉时，
图谱能力仍要靠"词典 + 规则"撑住——这几条测试就是它的安全网。
"""

import pytest

from xinglin.domain.values import QAType
from xinglin.fallback import (
    MedicalDictionary,
    RobotQwen,
    classify,
    load_words,
    sql_transfer,
)
from tests.conftest import FakeGraph


def _dictionary() -> MedicalDictionary:
    return MedicalDictionary({
        "Disease": ["感冒", "流行性感冒"],
        "Symptom": ["发热", "咳嗽"],
        "Drug": ["阿莫西林"],
        "Food": ["苹果"],
        "Check": ["血常规"],
        "deny": ["不能", "不宜"],
    })


class TestDictionary:
    def test_size_counts_only_entities(self):
        d = _dictionary()
        assert d.available is True
        assert d.size == 7          # 6 类实体词，deny 不计入

    def test_longest_match_wins(self):
        """「流行性感冒」应压过「感冒」，否则会退化成更粗的匹配。"""
        assert _dictionary().find_entity("流行性感冒怎么治")[0] == "流行性感冒"

    def test_role_returned_with_entity(self):
        assert _dictionary().find_entity("阿莫西林怎么用") == ("阿莫西林", "Drug")

    def test_no_match_returns_none(self):
        assert _dictionary().find_entity("完全无关的一句话") is None

    def test_deny_words_detected(self):
        d = _dictionary()
        assert d.is_denied("螃蟹不能吃") is True
        assert d.is_denied("苹果可以吃") is False

    def test_empty_dictionary_is_unavailable(self):
        assert MedicalDictionary({}).available is False

    def test_load_words_on_missing_dir_is_silent(self, tmp_path):
        assert load_words(tmp_path / "not_exists") == {}


class TestClassifier:
    def test_disease_with_symptom_question(self):
        assert classify("感冒有什么症状", "感冒", "Disease") is QAType.DISEASE_SYMPTOM

    def test_drug_question_targets_diseases(self):
        assert classify("阿莫西林主治什么病", "阿莫西林", "Drug") is QAType.DRUG_DISEASE

    def test_result_is_qa_type_or_none(self):
        result = classify("嗯嗯", None, None)
        assert result is None or isinstance(result, QAType)


class TestQuestionParser:
    def test_returns_parameterised_cypher(self):
        cypher, params = sql_transfer(QAType.DISEASE_SYMPTOM, "感冒")
        assert "$entity" in cypher
        assert params == {"entity": "感冒"}

    def test_missing_qa_type_raises(self):
        with pytest.raises(ValueError):
            sql_transfer(None, "感冒")

    def test_missing_entity_raises(self):
        with pytest.raises(ValueError):
            sql_transfer(QAType.DISEASE_SYMPTOM, "")


class TestRobotQwen:
    def test_rule_path_collects_facts(self):
        robot = RobotQwen(_dictionary(),
                          FakeGraph(rows=[{"value": "咳嗽"}, {"value": "发热"}]))
        result = robot.chat_main("感冒有什么症状？")
        assert result.entity == "感冒"
        assert result.qa_type_code == 1
        assert [f.value for f in result.facts] == ["咳嗽", "发热"]
        assert result.decided_by == "rule"

    def test_unknown_question_returns_empty(self):
        robot = RobotQwen(_dictionary(), FakeGraph())
        result = robot.chat_main("今天天气不错")
        assert result.facts == []
        assert result.decided_by in ("rule", "none")

    def test_graph_failure_does_not_raise(self):
        class _Broken(FakeGraph):
            def query(self, cypher, params=None):
                raise RuntimeError("neo4j down")

        robot = RobotQwen(_dictionary(), _Broken())
        result = robot.chat_main("感冒有什么症状？")
        assert result.facts == []          # 12.1：图谱不可用也不能抛给用户

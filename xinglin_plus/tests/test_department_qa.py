"""科室问答（需求 14.7）与「厂商词典污染」的回归测试（纯离线）。

两件事：

1. **科室**——图谱 `belongs_to` 实测覆盖 8807/8808 疾病，接入为固定问答类型 19/20；
2. **厂商**——既有图谱的 Producer 数据不可用（17201 条「厂商+药名」拼接串、
   `drugs_of` 仅 251 条且指向同名节点）。那些脏名字**更长**，在最长优先匹配里会
   压过正确实体，因此 `producer.txt` **不再加载**——下面的用例锁住这个决定。
"""

from xinglin.domain.entities import Fact
from xinglin.domain.rules import match_keyword
from xinglin.domain.rules.answer_template import render_facts
from xinglin.domain.services.intent_service import IntentService
from xinglin.domain.services.kg_query_service import build_cypher
from xinglin.domain.values import QAType
from xinglin.fallback import MedicalDictionary, classify, load_words
from tests.conftest import FakeLLM, FakeRecognizer


class TestDepartmentCypher:
    def test_forward_query_anchors_on_disease(self):
        cypher = build_cypher(QAType.DISEASE_DEPARTMENT)
        assert "`Disease`" in cypher and "`Department`" in cypher
        assert "belongs_to" in cypher
        assert "$entity" in cypher

    def test_reverse_query_anchors_on_department(self):
        cypher = build_cypher(QAType.DEPARTMENT_DISEASE)
        # 反向：实体是关系**目标端**的 Department，疾病在起点
        assert "`Department` {name: $entity}" in cypher
        assert "`Disease`" in cypher
        assert "belongs_to" in cypher

    def test_both_are_read_only(self):
        for t in (QAType.DISEASE_DEPARTMENT, QAType.DEPARTMENT_DISEASE):
            assert build_cypher(t).strip().upper().startswith("MATCH")


class TestDepartmentKeyword:
    def test_disease_to_department_phrasings(self):
        for q in ("感冒应该看什么科？", "感冒挂什么科", "感冒看哪个科室", "感冒的就诊科室"):
            matched = match_keyword(q)
            assert matched is not None and matched[0] is QAType.DISEASE_DEPARTMENT, q

    def test_symptom_keyword_still_works(self):
        """新规则插在最前面，但不能"抢走"既有的症状类问法。"""
        matched = match_keyword("感冒有什么症状")
        assert matched is not None and matched[0] is QAType.DISEASE_SYMPTOM


class TestDepartmentIntent:
    def test_department_entity_anchors_department_question(self):
        """「泌尿内科看哪些疾病」必须走科室—疾病，而不是被泛化的「哪些疾病」抢走。"""
        svc = IntentService(llm=None, recognizer=FakeRecognizer({"泌尿内科": "Department"}))
        intent = svc.classify("泌尿内科看哪些疾病？")
        assert intent.qa_type is QAType.DEPARTMENT_DISEASE
        assert intent.entity == "泌尿内科"
        assert intent.entity_type == "科室"
        assert intent.open_ended is False

    def test_llm_channel_also_accepts_code_19(self):
        llm = FakeLLM(reply='{"entity": "感冒", "entity_type": "疾病", "qa_type_code": 19,'
                            ' "open_ended": false}')
        intent = IntentService(llm=llm).classify("感冒应该看什么科？")
        assert intent.qa_type is QAType.DISEASE_DEPARTMENT


class TestDepartmentFallbackChain:
    def test_rule_classifier_handles_department_role(self):
        assert classify("泌尿内科看哪些疾病", "泌尿内科", "Department") is QAType.DEPARTMENT_DISEASE

    def test_rule_classifier_handles_disease_to_department(self):
        assert classify("感冒看什么科", "感冒", "Disease") is QAType.DISEASE_DEPARTMENT


class TestDepartmentAnswerText:
    @staticmethod
    def _fact(entity: str, relation: str, value: str) -> Fact:
        return Fact(entity=entity, relation=relation, value=value)

    def test_disease_to_department_phrasing(self):
        text = render_facts("感冒",
                            [self._fact("感冒", "belongs_to", "呼吸内科"),
                             self._fact("感冒", "belongs_to", "内科")],
                            QAType.DISEASE_DEPARTMENT)
        assert "就诊科室" in text and "呼吸内科" in text and "内科" in text

    def test_department_to_disease_phrasing(self):
        text = render_facts("泌尿内科",
                            [self._fact("泌尿内科", "belongs_to", "尿道炎")],
                            QAType.DEPARTMENT_DISEASE)
        assert "主要诊治" in text and "尿道炎" in text


class TestProducerDictRegression:
    """厂商词典不再加载——否则脏名字会压过正确实体（实测「太极阿胶」被误判）。"""

    def test_producer_file_is_not_loaded(self, tmp_path):
        (tmp_path / "department.txt").write_text("泌尿内科\n", encoding="utf-8")
        (tmp_path / "food.txt").write_text("阿胶\n", encoding="utf-8")
        (tmp_path / "producer.txt").write_text("999华蟾素口服液\n太极阿胶\n", encoding="utf-8")
        words = load_words(tmp_path)
        assert "Producer" not in words
        assert "Department" in words and "Food" in words

    def test_dirty_producer_name_does_not_shadow_real_entity(self, tmp_path):
        (tmp_path / "food.txt").write_text("阿胶\n", encoding="utf-8")
        (tmp_path / "producer.txt").write_text("太极阿胶\n", encoding="utf-8")
        d = MedicalDictionary(load_words(tmp_path))
        assert d.find_entity("太极阿胶能吃吗") == ("阿胶", "Food")

    def test_department_entity_is_recognized(self, tmp_path):
        (tmp_path / "department.txt").write_text("泌尿内科\n呼吸内科\n", encoding="utf-8")
        d = MedicalDictionary(load_words(tmp_path))
        assert d.find_entity("泌尿内科看哪些疾病") == ("泌尿内科", "Department")

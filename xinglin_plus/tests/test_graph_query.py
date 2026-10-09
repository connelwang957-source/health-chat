"""图谱查询纯逻辑：Cypher 拼装、只读校验、NL2Cypher 输出解析。"""

from xinglin.domain.graph.nl2cypher import parse_generation, to_facts
from xinglin.domain.graph.validators import ensure_limit, validate_rules
from xinglin.domain.services.kg_query_service import build_cypher, rows_to_facts
from xinglin.domain.values import QAType


class TestBuildCypher:
    def test_uses_entity_parameter(self):
        """语句必须参数化（需求 13.2：不做字符串拼接）。"""
        assert "$entity" in build_cypher(QAType.DISEASE_CAUSE)

    def test_is_read_only(self):
        assert build_cypher(QAType.DISEASE_SYMPTOM).strip().upper().startswith("MATCH")

    def test_relation_kind_uses_relation_name(self):
        assert "has_symptom" in build_cypher(QAType.DISEASE_SYMPTOM)

    def test_reverse_kind_uses_reverse_relation(self):
        assert "recommand_drug" in build_cypher(QAType.DRUG_DISEASE)


class TestRowsToFacts:
    def test_skips_empty_values(self):
        facts = rows_to_facts([{"value": None}, {"value": "咳嗽"}], "感冒", "has_symptom")
        assert [f.value for f in facts] == ["咳嗽"]

    def test_carries_entity_and_relation(self):
        fact = rows_to_facts([{"value": "咳嗽"}], "感冒", "has_symptom")[0]
        assert (fact.entity, fact.relation, fact.value) == ("感冒", "has_symptom", "咳嗽")


class TestEnsureLimit:
    def test_appends_limit_when_absent(self):
        assert "LIMIT" in ensure_limit("MATCH (n) RETURN n").upper()

    def test_does_not_duplicate_limit(self):
        out = ensure_limit("MATCH (n) RETURN n LIMIT 5")
        assert out.upper().count("LIMIT") == 1


class TestValidateRules:
    def test_write_statement_is_rejected(self):
        assert validate_rules("MATCH (n) DELETE n") != []

    def test_read_only_statement_passes(self):
        assert validate_rules("MATCH (n:Disease) RETURN n LIMIT 3") == []


class TestParseGeneration:
    def test_parses_entity_and_cypher(self):
        entity, cypher = parse_generation("ENTITY: 感冒\nCYPHER: MATCH (n) RETURN n")
        assert entity == "感冒"
        assert "MATCH" in cypher

    def test_none_like_entity_becomes_null(self):
        entity, _ = parse_generation("ENTITY: 无\nCYPHER: MATCH (n) RETURN n")
        assert entity is None

    def test_plain_cypher_without_labels(self):
        entity, cypher = parse_generation("MATCH (n) RETURN n")
        assert entity is None
        assert "MATCH" in cypher


class TestToFacts:
    def test_maps_rows_to_facts(self):
        facts = to_facts([{"name": "咳嗽"}], "感冒")
        assert facts and facts[0].entity == "感冒"
        assert "咳嗽" in facts[0].value

    def test_ignores_empty_rows(self):
        assert to_facts([], "感冒") == []

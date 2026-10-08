"""QAType 18 类枚举与 KG 查询模板测试（已对齐 medical 库真实 schema）。"""

import pytest

from app.domain.values import QAType
from app.domain.services import build_cypher


def test_18_types_complete():
    assert len(list(QAType)) == 18
    assert {t.code for t in QAType} == set(range(1, 19))
    names = {t.name for t in QAType}
    assert len(names) == 18


def test_by_code():
    assert QAType.by_code(11) is QAType.DISEASE_FOOD_AVOID
    assert QAType.by_code(None) is None
    with pytest.raises(ValueError):
        QAType.by_code(99)


def test_node_labels_english():
    assert QAType.DISEASE_SYMPTOM.source_role.node_label == "Disease"
    assert QAType.DISEASE_SYMPTOM.target_role.node_label == "Symptom"
    assert QAType.DISEASE_FOOD_AVOID.target_role.node_label == "Food"


def test_relation_cypher():
    cy = build_cypher(QAType.DISEASE_FOOD_AVOID)
    assert "MATCH (n:`Disease` {name: $entity})" in cy
    assert "-[:`no_eat`]->" in cy
    assert "RETURN m.name AS value" in cy


def test_reverse_cypher():
    cy = build_cypher(QAType.SYMPTOM_DISEASE)
    assert "MATCH (n:`Disease`)-[:`has_symptom`]->(m:`Symptom` {name: $entity})" in cy


def test_property_cypher():
    cy = build_cypher(QAType.DISEASE_DESC)
    assert "RETURN n.`desc` AS value" in cy


def test_all_templates_parameterized():
    """全部 18 类模板必须参数化（防注入），禁止字符串直拼实体。"""
    for t in QAType:
        cy = build_cypher(t)
        assert "$entity" in cy
        assert "'感冒'" not in cy

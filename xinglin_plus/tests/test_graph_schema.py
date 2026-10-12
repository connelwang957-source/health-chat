"""图谱 schema 与固定问答类型的一致性（纯离线）。

`QAType` 是模板查询的**唯一事实源**，`MEDICAL_GRAPH_SCHEMA` 是 NL2Cypher 提示词与
校验器的共同事实源——两者必须对得上：QAType 里出现的每个标签 / 关系 / 属性，
都要能在 schema 中找到，否则要么查询报错，要么 LLM 被允许写出我们没有的东西。

本文件同时把**需求规格说明书第 9 章的 18 类**逐字固化为断言：
以后任何改动若动了这 18 类的编号或名称，测试立刻失败。
"""

from xinglin.domain.graph.schemas import (
    MEDICAL_GRAPH_SCHEMA,
    allowed_labels,
    allowed_properties,
    allowed_relations,
    format_schema,
)
from xinglin.domain.values import EntityRole, QAType

# 需求规格说明书 V1.2 第 9 章原文（编号 → 问答类型）。**顺序与名称都不许漂移。**
REQUIRED_18 = [
    (1, "疾病—症状"),
    (2, "症状—疾病"),
    (3, "疾病—病因"),
    (4, "疾病—预防"),
    (5, "疾病—治疗周期"),
    (6, "疾病—治疗方式"),
    (7, "疾病—治愈相关"),
    (8, "疾病—易感人群"),
    (9, "疾病—描述"),
    (10, "疾病—并发症"),
    (11, "疾病—忌吃食品"),
    (12, "疾病—宜吃食品"),
    (13, "食品—疾病（限制）"),
    (14, "食品—疾病（推荐）"),
    (15, "疾病—药品"),
    (16, "药品—疾病"),
    (17, "疾病—检查"),
    (18, "检查—疾病"),
]


class TestRequirementChapter9:
    """需求 9 章的 18 类必须**原样**存在（"至少支持"，所以只能加、不能改）。"""

    def test_first_18_match_requirement_verbatim(self):
        actual = [(t.code, t.cn_name) for t in QAType if t.code <= 18]
        assert actual == REQUIRED_18

    def test_codes_are_unique_and_contiguous(self):
        codes = sorted(t.code for t in QAType)
        assert codes == list(range(1, len(codes) + 1))

    def test_by_code_roundtrip(self):
        for t in QAType:
            assert QAType.by_code(t.code) is t

    def test_food_types_are_the_four_diet_relations(self):
        assert {t.code for t in QAType.food_types()} == {11, 12, 13, 14}


class TestDepartmentExtension:
    """需求 14.7「科室数据（科室名称 + 相关疾病）」—— 原 18 类未覆盖，故扩展 19/20。"""

    def test_two_new_types_exist(self):
        assert QAType.by_code(19) is QAType.DISEASE_DEPARTMENT
        assert QAType.by_code(20) is QAType.DEPARTMENT_DISEASE

    def test_they_are_forward_and_reverse_of_belongs_to(self):
        assert QAType.DISEASE_DEPARTMENT.kind == "relation"
        assert QAType.DEPARTMENT_DISEASE.kind == "reverse"
        assert QAType.DISEASE_DEPARTMENT.key == QAType.DEPARTMENT_DISEASE.key == "belongs_to"

    def test_department_role_maps_to_graph_label(self):
        assert EntityRole.DEPARTMENT.node_label == "Department"
        assert EntityRole.from_node_label("Department") is EntityRole.DEPARTMENT


class TestSchemaConsistency:
    def test_every_qa_type_maps_into_schema(self):
        labels, props = allowed_labels(), allowed_properties()
        for t in QAType:
            assert t.source_role.node_label in labels, t
            if t.kind == "property":
                assert t.key in props, t
            else:
                assert t.target_role is not None, t
                assert t.key in allowed_relations(), t
                assert t.target_role.node_label in labels, t

    def test_schema_only_relations_are_nl2cypher_territory(self):
        """模板覆盖不到的关系由 NL2Cypher 兜——这里把"未覆盖清单"显式固化，
        以后新增/删除覆盖范围都会被立刻发现（`drugs_of` 因数据缺陷刻意不做）。"""
        covered = {t.key for t in QAType if t.kind in ("relation", "reverse")}
        assert allowed_relations() - covered == {"command_drug", "recommand_eat", "drugs_of"}

    def test_format_schema_mentions_all_labels(self):
        text = format_schema()
        for label in MEDICAL_GRAPH_SCHEMA["labels"]:
            assert label in text

    def test_format_schema_mentions_department_relation(self):
        assert "belongs_to" in format_schema()

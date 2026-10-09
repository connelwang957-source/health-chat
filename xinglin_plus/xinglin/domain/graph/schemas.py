"""图谱 schema 知识（domain/graph）：NL2Cypher 提示词与校验器的**共同事实源**。

来自 `medical` 库实测导出（**7 类节点、10 类关系**）。
与 `QAType` 元数据同源但**更完整**：`belongs_to`（科室）、`drugs_of`（药品厂商）、
`command_drug` / `recommand_eat` 这些 18 类固定问答没覆盖的关系，NL2Cypher 可以到达。

> 一致性由 `tests/test_graph_schema.py` 固化：
> `QAType` 里用到的每个标签 / 关系 / 属性都必须能在本 schema 中找到。
"""

from typing import TypedDict


class GraphRelation(TypedDict):
    """一条关系：起点标签 -[:类型]-> 终点标签，附业务含义。"""
    start: str
    type: str
    end: str
    meaning: str


MEDICAL_GRAPH_SCHEMA: dict = {
    "database": "medical",
    "labels": {
        "Disease": ["name", "desc", "cause", "prevent", "cure_lasttime",
                    "cure_way", "cure_prob", "easy_get", "cure_department"],
        "Symptom": ["name"],
        "Drug": ["name"],
        "Food": ["name"],
        "Check": ["name"],
        "Department": ["name"],
        "Producer": ["name"],
    },
    "relations": [
        {"start": "Disease", "type": "has_symptom", "end": "Symptom", "meaning": "疾病的症状"},
        {"start": "Disease", "type": "acompany_with", "end": "Disease", "meaning": "并发症"},
        {"start": "Disease", "type": "no_eat", "end": "Food", "meaning": "忌吃食品"},
        {"start": "Disease", "type": "do_eat", "end": "Food", "meaning": "宜吃食品"},
        {"start": "Disease", "type": "recommand_eat", "end": "Food", "meaning": "推荐食品"},
        {"start": "Disease", "type": "recommand_drug", "end": "Drug", "meaning": "推荐药品"},
        {"start": "Disease", "type": "command_drug", "end": "Drug", "meaning": "常用药品"},
        {"start": "Disease", "type": "need_check", "end": "Check", "meaning": "所需检查"},
        {"start": "Disease", "type": "belongs_to", "end": "Department", "meaning": "所属科室"},
        {"start": "Drug", "type": "drugs_of", "end": "Producer", "meaning": "药品生产厂商"},
    ],
}


def allowed_labels(schema: dict | None = None) -> set[str]:
    return set((schema or MEDICAL_GRAPH_SCHEMA)["labels"].keys())


def allowed_relations(schema: dict | None = None) -> set[str]:
    return {r["type"] for r in (schema or MEDICAL_GRAPH_SCHEMA)["relations"]}


def allowed_properties(schema: dict | None = None) -> set[str]:
    props: set[str] = set()
    for fields in (schema or MEDICAL_GRAPH_SCHEMA)["labels"].values():
        props.update(fields)
    return props


def format_schema(schema: dict | None = None) -> str:
    """把 schema 渲染成给 LLM 看的文本（提示词用）。"""
    s = schema or MEDICAL_GRAPH_SCHEMA
    lines = [f"数据库：{s['database']}", "", "节点（标签: 属性）："]
    for label, props in s["labels"].items():
        lines.append(f"- {label}: {', '.join(props)}")
    lines.append("")
    lines.append("关系（起点 -[:关系]-> 终点　含义）：")
    for r in s["relations"]:
        lines.append(f"- ({r['start']})-[:{r['type']}]->({r['end']})　{r['meaning']}")
    return "\n".join(lines)


__all__ = ["GraphRelation", "MEDICAL_GRAPH_SCHEMA", "allowed_labels",
           "allowed_relations", "allowed_properties", "format_schema"]

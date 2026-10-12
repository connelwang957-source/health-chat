"""KGQueryService：固定问答类型的 Cypher 模板查询（domain 领域服务）。

这是图谱通路的**生产主路径**：零 LLM 成本、结果确定。
Cypher 全部参数化（锚点实体绑定 ``$entity``），节点标签与关系名来自 `QAType` 元数据。
"""

from xinglin.domain.entities import Fact
from xinglin.domain.ports import GraphStore
from xinglin.domain.values import QAType


# 模板查询的结果上限。
# 关系密集的实体必须先截断：实测「螃蟹」有 646 个忌吃疾病、「儿科」关联 795 个疾病，
# 不加 LIMIT 会把全量塞进 sources 与 prompt——出现过 **647 条来源**、响应体与 token 双爆。
TEMPLATE_LIMIT = 20


def build_cypher(qa_type: QAType) -> str:
    """按 QAType 元数据生成参数化 Cypher（锚点实体统一绑定 $entity，并强制 LIMIT）。"""
    src = qa_type.source_role.node_label
    if qa_type.kind == "property":
        return (f"MATCH (n:`{src}` {{name: $entity}}) "
                f"RETURN n.`{qa_type.key}` AS value LIMIT {TEMPLATE_LIMIT}")
    if qa_type.kind == "relation":
        tgt = qa_type.target_role.node_label
        return (f"MATCH (n:`{src}` {{name: $entity}})-[:`{qa_type.key}`]->(m:`{tgt}`) "
                f"RETURN m.name AS value LIMIT {TEMPLATE_LIMIT}")
    # reverse：实体在关系的目标端
    other = qa_type.target_role.node_label
    return (f"MATCH (n:`{other}`)-[:`{qa_type.key}`]->(m:`{src}` {{name: $entity}}) "
            f"RETURN n.name AS value LIMIT {TEMPLATE_LIMIT}")


def rows_to_facts(rows: list[dict], entity: str, relation: str) -> list[Fact]:
    """Neo4j 记录 → 领域 `Fact`（统一过滤空值，全项目只有这一处转换口径）。"""
    facts: list[Fact] = []
    for row in rows or []:
        value = row.get("value")
        text = "" if value is None else str(value).strip()
        if text and text.lower() != "null":
            facts.append(Fact(entity=entity, relation=relation, value=text))
    return facts


class KGQueryService:
    """模板化图谱查询（固定问答类型，零 LLM、结果确定）。"""

    def __init__(self, graph: GraphStore):
        self._graph = graph

    def query(self, qa_type: QAType, entity: str) -> list[Fact]:
        if not entity:
            return []
        cypher = build_cypher(qa_type)
        rows = self._graph.query(cypher, {"entity": entity})
        return rows_to_facts(rows, entity, qa_type.key)


__all__ = ["KGQueryService", "build_cypher", "rows_to_facts"]

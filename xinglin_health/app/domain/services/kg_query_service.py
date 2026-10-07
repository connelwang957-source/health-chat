"""KGQueryService：18 类固定问答的 Cypher 模板查询（领域服务）。

Cypher 全部参数化（防注入），节点标签与关系名来自 QAType 元数据【待对齐】。
"""

from app.domain.entities import Fact
from app.domain.values import QAType


class KGUnavailable(Exception):
    """知识图谱服务不可用（12.1）。"""


def build_cypher(qa_type: QAType) -> str:
    """按 QAType 元数据生成参数化 Cypher（锚点实体统一绑定 $entity）。"""
    src = qa_type.source_role.node_label
    if qa_type.kind == "property":
        return (f"MATCH (n:`{src}` {{name: $entity}}) "
                f"RETURN n.`{qa_type.key}` AS value")
    if qa_type.kind == "relation":
        tgt = qa_type.target_role.node_label
        return (f"MATCH (n:`{src}` {{name: $entity}})-[:`{qa_type.key}`]->(m:`{tgt}`) "
                f"RETURN m.name AS value")
    # reverse：实体在关系的目标端
    other = qa_type.target_role.node_label
    return (f"MATCH (n:`{other}`)-[:`{qa_type.key}`]->(m:`{src}` {{name: $entity}}) "
            f"RETURN n.name AS value")


class KGQueryService:
    def __init__(self, repo):
        # repo: infrastructure.neo4j_repo.Neo4jRepo
        self._repo = repo

    def query(self, qa_type: QAType, entity: str) -> list[Fact]:
        if not entity:
            return []
        cypher = build_cypher(qa_type)
        rows = self._repo.run_read(cypher, {"entity": entity})
        return [Fact(entity=entity, relation=qa_type.key,
                     value=str(r.get("value")).strip())
                for r in rows if r.get("value") not in (None, "", "null")]

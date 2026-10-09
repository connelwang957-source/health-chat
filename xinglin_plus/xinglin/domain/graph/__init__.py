"""domain/graph：知识图谱能力（NL2Cypher 链路 + 图谱 schema + 只读校验器 + 离线建图）。

对外只暴露能力，不含任何编排（编排在 `application/`）。
"""

from xinglin.domain.graph.build_graph import MedicalGraph, load, parse_disease, summarize
from xinglin.domain.graph.nl2cypher import (
    NL2Cypher,
    format_results,
    parse_generation,
    to_facts,
)
from xinglin.domain.graph.schemas import MEDICAL_GRAPH_SCHEMA, format_schema
from xinglin.domain.graph.validators import CypherValidator, ensure_limit, validate_rules

__all__ = [
    "MedicalGraph", "load", "parse_disease", "summarize",
    "NL2Cypher", "format_results", "parse_generation", "to_facts",
    "MEDICAL_GRAPH_SCHEMA", "format_schema",
    "CypherValidator", "ensure_limit", "validate_rules",
]

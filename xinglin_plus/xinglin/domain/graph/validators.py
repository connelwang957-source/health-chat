"""Cypher 只读校验器（对应《项目开发指导》§5.3 / §5.4 的 `CypherValidator`）。

LLM 生成的语句在**执行之前**要过两道关：

1. **规则校验**（本文件的 `validate_rules`，纯函数）：
   黑名单（写操作 / 越权过程）+ 白名单（标签、关系必须在 schema 内）
   + 单语句 + 只读起始 + LIMIT 兜底；
2. **EXPLAIN 预检**（`CypherValidator.validate` 的后半段）：
   把语句交给 Neo4j 只做执行计划规划，语法/标签/属性错误会在此暴露，但**不执行原查询**。

两道都过才允许执行；任何一道不过都直接降级，不冒险。
"""

import re

from xinglin.domain.graph.schemas import (
    MEDICAL_GRAPH_SCHEMA,
    allowed_labels,
    allowed_properties,
    allowed_relations,
)
from xinglin.domain.ports import GraphStore

# 写操作 / 越权 / 危险过程（命中即拒）
WRITE_KEYWORDS: tuple[str, ...] = (
    "create", "merge", "set ", "delete", "remove", "drop", "detach",
    "foreach", "load csv", "call apoc", "call dbms", "call db.",
    "grant", "revoke", "create index", "create constraint",
)

# 合法起始关键字（只读查询必须以其中之一开头）
READ_STARTERS: tuple[str, ...] = ("match", "optional match", "with", "unwind", "return")

# 反引号包裹的标签/关系名，如 (:`Disease`)-[:`has_symptom`]->
_KEY_RE = re.compile(r":\s*`?([A-Za-z_]\w*)`?")
_STR_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
_LIMIT_RE = re.compile(r"\blimit\b\s+\d+", re.IGNORECASE)

DEFAULT_LIMIT = 20


def ensure_limit(cypher: str, limit: int = DEFAULT_LIMIT) -> str:
    """没有 LIMIT 就补一个（防大结果集）。"""
    text = (cypher or "").strip().rstrip(";")
    if not text or _LIMIT_RE.search(text):
        return text
    return f"{text} LIMIT {limit}"


def validate_rules(cypher: str, schema: dict | None = None) -> list[str]:
    """纯规则校验，返回错误列表（空列表 = 通过）。"""
    text = (cypher or "").strip()
    if not text:
        return ["语句为空"]
    errors: list[str] = []

    stripped = _STR_RE.sub("''", text)                     # 先去字符串字面量，避免误判
    lowered = stripped.lower()

    # 1) 只读起始
    if not lowered.lstrip().startswith(READ_STARTERS):
        errors.append("语句不是只读查询（必须以 MATCH/OPTIONAL MATCH/WITH/UNWIND/RETURN 开头）")

    # 2) 写操作黑名单
    for kw in WRITE_KEYWORDS:
        if kw in lowered:
            errors.append(f"检测到禁止的写操作或越权关键字：{kw.upper().strip()}")
            break

    # 3) 单语句
    if ";" in stripped.strip().rstrip(";"):
        errors.append("只允许单条语句（检测到分号分隔的多段查询）")

    # 4) 标签 / 关系 / 属性白名单
    labels = allowed_labels(schema)
    relations = allowed_relations(schema)
    props = allowed_properties(schema)
    for token in _KEY_RE.findall(stripped):
        if token in relations:
            continue
        if token in labels:
            continue
        # 属性访问（n.cause）在 _KEY_RE 里不会命中；这里兜住 `:Prop` 的臆造写法
        if token in props:
            continue
        errors.append(f"出现 schema 未定义的标签/关系：{token}")

    return errors


class CypherValidator:
    """规则校验 + EXPLAIN 预检（EXPLAIN 走 `GraphStore` 端口）。"""

    def __init__(self, graph: GraphStore):
        self._graph = graph

    def validate(self, cypher: str, schema: dict | None = None,
                 params: dict | None = None) -> tuple[bool, list[str]]:
        """返回 ``(是否通过, 错误列表)``。"""
        errors = validate_rules(cypher, schema or MEDICAL_GRAPH_SCHEMA)
        if errors:
            return False, errors

        try:                                   # EXPLAIN 只规划、不执行原查询
            self._graph.explain(cypher, params)
        except Exception as e:                 # noqa: BLE001 —— 任何失败都视为校验不过
            return False, [f"EXPLAIN 校验失败：{type(e).__name__}"]
        return True, []


__all__ = ["WRITE_KEYWORDS", "READ_STARTERS", "DEFAULT_LIMIT",
           "ensure_limit", "validate_rules", "CypherValidator"]

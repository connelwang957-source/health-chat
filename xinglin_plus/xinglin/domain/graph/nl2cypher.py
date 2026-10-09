"""NL2Cypher 核心（对应《项目开发指导》§5.3）。

用大模型把自然语言转成 Cypher，并做「生成 → 校验 → 执行 → 格式化」全流程。

这是对第一代「规则拼 Cypher」（`fallback/question_parser_v2.sql_transfer`）的换代：
- 旧：根据 question_type 用 if/elif 硬编码拼 Cypher，脆弱、难扩展；
- 新：把自然语言 + 图谱 schema 交给 LLM 生成 Cypher，再用**规则 + EXPLAIN** 双重校验。

层归属：**领域能力**（只依赖 `ports.LLM` / `ports.GraphStore`）——被
`application/nl2cypher_agent.py`、`application/hybrid_agent.py`、`application/tool_agent.py`
三处复用，因此它表达的是可复用的业务能力，而不是某条产品流程。
"""

import re
from typing import Any, Dict, List, Tuple

from xinglin.domain.entities import Fact
from xinglin.domain.graph.prompts import create_system_prompt, create_user_prompt
from xinglin.domain.graph.schemas import MEDICAL_GRAPH_SCHEMA, format_schema
from xinglin.domain.graph.validators import CypherValidator, ensure_limit
from xinglin.domain.ports import GraphStore, LLM

_ENTITY_RE = re.compile(r"ENTITY\s*[:：]\s*(.+)", re.IGNORECASE)
_CYPHER_RE = re.compile(r"CYPHER\s*[:：]\s*(.*)", re.IGNORECASE | re.DOTALL)
_ENTITY_NONE = {"无", "none", "null", "-", "n/a", "未知", ""}


def _strip_code_fence(text: str) -> str:
    """清理 LLM 可能输出的 markdown 代码块包裹。"""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("cypher"):
            t = t[6:]
        t = t.strip()
    return t


def format_results(results: List[Dict[str, Any]], limit: int = 10) -> str:
    """把 Neo4j 原始记录格式化成一段可读文本（通用，不依赖具体别名）。"""
    if not results:
        return ""

    values: List[str] = []
    for record in results:
        for v in record.values():
            if isinstance(v, str) and v.strip():
                values.append(v.strip())
            elif isinstance(v, (list, tuple)):
                values.extend(x.strip() for x in v if isinstance(x, str) and x.strip())
            elif v is not None:
                values.append(str(v))

    seen = set()
    uniq: List[str] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return "；".join(uniq[:limit])


def to_facts(results: List[Dict[str, Any]], entity: str | None,
             relation: str = "nl2cypher") -> List[Fact]:
    """查询结果 → 领域 `Fact` 列表（供上游统一按"证据"处理）。"""
    facts: List[Fact] = []
    for record in results or []:
        values: List[str] = []
        for v in record.values():
            if v is None:
                continue
            if isinstance(v, (list, tuple)):
                values.extend(str(x).strip() for x in v if str(x).strip())
            elif str(v).strip():
                values.append(str(v).strip())
        if values:
            facts.append(Fact(entity=entity or "查询结果", relation=relation,
                              value="；".join(values)))
    return facts


def parse_generation(raw: str) -> Tuple[str | None, str]:
    """解析 LLM 输出的 ``ENTITY: ... / CYPHER: ...``；兼容只给语句的情况。"""
    text = (raw or "").strip()
    entity: str | None = None
    if (m := _ENTITY_RE.search(text)) is not None:
        candidate = m.group(1).strip().strip("`\"'“”").strip()
        if candidate.lower() not in _ENTITY_NONE:
            entity = candidate
    cypher = m.group(1) if (m := _CYPHER_RE.search(text)) is not None else text
    return entity, ensure_limit(_strip_code_fence(cypher))


class NL2Cypher:
    """「自然语言 → Cypher → 校验 → 执行 → 格式化」的领域能力。"""

    def __init__(self, llm: LLM, graph: GraphStore,
                 system_prompt_builder=create_system_prompt,
                 user_prompt_builder=create_user_prompt,
                 schema: dict | None = None):
        self.llm = llm
        self.graph = graph
        self.schema = schema or MEDICAL_GRAPH_SCHEMA
        self.schema_text = format_schema(self.schema)
        self.system_prompt_builder = system_prompt_builder
        self.user_prompt_builder = user_prompt_builder
        # 校验器：规则校验 + EXPLAIN 校验（EXPLAIN 走图存储端口）
        self.validator = CypherValidator(self.graph)

    @property
    def available(self) -> bool:
        """LLM 配置齐全即可用（工具缺失由上层降级）。"""
        return self.llm is not None and getattr(self.llm, "available", False)

    # -- ① 生成 -------------------------------------------------------------
    def generate_cypher(self, natural_language: str) -> str:
        """LLM 生成 Cypher 查询。"""
        raw = self.llm.complete(
            self.system_prompt_builder(self.schema_text),
            self.user_prompt_builder(natural_language),
            temperature=0.1, max_tokens=2048,
        )
        return _strip_code_fence(raw)

    def generate(self, natural_language: str) -> Tuple[str | None, str]:
        """生成 ``(实体名, Cypher)``；实体由 LLM 在 ``ENTITY:`` 字段回填。"""
        return parse_generation(self.generate_cypher(natural_language))

    # -- ② 校验（规则 + EXPLAIN） -------------------------------------------
    def validate(self, cypher_query: str,
                 params: dict | None = None) -> Tuple[bool, List[str]]:
        return self.validator.validate(cypher_query, self.schema, params)

    # -- ③ 执行（参数化） ----------------------------------------------------
    def execute(self, cypher_query: str, params: dict | None = None) -> List[Dict[str, Any]]:
        return self.graph.query(cypher_query, params)

    # -- ④ 全流程 -----------------------------------------------------------
    def answer(self, natural_language: str) -> Dict[str, Any]:
        """完整 NL2Cypher 流程：生成 → 校验 → 执行 → 格式化。"""
        result: Dict[str, Any] = {
            "question": natural_language, "entity": None, "cypher": "",
            "validated": False, "errors": [], "results": [], "facts": [], "answer": "",
        }
        if not self.available:
            result["errors"] = ["LLM 不可用，无法生成 Cypher"]
            return result

        try:
            entity, cypher = self.generate(natural_language)
        except Exception as e:                      # noqa: BLE001 —— 交上层降级
            result["errors"] = [f"Cypher 生成失败：{type(e).__name__}"]
            return result

        result["entity"], result["cypher"] = entity, cypher
        params = {"entity": entity} if "$entity" in cypher else None
        if "$entity" in cypher and not entity:
            result["errors"] = ["语句使用 $entity 但未能识别出实体名"]
            return result

        is_valid, errors = self.validate(cypher, params)
        result["validated"], result["errors"] = is_valid, errors
        if not is_valid:
            return result

        try:
            results = self.execute(cypher, params)
        except Exception as e:                      # noqa: BLE001 —— 执行失败同样降级
            result["validated"] = False
            result["errors"] = [f"查询执行失败：{type(e).__name__}"]
            return result

        result["results"] = results
        result["facts"] = to_facts(results, entity)
        result["answer"] = format_results(results)
        return result

    def close(self) -> None:
        close = getattr(self.graph, "close", None)
        if callable(close):
            close()


__all__ = ["NL2Cypher", "_strip_code_fence", "format_results", "to_facts", "parse_generation"]

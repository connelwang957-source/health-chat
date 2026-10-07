"""domain 实体层：跨层流转的领域对象（pydantic v2）。"""

from typing import Any

from pydantic import BaseModel, Field

from app.domain.values import Mode, QAType, Reliability, SourceType


class Question(BaseModel):
    value: str
    normalized: str


class Intent(BaseModel):
    """FR-002 问题理解的结果。"""
    entity: str | None = None
    entity_type: str | None = None          # EntityRole.value
    qa_type: QAType | None = None
    open_ended: bool = False
    confidence: float = 0.0
    decided_by: str = "rule"                # llm | rule
    reason: str = ""


class Fact(BaseModel):
    """KG 结构化事实（来源类型=结构化知识）。"""
    entity: str
    relation: str                           # 关系名或属性名
    value: str


class Source(BaseModel):
    """回答来源（FR-022：type 必填，FR-023：可靠性按类型区分）。"""
    type: SourceType
    label: str = ""                         # 来源展示名，如"知识图谱"
    relation: str | None = None             # KG: 关系名
    entity: str | None = None               # KG: 实体名
    title: str | None = None                # 文献: 标题
    journal: str | None = None
    year: int | None = None
    doi: str | None = None
    url: str | None = None
    loc: str | None = None                  # 定位信息，如"第3页"


class Answer(BaseModel):
    """一次问答的最终产出。"""
    status: str = "ok"                      # ok | insufficient_info | service_unavailable | rejected
    mode: Mode = Mode.DIRECT
    answer: str = ""
    sources: list[Source] = Field(default_factory=list)
    reliability: Reliability = Reliability.LOW
    risk_notice: str | None = None          # 10.4 健康风险提示
    meta: dict[str, Any] = Field(default_factory=dict)

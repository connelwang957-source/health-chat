"""领域实体：跨层流转的数据结构（pydantic v2，纯数据 + 极小行为）。

这是**读模型**（纯查询系统，无状态变化、无业务不变量、无写副作用链），
所以没有聚合根/仓储——见《DDD架构分析.md》第 3 节的论证。
"""

from typing import Any

from pydantic import BaseModel, Field

from xinglin.domain.values import Mode, QAType, Reliability, SourceType


class Question(BaseModel):
    """用户问题。"""
    value: str
    normalized: str = ""        # 规范化结果（缓存 Key 用）


class Intent(BaseModel):
    """FR-002 问题理解的结果。"""
    entity: str | None = None
    entity_type: str | None = None      # EntityRole.value（中文业务名）
    qa_type: QAType | None = None       # 命中 18 类之一；None 表示开放式
    open_ended: bool = False
    confidence: float = 0.0
    decided_by: str = "rule"            # llm | rule
    reason: str = ""


class Fact(BaseModel):
    """KG 结构化事实（来源类型 = 结构化知识）。"""
    entity: str
    relation: str                       # 关系名或属性名
    value: str


class Source(BaseModel):
    """回答来源（FR-022：type 必填；FR-023：可靠性按类型区分）。"""
    type: SourceType
    label: str = ""
    relation: str | None = None         # KG：关系名
    entity: str | None = None           # KG：实体名
    title: str | None = None            # 文献：标题
    journal: str | None = None
    year: int | None = None
    doi: str | None = None
    url: str | None = None
    loc: str | None = None              # 定位信息，如"第3页"


class Answer(BaseModel):
    """一次问答的最终产出。"""
    status: str = "ok"                  # ok | insufficient_info | service_unavailable | rejected
    mode: Mode = Mode.DIRECT
    answer: str = ""
    sources: list[Source] = Field(default_factory=list)
    reliability: Reliability = Reliability.LOW
    risk_notice: str | None = None      # 第 10.4 条健康风险提示
    meta: dict[str, Any] = Field(default_factory=dict)


__all__ = ["Question", "Intent", "Fact", "Source", "Answer"]

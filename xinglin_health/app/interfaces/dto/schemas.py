"""接口层 DTO：请求/响应模型（与领域对象解耦）。"""

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500,
                          description="中文健康问题（自然语言，无需固定格式）")


class SourceOut(BaseModel):
    type: str                 # kg | lit（FR-022 来源类型必标）
    label: str = ""           # 结构化知识 / 医学文献
    relation: str | None = None
    entity: str | None = None
    title: str | None = None
    journal: str | None = None
    year: int | None = None
    doi: str | None = None
    url: str | None = None
    loc: str | None = None


class AskResponse(BaseModel):
    status: str               # ok | insufficient_info | service_unavailable | rejected
    mode: str                 # direct | kg | rag | hybrid（系统自选，FR-024）
    answer: str
    sources: list[SourceOut] = Field(default_factory=list)
    reliability: str          # high | partial | low（FR-023）
    risk_notice: str | None = None
    cached: bool = False
    meta: dict = Field(default_factory=dict)


class DependencyHealth(BaseModel):
    neo4j: str
    milvus: str
    redis: str
    llm: str


class HealthResponse(BaseModel):
    status: str
    dependencies: DependencyHealth

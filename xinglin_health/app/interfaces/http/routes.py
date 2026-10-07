"""HTTP 路由（interfaces 层，瘦）：只做校验、调用用例、组装响应。"""

import logging

from fastapi import APIRouter

from app.domain.values import SourceType
from app.interfaces.dto.schemas import (
    AskRequest, AskResponse, DependencyHealth, HealthResponse, SourceOut,
)
from app.wiring import get_ask_usecase

logger = logging.getLogger(__name__)
router = APIRouter()


def _to_source_out(s: dict) -> SourceOut:
    s = dict(s)
    s["type"] = SourceType(s["type"]).value if s.get("type") in ("kg", "lit") else s.get("type", "kg")
    if not s.get("label") and s.get("type"):
        try:
            s["label"] = SourceType(s["type"]).label
        except ValueError:
            s["label"] = s["type"]
    return SourceOut(**s)


@router.post("/ask", response_model=AskResponse, response_model_exclude_none=False)
def ask(req: AskRequest) -> AskResponse:
    payload = get_ask_usecase().execute(req.question.strip())
    return AskResponse(
        status=payload.get("status", "ok"),
        mode=payload.get("mode", "direct"),
        answer=payload.get("answer", ""),
        sources=[_to_source_out(s) for s in payload.get("sources", [])],
        reliability=payload.get("reliability", "low"),
        risk_notice=payload.get("risk_notice"),
        cached=payload.get("cached", False),
        meta=payload.get("meta", {}),
    )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """FR-030/14.11：反映问答服务是否正常（各依赖真实探活）。"""
    deps = {}
    try:
        from app.infrastructure.neo4j_repo import get_neo4j_repo
        deps["neo4j"] = "ok" if get_neo4j_repo().health() else "error"
    except Exception:  # noqa: BLE001
        deps["neo4j"] = "error"

    try:
        from app.infrastructure.milvus_retriever import milvus_health
        deps["milvus"] = "ok" if milvus_health() else "error"
    except Exception:  # noqa: BLE001
        deps["milvus"] = "error"

    try:
        from app.infrastructure.redis_cache import get_redis_cache
        deps["redis"] = "ok" if get_redis_cache().available else "error"
    except Exception:  # noqa: BLE001
        deps["redis"] = "error"

    try:
        from app.infrastructure.llm.gateway import get_llm_gateway
        gw = get_llm_gateway()
        deps["llm"] = "configured" if gw.available else "unconfigured"
    except Exception:  # noqa: BLE001
        deps["llm"] = "unconfigured"

    ok = all(v in ("ok", "configured") for v in deps.values())
    return HealthResponse(status="ok" if ok else "degraded",
                          dependencies=DependencyHealth(**deps))

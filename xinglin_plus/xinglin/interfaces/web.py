"""接口层：Web 服务（FastAPI）。

对应文档 §2.2 / §8.3：只暴露两个端点，**请求里不带模式参数**
（FR-024/6.2：咨询人员不可指定检索模式）；模式只在**启动时**由运维指定。

    POST /v1/chat   问答（走默认 Agent）
    GET  /health    依赖探活（四依赖真实探测）

启动（文档 §8.3）::

    python -m xinglin.interfaces.web --mode agent --host 0.0.0.0 --port 8000
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from xinglin.config import BASE_DIR

logger = logging.getLogger(__name__)

# 单次提问长度约束（FR-001）
MIN_QUESTION_LEN = 1
MAX_QUESTION_LEN = 500

# 单文件前端（含深浅色主题切换），由本服务托管在 `/`
FRONTEND_INDEX = BASE_DIR / "frontend" / "index.html"


class AskRequest(BaseModel):
    question: str = Field(..., min_length=MIN_QUESTION_LEN, max_length=MAX_QUESTION_LEN)


class SourceOut(BaseModel):
    type: str
    label: str = ""
    relation: str | None = None
    entity: str | None = None
    title: str | None = None
    journal: str | None = None
    year: int | None = None
    doi: str | None = None
    url: str | None = None
    loc: str | None = None


class AskResponse(BaseModel):
    status: str                 # ok | insufficient_info | service_unavailable | rejected
    mode: str                   # direct | kg | rag | hybrid（系统自选，FR-024）
    reliability: str            # high | partial | low（FR-023）
    answer: str
    sources: list[SourceOut] = Field(default_factory=list)
    risk_notice: str | None = None
    meta: dict = Field(default_factory=dict)


class DependencyHealth(BaseModel):
    neo4j: str
    milvus: str
    redis: str
    llm: str


class HealthResponse(BaseModel):
    status: str                 # ok | degraded
    dependencies: DependencyHealth


def _get_bot():
    """默认问答 Agent（进程内单例）。"""
    from xinglin.application.runtime import get_default_agent
    return get_default_agent()


def _milvus_health() -> bool:
    """Milvus 真实探活：连不上即视为不健康（不影响问答，只影响状态胶囊）。"""
    try:
        from pymilvus import MilvusClient

        from xinglin.config import MILVUS_CONFIG
        client = MilvusClient(uri=MILVUS_CONFIG["uri"])
        try:
            client.list_collections()
            return True
        finally:
            client.close()
    except Exception as e:      # noqa: BLE001
        logger.debug("Milvus 健康检查失败: %s", e)
        return False


def create_app() -> FastAPI:
    app = FastAPI(title="杏林大健康 AI 问答系统", version="2.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"])

    @app.get("/", include_in_schema=False)
    def index():
        """问答界面（单文件前端，自带深/浅色主题切换）。"""
        if not FRONTEND_INDEX.exists():
            return HTMLResponse(
                "<h1>前端未找到</h1><p>请确认 frontend/index.html 存在。</p>",
                status_code=404)
        return FileResponse(FRONTEND_INDEX)

    @app.post("/v1/chat", response_model=AskResponse)
    def ask(req: AskRequest) -> AskResponse:
        """问答：内部由 Agent 自动判断检索模式（FR-024）。"""
        try:
            answer = _get_bot().chat_main(req.question)
        except Exception:       # noqa: BLE001 —— 内部错误不外泄（ACC-031）
            logger.exception("ask pipeline failed")
            return AskResponse(status="service_unavailable", mode="direct",
                               reliability="low",
                               answer="服务暂时不可用，请稍后再试。")
        payload = answer.model_dump()
        return AskResponse(
            status=payload["status"],
            mode=getattr(payload["mode"], "value", payload["mode"]),
            reliability=getattr(payload["reliability"], "value", payload["reliability"]),
            answer=payload["answer"],
            sources=[SourceOut(**s) for s in payload["sources"]],
            risk_notice=payload["risk_notice"],
            meta=payload["meta"],
        )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        """依赖探活：反映问答服务当前是否可用。"""
        from xinglin.application.runtime import get_graph, get_llm, get_redis

        deps = {
            "neo4j": "ok" if get_graph().health() else "error",
            "milvus": "ok" if _milvus_health() else "error",
            "redis": "ok" if get_redis().available else "error",
            "llm": "configured" if get_llm().available else "unconfigured",
        }
        ok = all(v in ("ok", "configured") for v in deps.values())
        return HealthResponse(status="ok" if ok else "degraded",
                              dependencies=DependencyHealth(**deps))

    return app


app = create_app()

__all__ = ["app", "create_app", "AskRequest", "AskResponse", "HealthResponse"]


if __name__ == "__main__":
    import argparse
    import os

    import uvicorn

    parser = argparse.ArgumentParser(description="杏林大健康 AI 问答系统 Web 服务")
    parser.add_argument("--mode", choices=["hybrid", "rag", "nl2cypher", "agent"],
                        default="hybrid", help="问答模式（启动时固定，请求不可改）")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    # 用环境变量把模式传给组合根（`runtime.get_default_agent`）——
    # 请求侧仍然不可指定，符合 FR-024/6.2。
    os.environ["XINGLIN_WEB_MODE"] = args.mode
    uvicorn.run("xinglin.interfaces.web:app", host=args.host, port=args.port)

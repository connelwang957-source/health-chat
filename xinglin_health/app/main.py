"""应用入口：uvicorn app.main:app"""

from fastapi import FastAPI

from app.interfaces.errors import register_exception_handlers
from app.interfaces.http.routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="杏林大健康 AI 问答系统",
        version="1.0.0",
        description="大健康信息咨询工具（KG + RAG + Agent，FR-024 多路检索自动路由）",
    )
    app.include_router(router)
    register_exception_handlers(app)
    return app


app = create_app()

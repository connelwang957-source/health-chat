"""应用入口。

启动方式（在项目根目录 xinglin_health 下执行）：
  .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000   # 推荐生产/常规
  .venv/Scripts/python.exe -m app.main                           # 等价，可直接调试运行
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.interfaces.errors import register_exception_handlers
from app.interfaces.http.routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="杏林大健康 AI 问答系统",
        version="1.0.0",
        description="大健康信息咨询工具（KG + RAG + Agent，FR-024 多路检索自动路由）",
    )
    # 内部工具：前端为本地静态页（file:// 或任意内网地址），放开跨域
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], allow_credentials=False,
        allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(router)
    register_exception_handlers(app)
    return app


app = create_app()


if __name__ == "__main__":
    # 允许直接运行本文件启动服务（注意：必须以 -m 模块方式或工作目录=项目根，
    # 否则包导入会失败；开发调试可用 reload=True）。端口可用 APP_PORT 环境变量覆盖。
    import os

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1",
                port=int(os.environ.get("APP_PORT", "8000")))


"""统一异常处理：内部错误绝不外泄（ACC-031），收敛为明确错误状态（14.12）。"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

GENERIC_UNAVAILABLE = "服务暂时不可用，请稍后再试。"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def on_validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=400, content={
            "status": "bad_request",
            "answer": "问题格式不正确：请输入 1-500 字的中文健康问题。",
            "detail": "invalid question"})

    @app.exception_handler(Exception)
    async def on_unexpected(request: Request, exc: Exception):
        logger.exception("unhandled error on %s", request.url.path)
        return JSONResponse(status_code=500, content={
            "status": "service_unavailable",
            "answer": GENERIC_UNAVAILABLE})

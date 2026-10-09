"""interfaces：接口层（瘦）。

    cli.py   命令行入口（四种模式 + 可选 Redis 缓存）
    web.py   Web 服务（FastAPI：POST /ask · GET /health）

本层只做参数校验、DTO 转换与展示，不含业务规则，也不直接碰基础设施
（依赖由 `xinglin.application.runtime` 组合根提供）。
"""

__all__ = ["cli", "web"]

"""杏林大健康 AI 问答系统（第二代）统一入口。

在项目根目录运行::

    python main.py --mode hybrid       # 双路融合（默认）
    python main.py --mode rag          # 仅 RAG
    python main.py --mode nl2cypher    # 仅图谱
    python main.py --mode agent        # 工具调用 ReAct Agent
    python main.py --cache             # 叠加 Redis 缓存
    python main.py -q "感冒有什么症状？"  # 单次提问（脚本化验证）

Web 服务另起::

    .venv\\Scripts\\python.exe -m uvicorn xinglin.interfaces.web:app --port 8100
"""

import os

# 国内可用的 HuggingFace 镜像（模型已在本机缓存，这里只是兜底）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from xinglin.interfaces.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

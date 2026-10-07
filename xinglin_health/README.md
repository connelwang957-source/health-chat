# 杏林大健康 AI 问答系统（xinglin_health）

大健康信息咨询工具：知识图谱（Neo4j）+ 文献 RAG（Milvus/BM25）+ Agent 路由（LangGraph），DDD 四层架构（interfaces → application → domain → infrastructure，严格单向依赖）。

- 需求依据：《杏林大健康AI问答系统需求规格说明书_V1.2.md》（本目录）
- 设计依据：《杏林大健康AI问答系统技术设计说明书_V1.0.md》（本目录）

> 注：本目录 `.venv` 使用 Python 3.13.5（技术文档基线 3.12 的等效可用环境，全部依赖已验证可装）。

## 快速启动

```bash
# 1. 启动依赖（Neo4j + Milvus + Redis）
cd deploy && docker compose up -d && cd ..

# 2. 配置环境变量
cp .env.example .env        # 填入 LLM_API_KEY、NEO4J_PASSWORD 等

# 3. 安装依赖（已装可跳过）
.venv/Scripts/python.exe -m pip install -r requirements.txt
# 本地向量化（RAG 入库需要，体积大按需装）：
.venv/Scripts/python.exe -m pip install langchain-huggingface sentence-transformers

# 4. 文献入库（切分 knowledge_base.txt → Milvus + BM25 语料）
.venv/Scripts/python.exe scripts/ingest_docs.py

# 5. 启动服务
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

- 问答接口：POST http://localhost:8000/ask {"question": "感冒不能吃什么？"}
- 健康检查：GET http://localhost:8000/health
- 接口文档：http://localhost:8000/docs

## 测试

```bash
.venv/Scripts/python.exe -m pytest tests/ -v        # 领域规则 + 18类模板 + API 冒烟
```

## 目录结构（DDD 四层）

```text
app/
├── interfaces/      接口层（瘦）：FastAPI 路由 / DTO / 统一异常
├── application/     应用层：AskUseCase + LangGraph 主图 + prompts
├── domain/          领域层：实体 / QAType 18类 / 领域服务 / 第10章规则（纯函数）
└── infrastructure/  基础设施层：Neo4j / Milvus / BM25 / Redis / LLM 网关 / BGE-M3
```

依赖方向严格单向：interfaces → application → domain → infrastructure（3.1 节强约束）。

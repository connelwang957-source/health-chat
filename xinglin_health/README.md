# 杏林大健康 AI 问答系统（xinglin_health）

大健康企业内部的健康信息咨询辅助工具：**知识图谱（Neo4j）+ 文献 RAG（稠密向量 + BM25 双路 RRF）+ Agent 路由（LangGraph）**，DDD 四层架构，严格单向依赖。

- 需求依据：[杏林大健康AI问答系统需求规格说明书_V1.2.md](杏林大健康AI问答系统需求规格说明书_V1.2.md)
- 设计依据：[杏林大健康AI问答系统技术设计说明书_V1.0.md](杏林大健康AI问答系统技术设计说明书_V1.0.md)

---

## 一、快速启动

### 1. 前置条件

| 依赖 | 说明 | 是否必需 |
|---|---|---|
| Python 3.12/3.13 + 依赖包 | 项目 `.venv` 已建好，依赖已装 | ✅ |
| Neo4j（medical 库） | 已建好的知识图谱（本机 7687 端口，账号密码见 `.env`） | ✅（KG 通路） |
| DeepSeek API Key | 系统环境变量 `DEEPSEEK_API_KEY`（或写进 `.env` 的 `LLM_API_KEY`） | ✅（生成与意图识别） |
| Milvus + Redis | `deploy/docker-compose.yml` | ⭕ 可选（见下方两种运行形态） |
| 本地向量模型 | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`（已在本地 HF 缓存） | ✅（RAG 稠密路） |

### 2. 启动步骤

```bash
cd D:\project_phase\medical\xinglin_health

# ① 启动 Milvus + Redis（可选：不启动则稠密检索走内存向量库、缓存关闭，功能不缺失）
cd deploy && docker compose up -d && cd ..

# ② 配置环境变量（首次：复制模板填写）
cp .env.example .env       # 填 NEO4J_PASSWORD / LLM_API_KEY（API Key 也可只用系统环境变量 DEEPSEEK_API_KEY）

# ③ 文献入库（切块 knowledge_base.txt → 稠密向量 + BM25 语料，重跑即增量）
.venv/Scripts/python.exe scripts/ingest_docs.py

# ④ 启动服务（两种等价方式）
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
# 或：.venv/Scripts/python.exe -m app.main      （端口用环境变量 APP_PORT 覆盖，默认 8000）
# ⚠ 必须在本目录（项目根）下执行，且用 -m 模块方式——直接右键跑 main.py 会报 No module named 'app'
```

### 3. 交互入口

**前端页面（推荐）**：双击 `启动前端.bat`（自动打开浏览器）；或手动双击 `index.html`。深色玻璃拟态单页应用，带健康状态胶囊、来源折叠区、复制回答。

| 入口 | 地址 | 用途 |
|---|---|---|
| 问答接口 | `POST http://localhost:8000/ask`，body：`{"question": "感冒不能吃什么？"}` | 核心问答 |
| 健康检查 | `GET http://localhost:8000/health` | 四依赖真实探活 |
| 接口文档 | `http://localhost:8000/docs` | 浏览器交互演示（Swagger） |

> 💡 也可以直接双击 `启动后端.bat` 一键起后端（窗口保持打开即服务运行）。前端页面通过 `API_BASE` 常量（index.html 顶部）配置后端地址。

### 4. 运行测试

```bash
.venv/Scripts/python.exe -m pytest tests/ -v
```

---

## 二、核心代码地图

所有业务代码在 `app/` 下，按 DDD 四层组织。**改代码前先看这张表**：

| 文件 | 层 | 职责 | 关联需求 |
|---|---|---|---|
| `app/main.py` | — | FastAPI 应用工厂，组合路由与异常处理 | 14.10 |
| `app/interfaces/http/routes.py` | 接口层 | `/ask` `/health` 路由（瘦，无业务逻辑） | 14.10/14.11 |
| `app/interfaces/dto/schemas.py` | 接口层 | 请求/响应模型（AskRequest/AskResponse） | 14.13 |
| `app/interfaces/errors.py` | 接口层 | 统一异常映射（内部错误不外泄） | 12.3/ACC-031 |
| `app/application/usecases/ask_usecase.py` | 应用层 | **提问用例**：查缓存→跑图→回写缓存，重复请求锁 | FR-028/029 |
| `app/application/graph/build.py` | 应用层 | **LangGraph 主图组装**（节点+条件边） | 第 11 章流程 |
| `app/application/graph/nodes.py` | 应用层 | 8 个图节点：意图/路由/KG/RAG/生成/可靠性/兜底/响应 | FR-001~027 |
| `app/application/graph/state.py` | 应用层 | 图状态定义（GraphState） | — |
| `app/application/prompts/` | 应用层 | 提示词模板（意图识别/回答生成，外置 md 文件） | 10.4 口吻约束 |
| `app/domain/values/qa_type.py` | 领域层 | **QAType 18 类问答枚举**（挂载 Cypher 模板元数据） | 第 9 章 |
| `app/domain/entities/models.py` | 领域层 | 领域对象：Intent/Fact/Source/Answer | 14.6/14.8 |
| `app/domain/services/intent_service.py` | 领域层 | 意图识别：LLM 结构化输出 + 关键词规则兜底 | FR-002/003 |
| `app/domain/services/kg_query_service.py` | 领域层 | 按 QAType 生成参数化 Cypher 并查询 | FR-004~020 |
| `app/domain/services/retrieval_service.py` | 领域层 | 文献混合检索封装 | FR-021/022 |
| `app/domain/services/generation_service.py` | 领域层 | 回答生成（来源标识强制落地）+ 模板兜底 | FR-022 |
| `app/domain/services/reliability_service.py` | 领域层 | 可靠性分级（分来源类型） | FR-023 |
| `app/domain/services/cache_service.py` | 领域层 | 缓存 Key 规范化与读写 | FR-028/029 |
| `app/domain/rules/` | 领域层 | **第 10 章业务规则纯函数**：宜忌判定/默认意图/信息不足/风险提示/非法拦截 | 第 10 章、12.7 |
| `app/infrastructure/neo4j_repo.py` | 基础设施 | Neo4j 只读仓储（参数化 Cypher） | 13.1/13.2 |
| `app/infrastructure/milvus_retriever.py` | 基础设施 | Milvus 稠密检索（langchain-milvus） | 14.8 |
| `app/infrastructure/bm25_store.py` | 基础设施 | BM25 稀疏检索（jieba 分词，内存索引） | FR-022 |
| `app/infrastructure/hybrid_retriever.py` | 基础设施 | **EnsembleRetriever 双路 RRF 融合**（含无 Milvus 的内存稠密回退） | FR-022 |
| `app/infrastructure/embedder.py` | 基础设施 | 本地向量化（MiniLM 384 维，离线加载） | 检索质量 |
| `app/infrastructure/llm/gateway.py` | 基础设施 | LLM 网关（ChatOpenAI，厂商可切换，绕系统代理） | 第 20 章 |
| `app/infrastructure/redis_cache.py` | 基础设施 | Redis JSON 读写 + SETNX 幂等锁 | FR-028/029 |
| `app/infrastructure/config.py` | 基础设施 | 全部配置（.env 读取，密钥仅此层可见） | 13.3 |
| `app/wiring.py` | 组合根 | 依赖注入：把基础设施适配器装进领域服务 | 依赖链唯一豁免点 |
| `scripts/ingest_docs.py` | 脚本 | **文献入库**：切块 + 向量化 + BM25 语料产出 | 14.8 |
| `deploy/docker-compose.yml` | 部署 | Neo4j/Milvus/Redis 一键启动 | 第 10 章 |

---

## 三、代码架构（DDD 四层，严格单向依赖）

```text
interfaces  →  application  →  domain  →  infrastructure
```

- **依赖只能沿此方向**，禁止反向与跨层回环（CI 用 import-linter 固化）；
- **interfaces** 只做校验与格式转换；**application** 做用例编排（LangGraph 在此层）；
- **domain** 承载实体与第 10 章业务规则（纯函数，可脱离网络单测），技术访问经领域服务封装；
- **infrastructure** 是唯一知道具体技术（Neo4j/Milvus/Redis/LLM SDK）的地方——换厂商/换向量库只改这一层；
- `app/wiring.py` 是组合根：唯一把所有实现装配起来的模块。

```text
┌───────────────────────────────────────────────┐
│ interfaces 接口层（瘦）                        │
│  POST /ask   GET /health   DTO · 统一异常      │
└───────────────────┬───────────────────────────┘
                    ▼
┌───────────────────────────────────────────────┐
│ application 应用层（用例编排）                  │
│  AskUseCase（查缓存→跑图→回写）                 │
│  LangGraph 主图：意图→路由→检索→生成→可靠性→兜底 │
│  prompts/（咨询口吻、来源标识、风险边界）        │
└───────────────────┬───────────────────────────┘
                    ▼
┌───────────────────────────────────────────────┐
│ domain 领域层（纯业务，规则可独立单测）          │
│  QAType 18类 · Intent/Fact/Source/Answer       │
│  服务：Intent/KGQuery/Retrieval/Generation/    │
│        Reliability/Cache                       │
│  规则(第10章)：宜忌·默认意图·信息不足·风险·拦截   │
└───────────────────┬───────────────────────────┘
                    ▼
┌───────────────────────────────────────────────┐
│ infrastructure 基础设施层（唯一碰具体技术）      │
│  Neo4jRepo · Milvus · BM25 · Ensemble(RRF)     │
│  RedisCache · LLMGateway(DeepSeek/Qwen)        │
│  Embedder(MiniLM 384维) · Settings(.env)       │
└───────────────────────────────────────────────┘
```

---

## 四、业务流程（一次问答的完整旅程）

以「感冒不能吃什么？」为例：

```text
用户提问
  ▼
【接口层】POST /ask → DTO 校验（1-500 字）→ 移交用例
  ▼
【应用层】① 查缓存 ──命中──▶ 直接返回（FR-028）
  │ 未命中 → 取 SETNX 锁（FR-029 防重复计算）
  ▼
【应用层】LangGraph 主图启动
  ▼
意图识别节点：LLM 结构化输出（失败自动降级关键词规则）
  → Intent{entity=感冒, qa_type=疾病—忌吃食品(11)}
  ▼
路由节点（FR-024 四选一，系统自动决定，用户不可指定）：
  ① 非法查询 ──▶ 拒绝（12.7）
  ② 寒暄/常识 ──▶ direct 直接回答
  ③ 命中 18 类 ──▶ kg  走知识图谱
  ④ 开放式问题 ──▶ rag  走文献 / hybrid 先图谱后文献（FR-025）
  ▼
【领域服务+基础设施】检索
  KG 路：参数化 Cypher → Disease-[:no_eat]->Food → 结构化事实
  RAG 路：稠密向量 + BM25 → RRF 融合 top-8 文献片段
  ▼
生成节点：LLM 按模板组织语言，强制携带来源标识（FR-022）
  ▼
可靠性节点（FR-023）：high / partial / low（分来源类型）
  │ 依据不足 → 备用处理：换检索路重试（≤2 次）→ 仍不足 → 信息不足话术（10.3）
  ▼
【应用层】回写缓存（TTL 24h）→ 返回响应
```

响应示例（`mode` 与 `sources[].type` 即路由与来源标识的直接证据）：

```json
{
  "status": "ok", "mode": "kg", "reliability": "high",
  "answer": "感冒期间建议避免……",
  "sources": [{ "type": "kg", "label": "结构化知识", "relation": "no_eat", "entity": "感冒" }],
  "risk_notice": "以上内容为健康信息参考，不构成医学诊断或治疗建议……",
  "cached": false
}
```

---

## 五、数据流向

### 1. 知识图谱（结构化知识路）

```text
medical 库（8808 Disease / 5998 Symptom / 4870 Food / 3828 Drug / 3353 Check）
   │  只读账户 + 参数化 Cypher（QAType 元数据驱动模板）
   ▼
Neo4jRepo.run_read() ──▶ Fact{entity, relation, value} ──▶ 生成上下文（高优先级证据）
```

关系模式：`has_symptom / acompany_with / no_eat / do_eat / recommand_drug / need_check / belongs_to`；属性：`desc / cause / prevent / cure_lasttime / cure_way / cure_prob / easy_get`。

### 2. 文献语料（医学文献路）

```text
knowledge_base.txt（19 篇，UTF-8，带文档/页分隔符）
   │  scripts/ingest_docs.py
   │    ├─ langchain-text-splitters 切块（500-800 字，重叠 120，保留标题/页码元数据）→ 762 片段
   │    ├─ data/bm25_docs.json（BM25 语料）
   │    └─ Milvus medical_lit 集合（MiniLM 384 维稠密向量；未起 Milvus 时自动用内存向量库）
   ▼
EnsembleRetriever：稠密向量路 + BM25 路 → RRF 融合 top-8 ──▶ 生成上下文（带 [1][2] 引用）
```

### 3. 缓存

```text
问题规范化（全角→半角、去标点、小写）→ sha256
   ├─ kb:ans:{hash}   答案 JSON，TTL 24h（FR-028 秒回）
   └─ kb:lock:{hash}  SETNX 60s（FR-029 同问题只算一次）
```

---

## 六、目录总览

```text
xinglin_health/
├── app/                     # 业务代码（四层，见第二节代码地图）
├── scripts/ingest_docs.py   # 文献入库脚本
├── deploy/docker-compose.yml# Neo4j/Milvus/Redis 编排
├── tests/                   # 领域规则 + 18类模板 + API 冒烟（24 用例）
├── evals/                   # 评测集（I5 建设：意图/检索/幻觉三层）
├── data/bm25_docs.json      # 切片语料（入库脚本产出）
├── .env / .env.example      # 环境配置（.env 不入库）
├── requirements.txt         # 依赖（版本协同已实测锁定）
└── *.md                     # 需求文档 V1.2 + 技术设计说明书 V1.0
```

## 七、常见问题

- **依赖没全启动能用吗？** 能。任何依赖故障都走降级链：KG 挂→纯文献；文献挂→KG/直接回答；缓存挂→正常问答只是变慢；全挂→明确告知"信息不足"而非报错（12.1~12.6）。`/health` 会如实上报各依赖状态。
- **MiniLM 报 transformers 兼容错误？** 已锁定 `transformers>=4.50,<5`（v5 加载不了旧版 ST 模型仓库），且 `HF_HUB_OFFLINE=true` 走本地缓存。
- **LLM 调用走了系统代理失败？** 网关默认 `LLM_TRUST_ENV=false` 直连国内 API，需要代理时改 `.env`。
- **换 LLM 厂商 / 换向量库？** 只改 `.env`（厂商）或 `infrastructure/` 层（组件），domain/application 零改动。
- **新增一类固定问答？** `QAType` 枚举加一项（含 Cypher 模板元数据）即可，路由与接口自动生效（NFR-MNT-01）。

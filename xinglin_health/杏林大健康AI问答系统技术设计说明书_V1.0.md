# 杏林大健康 AI 问答系统技术设计说明书

> **版本** V1.0 ｜ **文档状态** 评审稿 ｜ **编制日期** 2026-10-07 ｜ **依据**《杏林大健康 AI 问答系统需求规格说明书》V1.2

---

## 1.2 修订记录

| 版本 | 日期 | 修订说明 | 编制/修订人 |
|---|---|---|---|
| V1.0 | 2026-10-07 | 初稿：技术栈、DDD 四层架构、Agent 编排、数据设计、接口、非功能量化指标、部署与评测方案 | 【编制人】 |

---

## 1. 引言

### 1.1 编写目的

本文档依据《需求规格说明书》V1.2（下称《需求文档》），定义系统的技术架构、模块设计、数据设计、接口契约、非功能量化指标、部署与评测方案，作为编码、测试与验收的直接依据。

### 1.2 与需求文档的关系

- 需求文档中的每一个 FR/NFR/G 编号，本文档在相应设计处引用（可追溯）；
- 需求文档 20 章明确"采用何种技术"由本文档规定——本文档即该规定的落点；
- 需求文档 14 章只约束业务层非功能目标，**量化取值由本文档第 8 章给出**。

### 1.3 术语

沿用《需求文档》2.2 节。另增：

| 术语 | 含义 |
|---|---|
| 通路 | 一次检索所走的链路：KG 通路 / RAG（文献）通路 / 混合通路 |
| 路由 | FR-024 定义的检索模式自动选择行为 |
| 事实注入 | KG 查询返回的结构化三元组，作为高优先级证据进入生成上下文 |

---

## 2. 技术栈与版本

| 层次 | 选型 | 版本基线 | 选型理由 | 对应需求 |
|---|---|---|---|---|
| 运行语言 | Python | 3.12（独立 conda 环境） | AI 生态兼容性最好，与系统 3.13 隔离 | — |
| **LLM 应用基座** | **LangChain 0.3.x**：langchain-core / langchain-openai / langchain-community / langchain-milvus / langchain-huggingface / langchain-text-splitters | 锁定 0.3 小版本 | **全项目约定：能用 LangChain 的地方一律用 LangChain**（切分、向量化、检索、融合、LLM、结构化输出） | — |
| API 框架 | FastAPI + Uvicorn + Pydantic v2 | fastapi ≥0.115 | 异步、自动文档、类型安全 | FR-030、14.10–14.12 |
| 编排 | LangGraph（LangChain 同生态，节点内直接使用 LCEL 链） | ≥0.2 | 状态图 + 条件边 + 循环，契合 FR-024/025 | FR-021~025 |
| 知识图谱 | Neo4j Community（已建库） | 5.x | 已有数据，Cypher 表达 18 类关系 | 第 9 章 |
| 向量库 | Milvus standalone（Docker），经 **langchain-milvus** 接入 | ≥2.4 | 稠密检索 + 元数据过滤 | FR-022 |
| 文档切分 | **langchain-text-splitters**：RecursiveCharacterTextSplitter，自定义分隔符对齐 knowledge_base.txt 的文档/页标记 | — | RAG 入库切块 | 14.8 |
| Embedding | BGE-M3，经 **langchain-huggingface** HuggingFaceEmbeddings 本地推理 | BAAI/bge-m3 | 中文强，稠密向量；19 篇语料 CPU 可跑 | 检索质量 |
| 稀疏检索 | **langchain-community BM25Retriever**（rank_bm25，内存索引） | — | 语料量小，免维护独立引擎 | FR-022 |
| 多路融合 | **langchain EnsembleRetriever**（内置 RRF）：稠密 + BM25 两路融合 | — | 免手写 RRF | FR-022、ACC-015 |
| 重排（可选） | **ContextualCompressionRetriever + CrossEncoderReranker**（BGE-reranker-v2-m3），默认关 | — | 精度换延迟，按评测决定 | ACC-015 |
| LLM | **langchain-openai ChatOpenAI** → DeepSeek-V3（主）/ Qwen-max（备），base_url/model 可配 | OpenAI 兼容 | 网关抽象，厂商可换 | 第 20 章 |
| 缓存 | Redis 7.x（redis-py；LLM 结果缓存可复用 langchain RedisCache） | 7.x | 缓存 + SETNX 幂等锁 | FR-028/029 |
| 部署 | docker-compose | — | 一键起 Neo4j + Milvus + Redis | 第 13/20 章 |
| 测试/评测 | pytest + 自建评测集 | — | 意图/检索/幻觉三层评测 | ACC-013~021 |

**模型调用约定**：所有 LLM 调用经 `langchain-openai.ChatOpenAI`（temperature ≤ 0.3，max_tokens ≤ 800）；意图识别用 `with_structured_output()` 直接输出领域对象；业务代码不直接接触任何厂商 SDK，LangChain 组件全部封装在 infrastructure 层适配器内（遵守 3.1 依赖链）。

---

## 3. 总体架构

### 3.1 分层与依赖规则（强约束）

四层依赖**严格单向**，禁止反向、禁止跨层回环：

```text
interfaces  →  application  →  domain  →  infrastructure
```

- **interfaces** 只依赖 application；
- **application** 只依赖 domain（一切技术访问经 domain 服务，不直接 import infrastructure）；
- **domain** 依赖 infrastructure（领域服务封装技术组件，完成业务动作）；
- **infrastructure** 不依赖任何上层，只提供技术能力。

配套约束：

1. 换 LLM 厂商 / 换向量库 / 换缓存，只允许改 infrastructure 内部实现，domain/application/interfaces 不动；
2. 第 10 章业务规则中不涉及 I/O 的部分（宜忌判定、默认意图）为 domain 纯函数；涉及技术调用的（信息不足时的补查、风险提示组装）由 domain 服务完成；
3. prompt 模板属于应用层资产（application/prompts），domain 不持有；
4. 用 import-linter 在 CI 中固化上述依赖契约（`importlinter` contract: layered）。

### 3.2 静态架构图

```text
        ┌────────────────────────────────────────────┐
        │        interfaces 接口层（瘦）              │
        │   FastAPI 路由 · DTO · 统一异常处理          │
        │   POST /ask      GET /health (FR-030)      │
        └─────────────────────┬──────────────────────┘
                              ▼
        ┌────────────────────────────────────────────┐
        │        application 应用层（用例编排）        │
        │   AskUseCase（查缓存→跑图→回写缓存）          │
        │   LangGraph 主图（见第 4 章）                │
        │   prompts/（咨询口吻、来源标识 FR-022）       │
        └─────────────────────┬──────────────────────┘
                              ▼
        ┌────────────────────────────────────────────┐
        │        domain 领域层                        │
        │  实体/值对象: Question·Intent·Answer         │
        │              QAType(18类)·Mode·SourceType    │
        │  领域服务（封装 Infra，完成业务动作）:          │
        │   IntentService · KGQueryService            │
        │   RetrievalService · GenerationService      │
        │   ReliabilityService · CacheService         │
        │  纯规则(第10章): 宜忌判定·默认意图·信息不足·风险 │
        └─────────────────────┬──────────────────────┘
                              ▼
        ┌────────────────────────────────────────────┐
        │        infrastructure 基础设施层             │
        │  Neo4jRepo(Cypher) · MilvusRetriever        │
        │  HybridRetriever(EnsembleRetriever RRF)     │
        │  RedisCache(TTL+SETNX)                      │
        │  LLMGateway(OpenAI兼容→DeepSeek/Qwen)       │
        │  Embedder(BGE-M3) · Settings(.env)          │
        └────────────────────────────────────────────┘
```

### 3.3 运行时流程（一次问答的穿层旅程）

以「感冒不能吃什么？」（QAType=疾病—忌吃食品）为例：

```text
【interfaces】POST /ask → DTO 校验 → 移交 AskUseCase
【application】① 查缓存（经 domain.CacheService）──命中──▶ 返回
              ② 启动 LangGraph 主图
【application+domain】意图识别节点 → Intent{实体=感冒, QAType=疾病—忌吃食品}
【application】路由节点（FR-024）→ 模式 b：仅查 KG
【domain】KGQueryService.query(QAType, entity)
【infrastructure】Neo4jRepo 执行参数化 Cypher（只读账户）
【domain】结果校验（宜忌判定 / 查空走 10.3 信息不足）
【application】生成节点 → LLMGateway + prompt → 回答带 来源类型=结构化知识
【domain】可靠性分级（FR-023，分来源类型）
        │ 不足 → application 备用处理（FR-026/027：换通路重试 → 兜底话术）
【application】③ 回写缓存（TTL）
【interfaces】AskResponse → 咨询人员
```

### 3.5 组件—需求映射表

| 架构组件 | 承载的需求 |
|---|---|
| 意图识别节点 | FR-002、FR-003、10.2 |
| 路由节点（条件边） | FR-024、ACC-014 |
| KGQueryService + Neo4jRepo | FR-004~020、第 9 章、G-03 |
| RetrievalService + HybridRetriever | FR-021、14.8 |
| 生成节点 + prompts | FR-022（来源标识）、10.4、NFR-C01 |
| ReliabilityService | FR-023、ACC-018~021 |
| 备用处理节点 | FR-026/027、12.1~12.3、G-07 |
| CacheService + RedisCache | FR-028/029、12.4 |
| guard（路由节点内前置） | 12.7、G-09、13.1/13.2 |
| /health + 依赖探针 | FR-030、14.11 |

---

## 4. Agent 编排设计（LangGraph）

### 4.1 图状态（GraphState）

```python
class GraphState(TypedDict):
    question: str                # 原始问题
    normalized: str              # 规范化问题（缓存 Key 用）
    intent: Intent | None        # 领域对象：实体 + QAType + 置信度
    mode: Mode | None            # direct / kg / rag / hybrid
    kg_facts: list[Fact]         # KG 结构化事实（实体-关系-值）
    lit_chunks: list[Chunk]      # 文献片段（含 doc_title/page/doi/url）
    answer: str
    sources: list[Source]        # 带 source_type: kg | lit
    reliability: Reliability     # high / partial / low
    retries: int                 # 备用处理计数，≤2
```

### 4.2 节点与条件边

```text
                 ┌────────────────┐
                 │ classify_intent │  LLM 结构化输出 + 10.2 默认规则兜底
                 └───────┬────────┘
                         ▼
                 ┌────────────────┐
        ┌───────▶│  route (FR-024) │  guard 非法查询在此前置拦截（12.7）
        │        └───────┬────────┘
        │        ┌───────┼─────────────┬─────────────┐
        │        ▼       ▼             ▼             │
        │   [direct]  [kg_retrieve]  [rag_retrieve]  │
        │        │       │              │             │
        │        │       ▼              ▼             │
        │        │   ┌───────── fuse（混合时）────────┐ │
        │        │       │  KG事实高优先级注入           │ │
        │        │       │  文献 dense+BM25 → RRF 融合  │ │
        │        │       └───────┬─────────────────────┘ │
        │        ▼               ▼                       │
        │   ┌──────────────────────────┐                 │
        │   │ generate（带来源标识）     │ ◀─ FR-025 循环： │
        │   └────────────┬─────────────┘   KG 结果不足且  │
        │                ▼                 意图开放时回路由 │
        │   ┌──────────────────────────┐   再查（≤2 跳）    │
        │   │ reliability_check(FR-023) │                  │
        │   └────────────┬─────────────┘                   │
        │        ┌───────┴────────┐                        │
        │    high/partial      low/失败                    │
        │        │              ▼                          │
        │        │   ┌──────────────────────┐              │
        └────────┼───│ fallback（FR-026/027）│──────────────┘
                 │   │ 换通路重试 → 兜底话术  │
                 ▼   └──────────┬───────────┘
                 ┌──────────────▼───┐
                 │      respond      │──▶ 回写缓存（UseCase 层）
                 └──────────────────┘
```

### 4.3 路由策略（FR-024 的实现口径）

| 条件（按序判定） | 模式 |
|---|---|
| 非法查询（guard 命中） | 直接拒绝（12.7） |
| 寒暄/常识、无实体 | direct |
| QAType ∈ 18 类枚举 | kg（查空且 10.3 触发 → 降级 rag 重试一次） |
| 开放式问题且 LLM 判定"需要资料" | rag |
| 开放式问题且涉及具体疾病实体 | hybrid（先 KG 定位实体，再 RAG 取证据，FR-025） |

超时与重试：LLM 60s、Neo4j 5s、Milvus 5s、Redis 1s；节点级失败均进 fallback，fallback 最多换路 2 次（`retries ≤ 2`），最终输出固定话术之一（可用回答/信息不足/服务暂不可用，FR-027）。

**节点实现形态（LangChain 化）**：

- 意图识别节点：`ChatPromptTemplate | ChatOpenAI.with_structured_output(Intent)`，结构化输出直接落 Domain 对象；
- 生成节点：LCEL 链 `prompt 模板 | ChatOpenAI | StrOutputParser`，prompt 模板外置在 application/prompts；
- 检索节点：内部调 RetrievalService（封装 LangChain EnsembleRetriever，见 6.2）；
- 全图节点均为 LangChain Runnable，可用 LCEL 组合、可独立单测。

---

## 5. 模块设计

### 5.1 目录结构（DDD 四层）

```text
xinglin_health/
├── app/
│   ├── interfaces/
│   │   ├── http/routes.py          # /ask /health
│   │   ├── dto/schemas.py          # AskRequest / AskResponse
│   │   └── errors.py               # 统一异常→错误码映射（不泄露内部）
│   ├── application/
│   │   ├── usecases/ask_usecase.py
│   │   ├── graph/{state.py, build.py, nodes/}
│   │   └── prompts/*.md            # 模板用独立文件，版本可管
│   ├── domain/
│   │   ├── entities/               # Question/Intent/Answer/Source/Fact
│   │   ├── values/                 # QAType(18类) Mode SourceType Reliability
│   │   ├── services/               # Intent/KGQuery/Retrieval/Generation/
│   │   │                           # Reliability/CacheService
│   │   └── rules/                  # 第10章纯函数：diet_rule/default_intent/
│   │                               # insufficiency/risk_notice
│   └── infrastructure/
│       ├── neo4j_repo.py  ├── milvus_retriever.py
│       ├── hybrid_retriever.py     # EnsembleRetriever（内置 RRF）封装
│       ├── redis_cache.py ├── llm/{gateway.py, deepseek.py, qwen.py}
│       ├── embedder.py    └── config.py
├── evals/                          # intent_v1.jsonl / retrieval_v1.jsonl / 脚本
├── tests/
├── deploy/docker-compose.yml
├── scripts/ingest_docs.py          # knowledge_base.txt → Milvus 入库
└── docs/                           # 需求 V1.2 + 本文档
```

### 5.2 关键类职责

| 类/模块 | 层 | 职责 | 备注 |
|---|---|---|---|
| AskUseCase | application | 缓存查询→执行图→回写缓存→组装 DTO | 不含业务规则 |
| route（图节点） | application | guard 拦截 + FR-024 策略表 | 策略见 4.3 |
| QAType | domain | 18 类枚举 + 每类对应的 KG 关系模式与话术模板 | 第 9 章唯一落点 |
| rules/* | domain | 第 10 章纯函数，输入输出均为领域对象 | 100% 单测覆盖 |
| KGQueryService | domain | 按 QAType 选择 Cypher 模板并执行、结果转 Fact | 18 类 × 1 模板表 |
| RetrievalService | domain | 组装混合检索：EnsembleRetriever（Milvus 稠密 + BM25 稀疏，内置 RRF），top_k=8 | rerank 开关 |
| GenerationService | domain | LCEL 链（prompt \| llm \| parser）：KG 事实优先 + 文献片段，强制来源标识 | FR-022 |
| ReliabilityService | domain | 分来源类型的依据检查，输出 Reliability | 规则+LLM 自检双通道 |
| LLMGateway | infrastructure | 封装 langchain-openai ChatOpenAI，base_url/model 可配切换厂商 | 密钥仅在此层可见 |
| RedisCache | infrastructure | get/set/lock（SETNX），Key 规范见 6.3 | 序列化 JSON |

---

## 6. 数据设计

### 6.1 知识图谱（已建库，映射待对齐）

> ⚠ 现有 KG 由业务方提供。本章按通用医疗 KG 模式先行设计，**【待对齐】**项在实际 schema 确认后校准。需要业务方提供：节点标签清单、关系类型清单、属性字段、一条样例 Cypher/数据。

假设的关系模式（【待对齐】）：

```text
(:疾病 {name, 描述, 病因, 预防, 易感人群, 治疗周期, 治疗方式, 治愈概率, 所属科室})
  -[:症状]-> (:症状 {name})
  -[:并发症]-> (:疾病)
  -[:药品]-> (:药品 {name, 厂商})
  -[:检查]-> (:检查 {name})
  -[:宜吃]-> (:食品 {name})
  -[:忌吃]-> (:食品 {name})
```

18 类问答 → Cypher 模板映射（每类一个参数化模板，只读）：

| QAType | 模式（示意，【待对齐】） |
|---|---|
| 疾病—症状 | MATCH (d:疾病{name:$e})-[:症状]->(s) RETURN s.name |
| 症状—疾病 | MATCH (d:疾病)-[:症状]->(s:症状{name:$e}) RETURN d.name |
| 疾病—病因/预防/描述 | 属性读取：RETURN d.病因 / d.预防 / d.描述 |
| 疾病—治疗周期/方式/治愈相关/易感人群 | 同上，属性读取 |
| 疾病—并发症 | MATCH (d{name:$e})-[:并发症]->(c) RETURN c.name |
| 疾病—忌吃/宜吃食品 | MATCH (d)-[:忌吃\|宜吃]->(f) RETURN f.name |
| 食品—疾病（限制/推荐） | MATCH (d)-[:忌吃\|宜吃]->(f{name:$e}) RETURN d.name |
| 疾病—药品 / 药品—疾病 | MATCH (d)-[:药品]->(m) / 反向 |
| 疾病—检查 / 检查—疾病 | MATCH (d)-[:检查]->(c) / 反向 |

实现形态：`QAType` 枚举挂载 `cypher_template` 与 `answer_template` 字段，新增问答类型=加枚举项（NFR-MNT-01）。

### 6.2 文献语料切块与检索（LangChain 组件链）

**切块（langchain-text-splitters）**：以 knowledge_base.txt 的文档分隔符定位篇、`--- 第 N 页 ---` 定位页；RecursiveCharacterTextSplitter 以自定义 separators（`["\n--- 第 ", "\n\n", "。", "；"]`）切成 500–800 字、重叠 120 字的片段；每片段包装为 LangChain `Document`，metadata 携带 `{doc_id, doc_title, page_num, chunk_seq}`（来源定位信息，满足 14.8 追溯）。

**Collection：`medical_lit`**（仅存稠密向量，BM25 走内存索引）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INT64, auto-id | 主键 |
| chunk_text | VARCHAR ≤ 4000 | 片段正文 |
| dense | FLOAT_VECTOR(1024) | BGE-M3 稠密向量，HNSW(M=16, ef=200)，COSINE |
| doc_id | VARCHAR(64) | 源文件 SHA256 前 16 位 |
| doc_title | VARCHAR(256) | 文件名去扩展名 |
| page_num | INT32 | 页码 |
| chunk_seq | INT32 | 篇内片段序号 |

**多路融合（EnsembleRetriever 内置 RRF）**：RetrievalService 内部组装

```python
retriever = EnsembleRetriever(
    retrievers=[
        milvus_dense_retriever,   # langchain-milvus，top_k=8
        bm25_retriever,           # langchain-community，启动时由全量 Document 内存重建
    ],
    weights=[0.6, 0.4],           # EnsembleRetriever 默认按 RRF 融合
)
```

19 篇量级 BM25 重建为毫秒级；语料增长到万篇级后，演进路径是把 BM25 路替换为 Milvus sparse 混合检索（langchain-milvus / pymilvus hybrid_search），接口不变。

**入库**：`scripts/ingest_docs.py` 读 knowledge_base.txt → text-splitters 切块 → HuggingFaceEmbeddings 向量化 → langchain-milvus `Milvus.add_documents`（按 doc_id 幂等，重跑即增量）。

### 6.3 Redis Key 设计

| Key | 类型 | 值 | TTL | 用途 |
|---|---|---|---|---|
| `kb:ans:{h}` | STRING | AskResponse JSON | 24h | h=sha256(规范化问题)；FR-028 |
| `kb:lock:{h}` | STRING | 请求标识 | 60s | SETNX 防重复计算；FR-029 |
| 规范化规则 | — | 去空格/全半角统一/去标点/小写 | — | 保证同义写法命中同一 Key |

### 6.4 日志

结构化 JSON 日志（时间/请求ID/规范化问题/模式/耗时/来源数/状态），落本地文件按天滚动，**留存 ≥ 90 天**；问题原文入库前做手机号/身份证正则脱敏（13.3 延伸）。

---

## 7. 接口设计

### 7.1 POST /ask

```jsonc
// 请求（FR-024 已定：不提供检索模式入参）
{ "question": "感冒不能吃什么？" }

// 响应 200
{
  "status": "ok",                  // ok | insufficient_info | service_unavailable
  "mode": "kg",                    // direct | kg | rag | hybrid（系统自选，供展示/调试）
  "answer": "感冒期间建议避免……",
  "sources": [                     // FR-022：来源类型必标
    { "type": "kg", "label": "知识图谱", "relation": "忌吃", "entity": "感冒" },
    { "type": "lit", "title": "...", "journal": "中国全科医学",
      "year": 2025, "doi": "...", "url": "...", "loc": "第3页" }
  ],
  "reliability": "high",           // high | partial | low（FR-023）
  "cached": false
}
```

### 7.2 GET /health

```json
{ "status": "ok", "dependencies": { "neo4j": "ok", "milvus": "ok", "redis": "ok", "llm": "ok" } }
```

### 7.3 错误码与超时

| 码 | 场景 | 对外行为 |
|---|---|---|
| 400 | 参数缺失/超长（问题 > 500 字） | 明确提示 |
| 422 | 无法识别的问题 | 兜底回答（FR-001） |
| 429 | 触发限流（预留） | 稍后再试 |
| 500 | 内部异常 | 统一话术，隐藏细节（ACC-031） |
| 503 | 关键依赖不可用且降级失败 | 服务暂不可用提示 |

整体链路超时 65s；`/ask` 并发保护由 Redis 锁承担（FR-029）。

---

## 8. 非功能设计（量化指标）

> 以下指标承接《需求文档》第 14 章，取值以"内部工具、单机部署、合理好达成"为原则，可随压测结果修订。检索命中率、幻觉率等评测阈值见第 12 章，不在本表重复。

| 编号 | 指标 | 目标值 | 说明 |
|---|---|---|---|
| NFR-T01 | 端到端延迟 | 固定问答 P95 ≤ 3s；开放式完整回答 P95 ≤ 30s；缓存命中 P95 ≤ 500ms | 瓶颈在 LLM API |
| NFR-T02 | 并发能力 | ≥ 10 路并发不降级 | 内部咨询人员规模 |
| NFR-A01 | 可用性与降级 | 工作时段可用性 ≥ 99%；单依赖故障 ≤ 5s 自动切换 | FR-026/027 |
| NFR-C01 | 单次回答长度 | 正文 ≤ 600 字 | 超长自动分节（PERF-03） |
| NFR-R01 | 意图分类准确率 | ≥ 90%（评测集 ≥ 570 条） | ACC-013/014 的量化 |
| NFR-R02 | 来源标识率 | 100%（direct 模式除外） | FR-022 强制 |
| NFR-R03 | 无依据陈述占比 | 人工抽检 50 条 ≤ 10% | ACC-020/021 的量化 |

---

## 9. 安全设计

- **只读**：问答链路使用 Neo4j 只读账户；全部 Cypher 参数化，禁止字符串拼接（13.1/13.2）；
- **输入防护**：`guard` 前置拦截（长度、注入特征、数据修改意图），命中即拒（12.7/G-09）；
- **密钥管理**：全部密钥走 `.env`（gitignore），仅 infrastructure 层读取（13.3）；
- **错误隐藏**：interfaces 统一异常处理器将内部异常映射为 500+统一话术，原始堆栈只进日志（ACC-031）；
- **脱敏**：日志中问题原文经手机号/身份证正则脱敏。

---

## 10. 部署方案

### 10.1 docker-compose（Neo4j + Milvus + Redis）

```yaml
services:
  neo4j:
    image: neo4j:5-community
    environment: [NEO4J_AUTH=none]        # 内网演示；生产改账密
    ports: ["7474:7474", "7687:7687"]
    volumes: [neo4j_data:/data]
  etcd:      { image: quay.io/coreos/etcd:v3.5.14, ... }
  minio:     { image: minio/minio, ... }
  milvus:
    image: milvusdb/milvus:v2.4.x-standalone
    depends_on: [etcd, minio]
    ports: ["19530:19530"]
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
volumes: { neo4j_data: {}, milvus_data: {} }
```

应用本体 `uvicorn app.interfaces.http:app` 本机运行（开发/演示形态）；后续内网部署可将 app 一并容器化。

### 10.2 环境变量（.env）

```text
NEO4J_URI=bolt://localhost:7687   NEO4J_USER=readonly   NEO4J_PASSWORD=***
MILVUS_URI=http://localhost:19530 REDIS_URL=redis://localhost:6379/0
LLM_PROVIDER=deepseek  LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=***        LLM_MODEL=deepseek-chat
EMBEDDING_MODEL=BAAI/bge-m3   RERANK_ENABLED=false
CACHE_TTL_HOURS=24     LOG_DIR=./logs
```

---

## 11. 开发计划（增量迭代）

| 迭代 | 内容 | 对应验收 | DoD |
|---|---|---|---|
| I0 骨架（第 1 周） | 四层目录 + compose + LLM 网关连通 + /health | — | 四依赖全绿 |
| I1 固定问答通路（第 2~3 周） | 意图识别 → KG 模板查询 → 组装回答；评测集 v1 | ACC-002~010、013 | 18 类全通 |
| I2 RAG 通路（第 3~4 周） | 19 篇入库 → Milvus → 混合检索 RRF → 带引用生成 | ACC-001、011、015、018~021 | 开放问答带来源 |
| I3 编排与可靠性（第 5 周） | FR-022~025 全链路 + FR-026/027 降级链 | ACC-014、016、017、022~027 | 断 KG 仍能答 |
| I4 缓存与安全（第 6 周） | Redis 缓存/幂等、guard 拦截、密钥外置、日志脱敏 | ACC-028~031 | 重复问题秒回 |
| I5 评测与验收（第 7 周） | 全量 ACC-001~035 回归、压测 10 并发、调优 | 全部 | 验收报告 |

每个迭代结束做一次可演示增量（敏捷评审），评测集随迭代扩充。

---

## 12. 评测方案

| 评测项 | 数据集 | 指标与阈值 | 对应 |
|---|---|---|---|
| 意图分类 | 18 类 × 30 条 + 开放式 50 条 + 非法/兜底 30 条（≈620 条） | acc ≥ 90%（NFR-R01） | ACC-013/014 |
| 路由正确性 | 上述集标注期望模式 | 路由一致率 ≥ 85% | FR-024 |
| 检索命中 | 人工标注"问题→应命中文档"子集 ≥ 60 条 | hit@5 ≥ 80% | ACC-015 |
| 幻觉抽检 | 随机 50 条真实回答 | 无依据陈述 ≤ 10% | ACC-020/021 |
| 回归 | 每迭代全量跑 evals/ | 不低于上一迭代 | — |

---

## 13. 待办与风险

| # | 事项 | 影响 | 状态 |
|---|---|---|---|
| 1 | **KG schema 对齐**：需业务方提供节点标签/关系/属性/样例数据 | 6.1 模板表落笔、I1 启动 | 【阻塞 I1】 |
| 2 | LLM 成本估算与厂商最终确认（DeepSeek/Qwen） | 8 章延迟指标 | 建议 I0 用 DeepSeek 实测 |
| 3 | Windows Docker Desktop（WSL2）环境确认 | I0 | 待环境检查 |
| 4 | rerank 是否启用 | ACC-015 精度 vs 延迟 | 默认关，I2 后按评测决定 |
| 5 | LangChain 0.3 API 迭代较快 | 组件升级破坏兼容 | requirements 锁定小版本，升级走单独迭代 |

# 杏林大健康 AI 问答系统（第二代 · xinglin_plus）

面向**健康问答**的检索增强系统：把「结构化知识图谱」与「医学文献」两路召回合起来，
由 Agent 按问题自动选路，生成后再用**事实护栏**做一次独立核查以抑制幻觉；
所有外部依赖（图数据库 / 向量库 / 大模型 / 缓存）都被端口-适配器关在基础设施层，
领域能力可以**离线单测**。

- **四种问答形态**：`hybrid`（默认双路）、`rag`（仅文献）、`nl2cypher`（仅图谱）、`agent`（ReAct）
- **三层图谱通路**：模板精确查询 → NL2Cypher → 规则兜底链（模型挂了图谱也不挂）
- **两条降级链**：文献不可用只走图谱；图谱不可用回落零 LLM 规则流水线
- **防幻觉**：`domain/guardrail` 用**第二次 LLM 调用**核查答案是否被参考上下文支撑
- **自带前端**：单文件对话界面（`frontend/index.html`），由 Web 服务托管，支持**深/浅色主题切换**
- **可测试**：领域层不碰 SDK，测试全离线（147 用例，无需网络与 Docker）

---

## 一、快速开始

### 1. 依赖服务

| 服务 | 地址 | 用途 |
|---|---|---|
| **Neo4j** | `neo4j://127.0.0.1:7687`，库 `medical` | 结构化知识：8808 疾病 / 7 类节点 / 10 类关系 |
| **Milvus** | `http://localhost:19530`，集合 `medical_lit` | 文献向量：762 条切片（384 维） |
| **DeepSeek** | 系统环境变量 `DEEPSEEK_API_KEY` | NL2Cypher 生成、融合生成、护栏核查 |
| Redis | `redis://localhost:6379/0` | 可选缓存（`--cache`） |

连接参数集中在 `.env`；**密钥只从环境变量读，不进代码、不进库**。

### 2. 安装与运行

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt

.venv\Scripts\python.exe -X utf8 main.py                       REM 交互式（默认 hybrid）
.venv\Scripts\python.exe -X utf8 main.py -q "感冒有什么症状？"    REM 单次提问
.venv\Scripts\python.exe -X utf8 main.py --mode agent -q "..."   REM 指定形态（开发/演示）
```

也可直接双击 `run_cli.bat` / `run_web.bat`。HTTP 服务：

```bat
python -m xinglin.interfaces.web --mode agent --host 127.0.0.1 --port 8000
REM 对话界面：http://127.0.0.1:8000/     （自带深/浅色主题切换）
REM 接口文档：http://127.0.0.1:8000/docs
REM 端点：POST /v1/chat ｜ GET /health
```

> ⚠ 监听地址用 `127.0.0.1`（本机访问，最稳）。开发文档 §8.3 的示例是 `0.0.0.0`
> （供局域网访问），但 Windows 下常被防火墙拦截，表现为浏览器一直转圈/超时。
> 确实需要外部访问时再改成 `0.0.0.0`，并在防火墙弹窗中选"允许访问"。

### 3. 四种问答形态（`--mode`）

| 模式 | 走的通路 | 说明 |
|---|---|---|
| `hybrid`（默认） | 图谱 + 文献 | 双路融合 + **FR-024 自动选路** + FR-026 依据不足时换路重试 |
| `rag` | 仅文献 | 稠密（Milvus）+ 稀疏（BM25）→ RRF 融合 |
| `nl2cypher` | 仅图谱 | **模板 → NL2Cypher → 规则兜底链** 三层递进 |
| `agent` | LLM 自主决策 | ReAct 循环：自己决定调图谱还是查文献、调几次 |

> ⚠ 模式只在**启动时**指定：CLI 用 `--mode`，Web 用 `python -m xinglin.interfaces.web --mode agent`。
> HTTP 请求体里**不带**模式参数——咨询人员不可指定检索模式（FR-024 / 需求 6.2）。

---

## 二、数据流向

### 2.1 `hybrid` 模式（默认，一次问答的完整链路）

```text
用户问题：「2型糖尿病的药物治疗有哪些新进展？」
    │
    ├─① 意图分类（domain/services/intent_service.py）
    │     LLM 通道：把 18 类编号表交给模型，要求只回一个 JSON
    │               （entity / entity_type / qa_type_code / open_ended）
    │     规则通道：LLM 不可用时 → 词典最长匹配实体 + 关键词表 + 10.2 默认规则
    │     开放式信号词（"新进展 / 为什么 / 对比 / 机制"）优先于关键词命中
    │     ──▶ Intent(entity="糖尿病", qa_type=None, open_ended=True)
    │
    ├─② 自动选路（application/hybrid_agent.py::_route）—— FR-024
    │     开放式 + 有实体 ──▶ hybrid 双路
    │     开放式 无实体   ──▶ rag 文献
    │     命中 18 类/有实体 ─▶ kg 结构化知识
    │     寒暄 / 常识      ──▶ direct 不检索
    │     ──▶ Mode.HYBRID
    │
    ├─③ 双路召回
    │     ├─ 图谱召回 _graph_recall()  —— 三层递进，前一层空才走下一层
    │     │     ① 模板精确查询（QAType 元数据 → 参数化 Cypher）  零 LLM、结果确定
    │     │     ② NL2Cypher：LLM 生成 Cypher → 规则校验 + EXPLAIN 预检 → 执行
    │     │     ③ 规则兜底链 fallback/：词典实体识别 + 规则拼 Cypher（零 LLM）
    │     │     失败只降级为空，不阻塞
    │     └─ 文献召回 RAGAgent.recall()
    │           Milvus 稠密检索 + 本地 BM25 稀疏检索 → RRF 融合 → Top-K
    │           每段都带「来源文件 + 页码」（可追溯）
    │
    ├─④ 融合生成（domain/services/generation_service.py）
    │     把 <graph_facts> 与 <context> 两路信息一起交给 DeepSeek 生成中文回答
    │     direct 通路 或 LLM 不可用 ──▶ 零幻觉的模板回答（100% 来自证据）
    │
    ├─⑤ 依据分级（domain/services/reliability_service.py）—— FR-023
    │     仅结构化知识 → high ｜ 含文献 → partial ｜ 无依据/direct → low
    │
    ├─⑥ 事实护栏（application/hybrid_agent.py::_guard）
    │     _fuse() 把两路证据拼成参考上下文
    │     FactGuardrail.check() —— **第二次 LLM 调用**，独立核查答案有无依据
    │     无依据 ──▶ 在答案末尾追加「（提醒：…请谨慎参考。）」，**不拦截**
    │     核查失败 / 无上下文 ──▶ fail-open 直接放行
    │
    └─⑦ 组装 Answer：正文 + 来源标识（FR-022）+ 可靠性 + 风险提示（10.4）
```

**为什么护栏要独立成第二次调用**：同一轮里既当"答题者"又当"裁判"时，模型倾向于为
刚写出的答案辩护（自检偏见）。分开调用后它面对的是"一段声明 + 一段证据"的干净任务。

### 2.2 `agent` 模式（ReAct，多跳）

```text
用户问题：「感冒应该如何治疗？常用药物有哪些？」
    │
    ├─① ReAct 循环（application/tool_agent.py，LangGraph create_react_agent）
    │     LLM 自主决定：调不调工具、调哪个、调几次
    │       ├─ graph_search(question)        → 图谱三层递进
    │       └─ literature_search_tool(q)     → Milvus + BM25 → 带出处的文本
    │     工具**返回可读字符串而非抛异常**：失败也是一种"观察结果"，
    │     模型据此自主转向或承认查不到
    │     （"你好"这类问候可能一次工具都不调，直接作答）
    │
    ├─② 从 messages 历史中过滤 ToolMessage，拼接作为护栏依据
    │     未调工具 → 上下文为空 → 护栏自动跳过
    │
    ├─③ 事实护栏（同 2.1 的 ⑥）
    │
    └─④ ReAct 失败（超步数 / LLM 异常 / 空回答）→ 回落 HybridAgent 自动路由
```

`agent` 补齐了 `hybrid` 的两块短板：**简单问题不再强制双路召回**；
**多跳问题**（先查图谱、再据图谱结果决定查哪篇文献）由 LLM 自主编排。

### 2.3 `rag` / `nl2cypher` 模式（固定单路）

```text
rag      : 问题 → RAGAgent.recall()（稠密 + 稀疏 → RRF，带来源页码）
              → 生成 → 依据分级 → 事实护栏 → Answer

nl2cypher: 问题 → 意图分类 → 图谱三层递进（模板 → NL2Cypher → 规则兜底链）
              → 生成 → 依据分级 → 事实护栏 → Answer
```

### 2.4 降级矩阵（任何时候都不空手而归）

| 挂掉的组件 | 系统行为 |
|---|---|
| LLM（无 Key / 超时） | 意图分类走规则通道；图谱走规则兜底链；生成走模板回答 |
| Neo4j | 图谱召回降级为空；`hybrid` 退化为纯文献；`direct` 仍可用 |
| Milvus / BM25 | 文献召回降级为空；`hybrid` 退化为纯图谱 |
| 护栏自身异常 | fail-open 放行（宁可漏检，不可因此中断问答） |
| Redis（`--cache`） | 直接问答，只是没了秒回 |

---

## 三、项目架构

```text
┌────────────────────────────────────────────────────────────────┐
│ 接口层 interfaces                                              │
│   cli.py  —— 解析 --mode / --cache，驱动交互循环                │
│   web.py  —— POST /v1/chat、GET /health（模式在启动时固定）      │
└───────────────────────────────┬────────────────────────────────┘
                                │ 按模式实例化 Agent
┌───────────────────────────────▼────────────────────────────────┐
│ 应用编排层 application（用例编排）                              │
│   runtime.py          组合根：唯一装配点，@lru_cache 复用重对象   │
│   hybrid_agent.py     双路融合 + 自动选路 + 重试 + 事实护栏（默认）│
│   rag_agent.py        仅文献；recall() 产出带出处的上下文        │
│   nl2cypher_agent.py  仅图谱：主路径 + 旧流水线兜底              │
│   tool_agent.py       ReAct：LLM 自主决策调哪个工具、调几次      │
│   tools.py            把「图谱查询 / 文献检索」封装成两个 @tool   │
└───────────────────────────────┬────────────────────────────────┘
                                │ 组装领域能力
┌───────────────────────────────▼────────────────────────────────┐
│ 领域层 domain（业务能力，只依赖端口 ↔ 可离线单测）               │
│   rag/        embeddings（本地向量模型）+ vectorstore（Milvus）  │
│   graph/      nl2cypher + schemas + prompts + validators        │
│   guardrail/  fact_guardrail（事实护栏，LLM 二次核查）           │
│   rules/      第 10 章业务规则（8 个纯函数模块）                  │
│   services/   意图 / 图谱查询 / 文献检索 / 生成 / 依据分级 / 缓存  │
│   ports.py    端口抽象：LLM、GraphStore、LiteratureSearch …      │
│   values.py   值对象：QAType（18 类固定问答）、Mode、Reliability  │
│   entities.py 领域实体：Intent、Fact、Source、Answer              │
└───────────────────────────────┬────────────────────────────────┘
                                │ 端口实现（依赖倒置）
┌───────────────────────────────▼────────────────────────────────┐
│ 基础设施层 infrastructure                                       │
│   llm.py    create_llm()（LangChain）+ OpenAILlm（实现 LLM 端口）│
│   graph.py  Neo4jGraph：只读会话 + 参数化 Cypher                 │
│   cache.py  RedisManager + 模块级 redis_manager                  │
│   init_data/ 词典导出等派生产物脚本                              │
└────────────────────────────────────────────────────────────────┘

    ┌──────────────────────────────────────────────────────┐
    │ 兜底层 fallback/（第 1 代规则流水线，零 LLM）          │
    │   dictionary / question_classifier_v2 / question_parser_v2 │
    │   answer_search_v2 / robot_qwen（编排 + 可选 Qwen 兜底）│
    └──────────────────────────────────────────────────────┘
```

### 三条硬规则（由 `tests/test_architecture.py` 用 AST 静态固化）

1. **依赖方向只能由外向内**：`domain` 不得 import 任何外层（`infrastructure` / `application` /
   `interfaces` / `fallback`）；`application` 不能 import `interfaces`；
   `fallback` 不能 import `application` / `interfaces`。
2. **只有 `runtime.py` 可以装配基础设施**：它是全应用唯一的组合根，
   其余 application 模块只能通过它取已装好的依赖。
3. **数据/资源归领域层所有**：`data/`、`dict/`、向量库、图谱都只能由 `domain/` 读写，
   `interfaces` 不得直接触碰（唯一白名单是文档 §4.6 的 `--cache` 用法）。

### 为什么是「分层 + 端口-适配器」

复杂度不在展示层（`web.py` 只有两个端点、`cli.py` 只是一个循环），而在领域规则
（NL2Cypher 的生成-校验-执行、Cypher 注入拦截、事实核查、双路融合）；
同时要隔离 Neo4j / Milvus / DeepSeek 三个外部依赖 —— 这正是端口-适配器擅长的事。

它**不需要**完整 DDD：本项目是**纯查询系统**，没有状态变化、没有业务不变量、
没有写操作副作用链，因此没有聚合根/实体/领域事件；`Answer` 是**读模型**而非聚合。
详见 `docs/DDD架构分析.md`。

---

## 四、项目内容

### 4.1 目录结构

```text
xinglin_plus/
├── main.py                        统一入口（根目录运行）
├── readme.md                      本文件
├── requirements.txt               依赖清单
├── run_cli.bat / run_web.bat      一键启动
├── .env                           环境配置（密钥只读系统环境变量）
├── frontend/index.html            单文件对话界面（深/浅色主题，由 Web 托管在 /）
├── xinglin/                       ★ 主包
│   ├── config.py                  全局配置（最底层依赖，不 import 业务模块）
│   ├── interfaces/                cli.py + web.py
│   ├── application/               四个 Agent + tools.py + runtime.py
│   ├── domain/                    rag/ graph/ guardrail/ rules/ services/ + 端口与值对象
│   ├── infrastructure/            llm.py + graph.py + cache.py + init_data/
│   └── fallback/                  第 1 代规则流水线（零 LLM 兜底）
├── tests/                         147 用例，全离线
├── data/                          medical.json + pdfs/
├── dict/                          8 类医学词典
├── docs/                          需求文档 / 技术文档 / DDD架构分析 / 项目结构与文件说明
└── models/                        本地模型目录
```

每个文件的具体职责见 `docs/项目结构与文件说明.md`。

### 4.2 数据 / 资源

| 数据 | 位置 / 形态 | 说明 |
|---|---|---|
| 原始医疗数据 | `data/medical.json`（47 MB） | 8808 条疾病记录，**建图脚本的输入**，非运行期依赖 |
| 医学文献 PDF | `data/pdfs/` | 20 篇，**已切好并入库**，日常无需重切 |
| 医学词典 | `dict/*.txt` | 8 类：7 类实体（疾病/症状/药品/食品/检查/科室/生产商）+ 否定词 |
| 稀疏检索语料 | `data/bm25_docs.json` | 切片正文 + 元数据，BM25 的数据源 |
| 知识图谱 | Neo4j 库 `medical` | 7 类节点、10 类关系 |
| 文献向量 | Milvus 集合 `medical_lit` | 762 条 × 384 维 + 元数据（标题 / 页码 / 切片序号 / 期刊） |

> **日常不需要任何数据准备**——图谱与向量库都是就绪的。
> 只在换机器、清了 `data/`、或数据源更新时才需要跑脚本：

```bat
REM 从既有向量集合导出稀疏路语料
.venv\Scripts\python.exe -X utf8 -m xinglin.domain.rag.vectorstore --export-bm25
REM 从图谱重新导出词典
.venv\Scripts\python.exe -X utf8 -m xinglin.infrastructure.init_data.export_dict
REM （可选）从 data/medical.json 重建图谱：MERGE 幂等，先干跑再 --write
.venv\Scripts\python.exe -X utf8 -m xinglin.domain.graph.build_graph --limit 300
.venv\Scripts\python.exe -X utf8 -m xinglin.domain.graph.build_graph --write
```

### 4.3 领域知识的载体

| 构件 | 位置 | 作用 |
|---|---|---|
| **`QAType`** | `domain/values.py` | 18 类固定问答的**唯一事实源**，每条挂载 Cypher 模板元数据（kind / key / source_role / target_role），路由与图谱查询都以它为准 |
| **`EntityRole`** | `domain/values.py` | 中文业务名 ↔ 图谱节点标签的唯一映射 |
| `domain/rules/` | 8 个纯函数模块 | 第 10 章业务规则：宜忌方向、默认意图、信息不足、风险提示、非法拦截、关键词表、开放式判定、话术模板 |
| `fallback/dictionary.py` | 8 类词典 | **最长优先**实体识别，实现 `EntityRecognizer` 端口（意图分类与规则链共用同一口径） |

### 4.4 关键配置（`.env`）

| 键 | 默认 | 说明 |
|---|---|---|
| `NEO4J_URI` / `NEO4J_DATABASE` | `neo4j://127.0.0.1:7687` / `medical` | 图数据库 |
| `LLM_API_KEY` | 空 | 留空则读系统变量 `DEEPSEEK_API_KEY` |
| `LLM_TRUST_ENV` | `false` | **国内 API 必须为 false**：走系统代理会连接失败 |
| `MILVUS_URI` / `MILVUS_COLLECTION` | `http://localhost:19530` / `medical_lit` | 向量库 |
| `RETRIEVAL_TOP_K` | `8` | 文献召回条数 |
| `SEARCH_SCORE_THRESHOLD` | `0.65` | 稠密路相似度阈值（只适用于单路绝对分） |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `600` / `100` | 切片参数 |
| `GUARDRAIL_ENABLED` | `true` | 事实护栏开关（关掉可省一次 LLM 调用） |
| `REDIS_URL` / `CACHE_TTL_HOURS` | `redis://localhost:6379/0` / `24` | 缓存 |

---

## 五、测试

```bat
.venv\Scripts\python.exe -X utf8 -m pytest tests/ -q        REM 147 用例，全离线
```

测试**不连任何外部服务**：Neo4j / Milvus / LLM 全部用 `tests/conftest.py` 的替身注入，
因此无网、无 Docker 也能完整回归。覆盖面：分层边界（AST）、端口契约、第 10 章规则、
事实护栏、意图分类与路由、Agent 编排与重试、Cypher 拼装与校验、向量元数据口径、
规则兜底链、接口层 DTO。

**排障提示**：若回答像是"旧内容"，多半是 Redis 命中了改代码之前的缓存，清一次即可：

```bat
docker exec xinglin-redis redis-cli FLUSHDB
```

---

## 六、文档导航

| 文档 | 内容 |
|---|---|
| `docs/需求文档.md` | 功能需求 → 实现位置 → 对应测试 的追溯表 |
| `docs/技术文档.md` | 架构、数据流、护栏口径、配置项 |
| `docs/DDD架构分析.md` | 为什么是本架构；三条硬规则；依赖倒置怎么落地 |
| `docs/项目结构与文件说明.md` | 每个目录、每个文件、每份数据的职责 |

---

## 七、与《项目开发指导》的差异（刻意为之）

| 项 | 指导文档 | 本项目 | 原因 |
|---|---|---|---|
| 图数据库库名 | `xinglin` | `medical` | 本地实例中不存在 `xinglin` 库，数据在 `medical` |
| 向量库 | Milvus Lite（嵌入式 `./milvus_agent.db`） | 既有 Milvus 服务 + 集合 `medical_lit` | 复用已就绪的生产形态，避免重复灌数据 |
| 稀疏检索 | Milvus 内置 BM25 稀疏字段 | 本地 BM25 内存索引（语料由集合导出） | 既有集合是单稠密字段；两路语料逐条一致，RRF 融合才有意义 |
| 向量模型 | BGE-M3（`models/bge-m3/`） | 自有 HuggingFace 模型（384 维） | `models/bge-m3/` 为空目录，改用本机已缓存的模型 |
| 建库脚本位置 | 统一放 `infrastructure/` | 建图在 `domain/graph/`、向量化在 `domain/rag/` | 能力与被复用代码同址（检索侧与建库侧共用同一逻辑） |

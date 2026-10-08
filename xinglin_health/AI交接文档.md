# AI 交接文档 · 杏林大健康 AI 问答系统

> 写给下一个接手的 AI/开发者。读完这一份即可上手，无需翻聊天记录。更新至 2026-10-08。

---

## 1. 项目是什么（30 秒版）

大健康企业**内部咨询辅助工具**（刻意规避医疗合规类需求）：咨询人员输入中文健康问题，返回带**来源类型标识**和**可靠性分级**的回答。定位是信息咨询，非诊疗。

三条通路，由 Agent（LangGraph）按 FR-024 自动路由，用户不可指定：
- **KG 路**：18 类固定问答 → Neo4j 参数化 Cypher 精确查询（实体-关系事实）
- **RAG 路**：19 篇文献 762 切片 → 稠密向量(Milvus) + BM25 → EnsembleRetriever RRF 融合
- **direct**：寒暄/常识直接回答

## 2. 文件与路径（全部实测存在）

| 路径 | 内容 |
|---|---|
| `D:\project_phase\medical\xinglin_health\` | **项目根**：代码 + 文档 + 前端 + bat |
| `xinglin_health\app\` | 业务代码，DDD 四层（见 §3） |
| `xinglin_health\杏林大健康AI问答系统需求规格说明书_V1.2.md` | 需求文档（FR-001~030、18 类问答、ACC-001~035） |
| `xinglin_health\杏林大健康AI问答系统技术设计说明书_V1.0.md` | 技术文档（架构/数据/接口/NFR 量化/迭代计划） |
| `xinglin_health\README.md` | 启动/代码地图/业务流程/数据流向 |
| `xinglin_health\.venv\` | Python 3.13 运行环境（依赖已全部装好，**勿用系统 conda base**） |
| `xinglin_health\.env` | 实际配置（Neo4j 账密 neo4j/12345678、database=medical；LLM_API_KEY 缺省自动读系统变量 `DEEPSEEK_API_KEY`） |
| `D:\project_phase\medical\medical\knowledge_base.txt` | RAG 语料源（19 篇文献合并文本，带文档/页分隔符） |
| `D:\project_phase\medical\medical\build_knowledge_base.py` | PDF→合并语料脚本（换 PDF 后重跑） |
| `D:\project_phase\medical\medical_eno4j\` | 用户建 KG 用的脚本工程（medical.json 数据源） |
| `D:\milvus_docker\docker-compose.yml` | 用户的 Milvus 栈（milvus v2.6.1 + etcd + minio + attu:8900） |

## 3. 架构与依赖规则（强约束，用户明确要求）

```
interfaces → application → domain → infrastructure   （只能这个方向）
```
- application **不直接 import** infrastructure，技术访问全经 domain 服务封装；
- `app/wiring.py` 是组合根（唯一装配点）；
- LangGraph 主图在 application 层（`app/application/graph/build.py` + `nodes.py`），8 节点：classify_intent → route → kg_retrieve / rag_retrieve → generate → reliability_check → fallback → respond；
- **QAType 枚举**（`app/domain/values/qa_type.py`）是 18 类问答唯一事实源，挂载 Cypher 模板元数据，已对齐真实 KG（英文标签 Disease/Symptom/Drug/Food/Check；关系 has_symptom/acompany_with/no_eat/do_eat/recommand_drug/need_check；属性 cause/prevent/cure_lasttime/cure_way/cure_prob/easy_get/desc）；
- 第 10 章业务规则 = `app/domain/rules/` 纯函数（宜忌判定/默认意图/信息不足/风险提示/非法拦截）。

用户偏好：**增量开发（六迭代 I0~I5）+ DDD + 能用 LangChain 一律用 LangChain**；安全合规类需求刻意不做；NFR 量化指标在技术文档第 8 章（已定值）。

## 4. 运行环境（关键端口与依赖）

| 依赖 | 地址 | 说明 |
|---|---|---|
| Neo4j（用户 KG） | neo4j://127.0.0.1:7687，database=`medical` | 用户原生安装，非 Docker；**每次开机需确认它在跑** |
| Milvus | http://localhost:19530 | `cd D:\milvus_docker && docker compose up -d`；**容器无 restart 策略，重启机器后要重新 up** |
| Redis | redis://localhost:6379/0 | 容器 `xinglin-redis`（已设 unless-stopped） |
| LLM | DeepSeek API | Key 读系统环境变量 `DEEPSEEK_API_KEY`；网关已设 trust_env=False 绕系统代理 |

⚠ 机器上还跑着一套 **Dify**（D:\dify，11 容器，占 80/5003 端口），与本系统无冲突但吃内存（16GB 机器）；卡顿时可停 Dify。

## 5. 启动与验证（全部实测）

```bash
cd D:\project_phase\medical\xinglin_health
# 依赖服务（重启机器后）：milvus 栈 up + 确认 neo4j 在跑
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000    # 或 .venv\Scripts\python.exe -m app.main
```
- 验证：`GET /health` → 四依赖全 ok/configured；`POST /ask {"question":"感冒有什么症状？"}` → mode=kg；`"2型糖尿病的药物治疗有哪些新进展？"` → mode=rag（带 lit 来源）；
- 测试：`.venv\Scripts\python.exe -m pytest tests/ -q`（24 个用例）；
- 前端：双击 `启动前端.bat`（或 `index.html`）；后端：双击 `启动后端.bat`；
- 扩量入库：`scripts/ingest_docs.py`（重跑幂等，先更新 knowledge_base.txt）。

## 6. 踩过的坑（已修复，别再踩）

1. **LangGraph 会静默丢弃不在 State TypedDict 里的返回键** → 曾致 fallback 死循环（GraphRecursionError）。新增状态字段必须同步 `graph/state.py`；
2. **transformers 必须 `<5`**（已 pin 4.57.6）：v5 无法加载旧版 sentence-transformers 模型仓库（用户本地模型 paraphrase-multilingual-MiniLM-L12-v2，384 维，HF 缓存已有，用 `HF_HUB_OFFLINE=1`）；
3. **langchain 1.4 下 EnsembleRetriever 在 `langchain_classic.retrievers`**，不在 `langchain.retrievers`；
4. **LLM 网关必须 trust_env=False**：系统代理环境变量会劫持 DeepSeek 调用导致连接失败；
5. neo4j 驱动参数是 `connection_timeout`（秒），`connection_timeout_ms` 会报 Unexpected config keys；连接必须带 `database="medical"`（默认 neo4j 库是空的）；
6. **bat 文件必须 CRLF 换行**（LF 会让 cmd 解析错乱闪退）；延时用 `ping -n 5 127.0.0.1` 别用 timeout（Git Bash 有同名 GNU 命令遮蔽）；
7. **中文输出在 GBK 控制台必然乱码**（仅显示问题，载荷是好的）：测 API 用 `.venv\Scripts\python.exe -X utf8` + httpx，别用 curl 直发中文；
8. 后端必须**项目根目录 + `-m` 模块方式**运行（`python app/main.py` 直接跑会 No module named 'app'）；
9. 异常细节只进日志，`meta.notes` 对外只给分类话术（ACC-031 内部错误隐藏）。

## 7. 当前进度与待办

**已完成**：需求 V1.2 → 技术文档 V1.0 → I0~I4 全部代码 + I1/I2/I3/I4 运行时验收（四依赖全绿、双路 RAG、降级链、拦截、24 测试）→ 前端 + bat → 生产存储形态（762 向量进真 Milvus）。

**待办（接手后按序做）**：
1. **I5 评测集**：18 类 × 30 条 + 开放式 50 + 非法 30（≈620 条，字段见 `evals/README.md`），跑意图 acc≥90%（NFR-R01）、路由一致率≥85%；
2. **ACC-001~035 全量回归**并出报告（对照需求文档第 16 章）；
3. 未做项提醒：rerank 默认关（配置开关）；langchain/transformers 版本已锁定勿随意升级；知识库扩量 = 加 PDF → `build_knowledge_base.py` → `ingest_docs.py`。

## 8. 一句话风格备忘

回复用户用中文；按迭代交付且每步给实测证据；文档改完同步 README；别引入合规类新需求（用户明确规避）。

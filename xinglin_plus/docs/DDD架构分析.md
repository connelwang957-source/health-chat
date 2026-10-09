# DDD 架构分析

本文对应《项目开发指导》§2 的论证：**为什么这个项目用「分层 + 端口-适配器」，
而不是 MVC，也不是完整 DDD**，以及三条必须守住的边界。

---

## 一、三个候选，各解决什么问题

| | MVC | DDD（战术） | 分层 + 端口适配器（本项目） |
|---|---|---|---|
| 解决的问题 | 组织**展示/UI** | **建模领域逻辑** | 隔离**领域能力**与**技术细节** |
| 复杂度位置 | 视图交互、请求流转 | 业务规则、领域对象 | 业务规则 + 外部依赖隔离 |
| Model 形态 | 贫血模型 | 充血模型 | 读模型 + 领域服务 |
| 典型场景 | 表单 CRUD、后台管理 | 有不变量的写系统 | 纯查询系统 |

### 为什么不是 MVC

1. **本项目的接口层已经薄到不需要 View/Controller**：`web.py` 只有两个端点
   （`/v1/chat`、`/health`），`cli.py` 只是一个交互循环——没有视图模板、没有复杂页面流转，
   MVC 要解决的「视图组织」问题在这里几乎不存在。
2. **真正的复杂度全在领域层**：`nl2cypher.py` 的「生成 → 校验 → 执行 → 格式化」、
   `validators.py` 的破坏性关键字拦截、`fact_guardrail.py` 的事实核查、
   `vectorstore.py` 的稠密 + 稀疏融合。硬套 MVC 会把它们塞进上帝 Controller 或贫血 Model。
3. **三个外部依赖需要隔离**：Neo4j + Milvus + DeepSeek。端口-适配器把它们关进基础设施层，
   领域层一行 SDK 都不碰；MVC 没有依赖倒置机制，换供应商要改一堆文件。

### 为什么不是完整 DDD

**本项目是纯查询系统**：没有状态变化、没有业务不变量、没有写操作副作用链。
因此它**不需要**聚合、实体（充血）、领域事件、仓储——那是写系统的工具。

`Answer` 必须叫**读模型**，不是聚合根：

| 聚合根的特征 | 本项目的 `Answer` |
|---|---|
| 有身份标识，可按 id 加载 | ❌ 每次问答现造现丢，无 id |
| 是事务 / 持久化单元 | ❌ 无写操作、无仓储、无事务 |
| 唯一入口 + 封装内部成员 | ❌ `sources` 是普通列表 |
| 守护不变式 | ⚠️ 有隐性约定（来源必须标注、可靠性由来源推导），但没有专门的守卫 |

真要上完整 DDD，得先出现**有状态变化的写功能**（用户、问诊记录、随访），
那时再新建限界上下文即可，**现有查询侧不用动**。

---

## 二、必须守住的三条边界（文档 §2.6）

### 1. 依赖方向只能自上而下

```text
interfaces  →  application  →  domain  ←  infrastructure
```

- `domain` 永远不能 import `application` / `interfaces` / `infrastructure`；
- `application` 不能 import `interfaces`；
- `application` 里**只有 `runtime.py`** 可以 import `infrastructure`（它是组合根）。

**落点**：`tests/test_architecture.py` 用 AST 静态分析固化。一旦误加反向 import，测试立刻失败。

### 2. 「编排」进 application，「能力」进 domain

- `hybrid_agent` 做的是编排（先查什么、怎么融合、失败怎么兜底）→ **application**
- 检索、NL2Cypher、事实护栏是领域能力 → **domain**
- 判断标准：**这段逻辑是"可复用的业务能力"，还是"某个产品的一次性流程"？**
  典型的对照是 `NL2Cypher`（domain，被三个 Agent 复用）vs `NL2CypherAgent`
  （application，只负责"主路径 + 兜底"这一个产品决策）。

> 哪天你想在 domain 里写「先查图谱再查向量」这种 if-else 流程，就是在往 domain 塞编排，要拉回 application。

### 3. 数据 / 资源归领域层所有

`medical.json`、`data/pdfs`、`dict/*.txt`、Milvus 集合 这些**不是代码模块**（不能被 import），
而是「数据 / 资源层」，由 `domain/rag`、`domain/graph` 读写；
`interfaces` 层**绝对不能**直接 open 这些文件。

**落点**：`tests/test_architecture.py::test_interfaces_never_touch_data_resources`。

---

## 三、依赖倒置怎么落地

以 LLM 为例：

```python
# domain/ports.py —— 领域自己定义抽象（Protocol，隐式抽象，不强制继承）
class LLM(Protocol):
    def complete(self, system: str, user: str, temperature: float = 0.0,
                 max_tokens: int = 2048) -> str: ...

# domain/services/intent_service.py —— 只依赖抽象
class IntentService:
    def __init__(self, llm: LLM | None = None, recognizer: EntityRecognizer | None = None): ...

# infrastructure/llm.py —— 基础设施反向实现
class OpenAILlm(LLM):
    def complete(self, system, user, temperature=0.0, max_tokens=2048) -> str: ...

# application/runtime.py —— 组合根把两者接起来
def get_intent_service() -> IntentService:
    return IntentService(get_llm(), get_dictionary())
```

依赖箭头由「领域 → 具体 SDK」**倒置**为「具体 SDK → 领域」。
所以领域层可以在**没有网络、没有数据库**的情况下被完整测试
（`tests/test_ports.py` + `conftest.py` 的替身就是证明）。

### 为什么用 `Protocol` 而不是 `ABC + @abstractmethod`

- **结构化类型（鸭子类型）**：适配器不必显式继承，Python 也不在实例化时报错；
  好处是适配器可以是对第三方 SDK 的薄包装；
- **代价**：契约只能靠约定和测试保证——所以有 `tests/test_ports.py` 做结构一致性检查。

---

## 四、四种架构范式的落点

| 范式 | 在本项目的体现 |
|---|---|
| 分层架构（Layered） | interfaces → application → domain ← infrastructure |
| Clean 架构（依赖倒置） | `domain/ports.py` 定义抽象，`infrastructure/` 反向实现 |
| 六边形（Ports & Adapters） | 端口 = 领域所需能力；适配器 = Neo4j / Milvus / Redis / DeepSeek |
| ReAct（Agent 范式） | `application/tool_agent.py`：LLM 自主决定调哪个工具、调几次 |

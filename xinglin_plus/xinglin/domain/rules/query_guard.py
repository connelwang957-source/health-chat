"""第 12.7 条业务规则：非法查询拦截（纯函数，无 I/O）。

问答链路是**只读**的，任何企图改数据、绕过查询边界、注入式探测的输入
一律前置拒绝，不进入后续任何环节。

真正的安全不止这一层（见需求第 13 章），完整防线是四道：
    ① 本规则（输入拦截）→ ② Neo4j 只读会话 → ③ Cypher 全参数化
    → ④ NL2Cypher 的只读校验器（白名单 + 黑名单 + 单语句 + LIMIT + EXPLAIN）
"""

# 数据破坏、注入与越权特征（匹配前统一转小写）。
#
# ⚠ 中文自然语言必须单列——实测「帮我往数据库里插入一条假疾病记录」「把图谱里所有
# 疾病节点删掉」原来全部漏网（只覆盖了 SQL/Cypher 的英文写法），于是非法请求一路
# 走到检索 + LLM，靠模型"自觉"拒绝。
ILLEGAL_PATTERNS: tuple[str, ...] = (
    # 写 / 删：SQL 与 Cypher 的英文写法
    "drop table", "drop database", "drop all", "delete from", "truncate",
    "update set", "insert into", "create user", "grant ", "revoke ",
    "shutdown", "detach delete", "delete ", "merge (", "create (",
    "call apoc", "call dbms",
    # 写 / 删：中文自然语言
    "插入", "删掉", "删除", "清空", "新建", "建表", "新表", "创建", "改数据",
    "修改数据", "写库", "写入数据库", "篡改", "伪造",
    # 注入探测
    "union select", "or 1=1", "1=1 --", "' or '", "\"; --", "sleep(",
    # 越权读取 / 敏感信息索取（13.3 / 13.4）
    "dbms.", "apoc.", "load csv", "show users", "show databases",
    "密码", "密钥", "api key", "环境变量", "堆栈",
)


def is_illegal_query(text: str) -> bool:
    """是否为非法/危险查询（命中即拒绝，12.7 / G-09）。"""
    lowered = (text or "").lower()
    return any(p in lowered for p in ILLEGAL_PATTERNS)


# 拒绝话术（唯一一份，避免多处漂移）。
# 措辞刻意克制：说明只做只读健康咨询，但**不透露**任何内部实现细节（ACC-031）。
ILLEGAL_REPLY = (
    "抱歉，这个请求我不能执行：本系统只提供健康知识咨询，无法对知识库做任何修改，"
    "也不支持越权访问。如果您有健康方面的问题，欢迎直接提问。"
)


__all__ = ["ILLEGAL_PATTERNS", "is_illegal_query", "ILLEGAL_REPLY"]

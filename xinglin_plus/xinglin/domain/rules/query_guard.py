"""第 12.7 条业务规则：非法查询拦截（纯函数，无 I/O）。

问答链路是**只读**的，任何企图改数据、绕过查询边界、注入式探测的输入
一律前置拒绝，不进入后续任何环节。

真正的安全不止这一层（见需求第 13 章），完整防线是四道：
    ① 本规则（输入拦截）→ ② Neo4j 只读会话 → ③ Cypher 全参数化
    → ④ NL2Cypher 的只读校验器（白名单 + 黑名单 + 单语句 + LIMIT + EXPLAIN）
"""

# 数据破坏与注入特征
ILLEGAL_PATTERNS: tuple[str, ...] = (
    # 写 / 删
    "drop table", "drop database", "delete from", "truncate", "update set",
    "insert into", "create user", "grant ", "revoke ",
    "删库", "删表", "删除数据", "清空数据", "drop all", "shutdown",
    # 注入探测
    "union select", "or 1=1", "1=1 --", "' or '", "\"; --", "sleep(",
    # 越权读取
    "dbms.", "apoc.", "load csv", "show users", "show databases",
)


def is_illegal_query(text: str) -> bool:
    """是否为非法/危险查询（命中即拒绝，12.7 / G-09）。"""
    lowered = (text or "").lower()
    return any(p in lowered for p in ILLEGAL_PATTERNS)


__all__ = ["ILLEGAL_PATTERNS", "is_illegal_query"]

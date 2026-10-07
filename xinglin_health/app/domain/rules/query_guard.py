"""第 12.7 / G-09 条规则：非法查询拦截（纯函数）。

问答场景只读（13.2），任何试图修改/破坏系统数据或注入语句的问题一律拒绝。
"""

ILLEGAL_PATTERNS = (
    "drop table", "delete from", "insert into", "update set", "union select",
    "删库", "删表", "删除所有", "删除数据", "修改数据库", "注入", "拖库",
    "truncate", "; --", "or 1=1", "drop database",
)


def is_illegal_query(question: str) -> bool:
    q = (question or "").lower()
    return any(p in q for p in ILLEGAL_PATTERNS)

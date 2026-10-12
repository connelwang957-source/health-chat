"""NL2Cypher 提示词（对应《项目开发指导》§5.3 的 `xinglin/domain/graph/prompts.py`）。

提示词里把三件事讲死，配合 `validators.CypherValidator` 形成"宽进严出"：

1. **只读**：只允许 MATCH/OPTIONAL MATCH/WITH/UNWIND/RETURN 起头的查询；
2. **参数化**：实体值一律用 ``$entity``，不得把用户输入拼进语句（防注入，13.1/13.2）；
3. **结构化输出**：先给 ``ENTITY:`` 再给 ``CYPHER:``，便于程序解析与参数绑定。
"""

READONLY_RULES = """硬性约束（违反则整条语句作废）：
1. 只能生成只读查询：允许 MATCH / OPTIONAL MATCH / WITH / UNWIND / RETURN；
2. 禁止 CREATE / MERGE / SET / DELETE / REMOVE / DROP / CALL apoc.* / LOAD CSV 等任何写入或越权操作；
3. 实体值**必须**用参数 $entity 绑定，禁止把实体名直接写进语句；
4. 只能出现下面 schema 中列出的标签、关系与属性，不得臆造；
5. 只输出**一条**语句，不要分号，不要多段查询；
6. 末尾加 LIMIT（不超过 20），避免大结果集；
7. **严格区分属性与关系**：节点自身的字段写成 `n.属性名`（如 `d.cure_way`、`d.desc`），
   关系必须写成 `-[:关系名]->`（如 `-[:recommand_drug]->`）；
   绝不能把属性当关系用——例如 `-[:cure_way]->` 是**错误**的（cure_way 是属性），
   这样做会查空并触发数据库告警；关系名只能取自上面 schema 的"关系"清单。"""

OUTPUT_FORMAT = """输出格式（严格两段，不要解释、不要 markdown 代码块）：

ENTITY: <从问题中识别出的实体名；识别不到就写 无>
CYPHER: <一条只读 Cypher 语句>"""


def create_system_prompt(schema_text: str) -> str:
    """组装系统提示词（带图谱 schema）。"""
    return (
        "你是医学知识图谱的查询生成器，把用户的自然语言问题转成一条合法的 Cypher 只读查询。\n\n"
        f"{READONLY_RULES}\n\n"
        f"图谱 schema：\n{schema_text}\n\n"
        f"{OUTPUT_FORMAT}"
    )


def create_user_prompt(natural_language: str) -> str:
    """组装用户提示词。"""
    return f"用户问题：{natural_language}\n请按格式输出 ENTITY 与 CYPHER。"


__all__ = ["READONLY_RULES", "OUTPUT_FORMAT", "create_system_prompt", "create_user_prompt"]

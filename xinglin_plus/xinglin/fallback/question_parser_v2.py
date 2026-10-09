"""规则拼 Cypher（第 1 代兜底链，对应文档的 `question_parser_v2.sql_transfer`）。

**零 LLM**：按 `QAType` 元数据拼出参数化 Cypher。它不自己维护一套模板，
而是直接复用 `domain/services/kg_query_service.build_cypher` ——
这样"模板怎么拼"全项目只有一份实现，规则链与生产主路径不会漂移。

被 `robot_qwen.RobotQwen.chat_main` 在"词典识别出实体 + 规则判定出类型"之后调用。
"""

from xinglin.domain.services import build_cypher
from xinglin.domain.values import QAType


def sql_transfer(question_type: QAType, entity: str) -> tuple[str, dict]:
    """``(问答类型, 实体)`` → ``(参数化 Cypher, 参数)``。

    实体值一律走 ``$entity`` 绑定，绝不拼进语句（13.1/13.2 防注入）。
    """
    if question_type is None or not entity:
        raise ValueError("缺少问答类型或实体，无法拼写查询")
    return build_cypher(question_type), {"entity": entity}


__all__ = ["sql_transfer"]

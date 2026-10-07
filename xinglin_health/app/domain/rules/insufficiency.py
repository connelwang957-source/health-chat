"""第 10.3 条业务规则：信息不足规则（纯函数）。

当系统无法从已有信息中获得足够依据时：
不虚构事实、不将推测表达为确定事实、明确说明信息不足、必要时提示咨询专业医生。
"""

INSUFFICIENT_ANSWER = (
    "抱歉，当前健康知识库中没有找到与您的问题直接对应的信息，"
    "无法给出有依据的回答。为避免误导，我不能凭空推测。"
    "建议您进一步咨询专业医生或补充问题细节后再试。"
)

EMPTY_RESULT_HINT = "知识库中未检索到「{entity}」相关的「{aspect}」信息。"


def is_insufficient(fact_count: int, doc_count: int) -> bool:
    """检索结果是否不足以支撑回答。"""
    return fact_count == 0 and doc_count == 0


def insufficient_reason(entity: str | None, qa_type_name: str | None) -> str:
    return EMPTY_RESULT_HINT.format(entity=entity or "该问题", aspect=qa_type_name or "所问内容")

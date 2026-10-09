"""第 10.3 条业务规则：信息不足时的处理（纯函数，无 I/O）。

系统拿不到足够依据时必须：不虚构事实、不把推测表述成确定事实、
明确说明信息不足、必要时提示咨询专业医生。

话术只有一处常量（兜底路径直接使用），避免多份话术漂移。
"""

INSUFFICIENT_ANSWER = (
    "抱歉，当前健康知识库中没有找到与您的问题直接对应的信息，"
    "无法给出有依据的回答。为避免误导，我不能凭空推测。"
    "建议您进一步咨询专业医生或补充问题细节后再试。"
)


def is_insufficient(fact_count: int, doc_count: int) -> bool:
    """检索结果是否不足以支撑回答（两条来源都是 0 才算不足）。"""
    return fact_count == 0 and doc_count == 0


__all__ = ["INSUFFICIENT_ANSWER", "is_insufficient"]

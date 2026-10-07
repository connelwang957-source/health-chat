"""第 10.4 条业务规则：健康风险提示规则（纯函数）。

系统属于健康咨询工具：涉及诊断、治疗方案、药品使用等可能影响实际健康决策的问题，
不得以医生诊断结论的形式回答，并须附加风险提示。
"""

RISK_PATTERNS = (
    "确诊", "诊断我是", "我得了什么病", "治疗方案", "剂量", "用量", "处方",
    "怎么治", "如何治疗", "吃什么药", "用什么药", "服药", "输液", "手术",
)

RISK_NOTICE_TEXT = (
    "以上内容为健康信息参考，不构成医学诊断或治疗建议；"
    "具体诊疗与用药请务必遵医嘱。"
)


def needs_risk_notice(question: str, answer: str) -> bool:
    """涉及诊疗决策内容时，回答必须附加风险提示。"""
    return any(w in (question or "") for w in RISK_PATTERNS)


def build_risk_notice() -> str:
    return RISK_NOTICE_TEXT

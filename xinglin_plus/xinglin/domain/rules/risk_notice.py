"""第 10.4 条业务规则：健康风险提示（纯函数，无 I/O）。

工具定位是**信息咨询而非诊疗**：当问题或回答触及诊疗边界
（怎么治、吃什么药、剂量、确诊、手术等）时，回答必须附一段健康边界提示，
避免用户把科普信息当作诊断结论使用。
"""

RISK_NOTICE = (
    "以上内容为一般性健康信息参考，不构成医学诊断或治疗建议。"
    "具体病情、用药与诊疗方案请咨询执业医师，遵医嘱执行。"
)

# 触及诊疗边界的表述
TREATMENT_HINTS: tuple[str, ...] = (
    "怎么治", "如何治", "治疗", "用药", "吃什么药", "吃啥药", "服药", "剂量", "几片",
    "手术", "要不要手术", "多久能好", "能不能治好", "确诊", "是不是得", "严重吗",
    "挂什么科", "吃什么能好", "偏方", "停药",
)


def needs_risk_notice(question: str, answer: str = "") -> bool:
    """问题或回答是否触及诊疗边界（需要附风险提示）。"""
    text = f"{question or ''}\n{answer or ''}"
    return any(w in text for w in TREATMENT_HINTS)


def build_risk_notice() -> str:
    return RISK_NOTICE


__all__ = ["RISK_NOTICE", "TREATMENT_HINTS", "needs_risk_notice", "build_risk_notice"]

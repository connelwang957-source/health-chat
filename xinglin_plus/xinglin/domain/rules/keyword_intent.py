"""共享关键词表：问题表述 → `QAType`（纯函数，无 I/O）。

**只有这一张表**，两个"规则通道"共用，避免两套规则各自演化后漂移：

    ① 意图识别的 LLM 降级通道（LLM 不可用/失败时兜底）；
    ② `fallback` 第 1 代规则链（`question_classifier_v2`）。

注意本表只做"关键词 → 类型"的裸匹配，**不含实体角色**；
「阿莫西林治疗哪些疾病」（药品端）与「咳嗽可能是什么病」（症状端）的区别
由角色优先逻辑处理（见 `question_classifier_v2.classify`）。
"""

from xinglin.domain.values import QAType

KEYWORD_RULES: tuple[tuple[tuple[str, ...], QAType], ...] = (
    # ---- 疾病端 ----
    (("症状", "表现", "有哪些表现"), QAType.DISEASE_SYMPTOM),
    (("并发症", "并发", "会引起什么"), QAType.DISEASE_COMPLICATION),
    (("病因", "原因", "怎么引起", "为什么会得"), QAType.DISEASE_CAUSE),
    (("预防", "怎么防", "如何预防", "怎么避免"), QAType.DISEASE_PREVENT),
    (("治疗周期", "多久能好", "多长时间能好"), QAType.DISEASE_TREAT_PERIOD),
    (("怎么治", "如何治", "治疗方法", "怎么治疗"), QAType.DISEASE_TREAT_METHOD),
    (("治好", "治愈", "治愈率", "能治好吗"), QAType.DISEASE_CURE),
    (("易感", "哪些人容易", "什么人群", "好发人群"), QAType.DISEASE_SUSCEPTIBLE),
    (("是什么病", "介绍", "简介", "概述", "是什么"), QAType.DISEASE_DESC),
    (("忌吃", "不能吃", "不宜吃", "忌口", "不能吃什么"), QAType.DISEASE_FOOD_AVOID),
    (("宜吃", "吃什么好", "适合吃", "推荐吃", "应该吃什么"), QAType.DISEASE_FOOD_RECOMMEND),
    (("吃什么药", "用药", "药品", "药物"), QAType.DISEASE_DRUG),
    (("做什么检查", "检查项目", "需要查", "要查什么"), QAType.DISEASE_EXAM),
    # ---- 非疾病端（反向）----
    (("哪些疾病", "什么病", "可能是什么病", "对应哪些"), QAType.SYMPTOM_DISEASE),
)


def match_keyword(question: str) -> tuple[QAType, str] | None:
    """按表顺序匹配，返回第一个命中的 ``(类型, 命中词)``；未命中返回 None。"""
    q = question or ""
    for keywords, qa_type in KEYWORD_RULES:
        for word in keywords:
            if word in q:
                return qa_type, word
    return None


__all__ = ["KEYWORD_RULES", "match_keyword"]

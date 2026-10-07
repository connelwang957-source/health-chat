"""第 10.1 条业务规则：宜吃与忌吃判断（纯函数，零外部依赖）。

当用户询问疾病与食品之间的关系时：
- 明确表达限制含义 → 限制类查询（疾病—忌吃食品 / 食品—疾病（限制））
- 未表达限制含义   → 推荐类查询（疾病—宜吃食品 / 食品—疾病（推荐））
"""

RESTRICT_WORDS = ("不能吃", "不要吃", "忌吃", "忌口", "不可以吃", "不适合吃", "避免", "禁食", "少吃")
RECOMMEND_WORDS = ("吃什么好", "适合吃", "推荐", "宜吃", "可以吃什么", "吃点什么", "多吃")

DIRECTION_RESTRICT = "restrict"
DIRECTION_RECOMMEND = "recommend"


def judge_diet_direction(question: str) -> str:
    """判定饮食咨询方向。10.1.2：未表达限制含义时，理解为推荐食品查询。"""
    q = question or ""
    if any(w in q for w in RESTRICT_WORDS):
        return DIRECTION_RESTRICT
    return DIRECTION_RECOMMEND


def adjust_food_qa_type(question: str, qa_type):
    """当意图判定落在疾病-食品关系上时，按 10.1 规则校正忌吃/宜吃方向。

    qa_type 必须是 QAType.food_types() 之一，否则原样返回。
    """
    from app.domain.values import QAType

    if qa_type not in QAType.food_types():
        return qa_type
    direction = judge_diet_direction(question)
    if direction == DIRECTION_RESTRICT:
        return (QAType.DISEASE_FOOD_AVOID if qa_type in (QAType.DISEASE_FOOD_RECOMMEND, QAType.DISEASE_FOOD_AVOID)
                else QAType.FOOD_DISEASE_AVOID)
    return (QAType.DISEASE_FOOD_RECOMMEND if qa_type in (QAType.DISEASE_FOOD_AVOID, QAType.DISEASE_FOOD_RECOMMEND)
            else QAType.FOOD_DISEASE_RECOMMEND)

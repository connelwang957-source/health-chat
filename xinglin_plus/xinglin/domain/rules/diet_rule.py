"""第 10.1 条业务规则：疾病—食品的宜忌方向判定（纯函数，无 I/O）。

同一句「XX 能吃吗」在**疾病端**和**食品端**含义完全不同，必须先判方向再选查询：

    疾病端：「感冒不能吃什么」 → 疾病—忌吃食品（DISEASE_FOOD_AVOID）
    食品端：「螃蟹不能吃吗」   → 食品—疾病（限制）（FOOD_DISEASE_AVOID）

判定依据：问题里是否出现限制性表述（不能/不宜/忌/避免…）。

对应需求 FR-016 与第 10.1 条；`QAType.food_types()` 给出受本规则影响的 4 个类型。
"""

from xinglin.domain.values import QAType

DIRECTION_RESTRICT = "restrict"      # 限制 / 忌口
DIRECTION_RECOMMEND = "recommend"    # 推荐 / 宜吃

# 限制性表述（命中任一即视为"限制"方向）
RESTRICT_WORDS: tuple[str, ...] = (
    "不能", "不可以", "不宜", "不适合", "不适宜", "忌", "禁", "避免",
    "少吃", "别吃", "不要吃", "不能吃", "能吃吗", "可以吃吗", "有没有害",
)


def judge_diet_direction(question: str) -> str:
    """判定问题表达的饮食方向。"""
    q = question or ""
    return DIRECTION_RESTRICT if any(w in q for w in RESTRICT_WORDS) \
        else DIRECTION_RECOMMEND


def adjust_food_qa_type(question: str, qa_type: QAType | None) -> QAType | None:
    """按问题实际方向校正 4 个食品类 QAType；非食品类原样返回。

    LLM 或关键词规则可能把「螃蟹不能吃吗」判成 FOOD_DISEASE_RECOMMEND，
    这里按问题中的方向词再纠一次，保证 FR-016 达标。
    """
    if qa_type is None or qa_type not in QAType.food_types():
        return qa_type
    restrict = judge_diet_direction(question) == DIRECTION_RESTRICT
    if qa_type in (QAType.DISEASE_FOOD_AVOID, QAType.DISEASE_FOOD_RECOMMEND):
        return QAType.DISEASE_FOOD_AVOID if restrict else QAType.DISEASE_FOOD_RECOMMEND
    return QAType.FOOD_DISEASE_AVOID if restrict else QAType.FOOD_DISEASE_RECOMMEND


__all__ = ["DIRECTION_RESTRICT", "DIRECTION_RECOMMEND", "RESTRICT_WORDS",
           "judge_diet_direction", "adjust_food_qa_type"]

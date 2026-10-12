"""IntentService：FR-002/FR-003 问题理解与分类（domain 领域服务）。

两条通道，先 LLM 后规则：

1. **LLM 通道**：把固定问答类型编号表交给大模型，要求它只回一个 JSON；
2. **规则通道**（LLM 不可用 / 失败时）：共享关键词表 + 第 10.2 条默认规则。

实体识别**只有一个口径**：`EntityRecognizer` 端口（词典最长匹配，组合根注入），
避免"启发式抽取"与"词典匹配"两套结果打架。
"""

import json

from pydantic import BaseModel

from xinglin.domain.entities import Intent
from xinglin.domain.ports import EntityRecognizer, LLM
from xinglin.domain.rules import (
    adjust_food_qa_type,
    default_qa_type,
    is_open_ended,
    match_keyword,
)
from xinglin.domain.values import EntityRole, QAType

# 交给 LLM 的固定问答类型编号表（第 9 章 18 类 + 需求 14.7 的科室 2 类）
QA_TYPE_LIST = "\n".join(f"{t.code}. {t.cn_name} —— {t.intent}" for t in QAType)

INTENT_SYSTEM_PROMPT = (
    "你是健康问答系统的意图识别模块。请判断用户问题涉及的健康对象与意图类型，"
    "并且**只输出一个 JSON 对象**，不要任何解释、不要 markdown 代码块。\n\n"
    f"固定问答类型编号表（qa_type_code 取其中之一；无法归入则填 null）：\n{QA_TYPE_LIST}\n\n"
    "JSON 字段：\n"
    '  "entity": 问题中的核心健康对象名（疾病/症状/药品/食品/检查/科室名），没有则 null\n'
    '  "entity_type": 该对象类型，取「疾病/症状/药品/食品/检查/科室」，不确定则 null\n'
    '  "qa_type_code": 上述编号（整数）或 null\n'
    '  "open_ended": 是否属于开放式问题（无法归入固定类型时为 true）'
)


class IntentOut(BaseModel):
    """LLM 结构化输出的意图模型。"""
    entity: str | None = None
    entity_type: str | None = None      # 疾病/症状/药品/食品/检查/科室/None
    qa_type_code: int | None = None     # 1-20；开放式为 null
    open_ended: bool = False


def parse_intent_json(raw: str) -> IntentOut:
    """从 LLM 输出里抠出 JSON（容忍代码块包裹与多余文字）。"""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("LLM 未返回 JSON")
    return IntentOut(**json.loads(text[start:end + 1]))


class IntentService:
    """问题理解与分类。"""

    def __init__(self, llm: LLM | None = None,
                 recognizer: EntityRecognizer | None = None):
        self._llm = llm
        self._recognizer = recognizer

    # -- public -------------------------------------------------------------
    def classify(self, question: str) -> Intent:
        if self._llm is not None and getattr(self._llm, "available", False):
            try:
                return self._classify_by_llm(question)
            except Exception:      # noqa: BLE001 —— LLM 异常不阻断问答，走规则降级
                pass
        return self._classify_by_rules(question)

    # -- LLM 通道 -----------------------------------------------------------
    def _classify_by_llm(self, question: str) -> Intent:
        out = parse_intent_json(
            self._llm.complete(INTENT_SYSTEM_PROMPT, f"用户问题：{question}",
                               temperature=0.0, max_tokens=512))
        qa_type = QAType.by_code(out.qa_type_code)
        qa_type = adjust_food_qa_type(question, qa_type)          # 10.1 宜忌校正
        if qa_type is None and not out.open_ended:
            qa_type = default_qa_type(question, out.entity_type)  # 10.2 默认规则
        # 开放式信号（进展 / 因果 / 对比）优先：即便模型归了编号，也应由文献路作答（FR-024）。
        # 注意**不**把 qa_type is None 也算作开放式——寒暄（"你好"）同样没有 qa_type，
        # 但它不需要检索，应留给路由判定为 direct。
        open_ended = out.open_ended or is_open_ended(question)
        return Intent(entity=out.entity, entity_type=out.entity_type, qa_type=qa_type,
                      open_ended=open_ended,
                      confidence=0.85, decided_by="llm")

    # -- 规则通道 ------------------------------------------------------------
    def _classify_by_rules(self, question: str) -> Intent:
        q = question or ""
        entity, entity_type = self._recognize(q)

        # 开放式问题优先（FR-024）：关键词命中也不该"抢走"进展 / 因果 / 对比类提问，
        # 否则会出现"明明有相关文献却答依据不足"
        if is_open_ended(q):
            return Intent(entity=entity, entity_type=entity_type, open_ended=True,
                          confidence=0.5, decided_by="rule",
                          reason="开放式提问（进展/因果/对比），转文献或多路召回")

        # 科室锚点：问的就是"这个科室治哪些病"（需求 14.7）。
        # 必须早于关键词表——否则「泌尿内科看哪些疾病」会被泛化的「哪些疾病」
        # 匹配成"症状—疾病"，把科室当症状去查。
        if entity_type == EntityRole.DEPARTMENT.value:
            return Intent(entity=entity, entity_type=entity_type,
                          qa_type=QAType.DEPARTMENT_DISEASE, open_ended=False,
                          confidence=0.6, decided_by="rule",
                          reason="实体角色为科室，按「科室—疾病」查询")

        if (matched := match_keyword(q)) is not None:
            qa_type, word = matched
            qa_type = adjust_food_qa_type(q, qa_type)
            return Intent(entity=entity,
                          entity_type=entity_type or qa_type.source_role.value,
                          qa_type=qa_type, open_ended=False,
                          confidence=0.6, decided_by="rule",
                          reason=f"命中关键词「{word}」")

        dt = default_qa_type(q, entity_type)                      # 10.2 默认规则
        if dt is not None:
            return Intent(entity=entity, entity_type=entity_type or dt.source_role.value,
                          qa_type=dt, open_ended=False, confidence=0.4,
                          decided_by="rule", reason="10.2 默认意图规则")

        return Intent(entity=entity, entity_type=entity_type,
                      open_ended=is_open_ended(q), confidence=0.3, decided_by="rule",
                      reason="未命中固定类型，交由路由按开放程度决定是否检索")

    def _recognize(self, question: str) -> tuple[str | None, str | None]:
        """词典实体识别（唯一口径）：返回 ``(实体, 中文角色)``。"""
        if self._recognizer is None or not getattr(self._recognizer, "available", False):
            return None, None
        found = self._recognizer.find_entity(question)
        if not found:
            return None, None
        entity, label = found
        role = EntityRole.from_node_label(label)          # 图谱标签 → 中文业务名
        return entity, (role.value if role else None)


__all__ = ["IntentService", "IntentOut", "QA_TYPE_LIST",
           "INTENT_SYSTEM_PROMPT", "parse_intent_json"]

"""IntentService：FR-002/FR-003 问题理解与分类。

优先 LLM 结构化输出（with_structured_output）；LLM 不可用或失败时，
回退关键词规则 + 第 10.2 条默认意图规则（同时是 LLM 故障时的降级通道，FR-026）。
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from app.domain.entities import Intent
from app.domain.rules import default_qa_type, adjust_food_qa_type
from app.domain.values import QAType

QA_TYPE_LIST = "\n".join(f"{t.code}. {t.cn_name}" for t in QAType)

# 关键词规则（LLM 不可用时的兜底，顺序即优先级）
KEYWORD_RULES: list[tuple[tuple[str, ...], QAType]] = [
    (("有什么症状", "哪些症状", "症状是什么", "症状有哪些"), QAType.DISEASE_SYMPTOM),
    (("主要治疗什么疾病", "治疗哪些疾病", "用于哪些疾病", "治什么的"), QAType.DRUG_DISEASE),
    (("常用什么药", "用什么药", "吃什么药", "相关药品", "用什么药品"), QAType.DISEASE_DRUG),
    (("可能是什么疾病", "什么病", "对应哪些疾病", "可能是什么病"), QAType.SYMPTOM_DISEASE),
    (("病因", "为什么得", "为什么会得", "是什么引起的"), QAType.DISEASE_CAUSE),
    (("怎么预防", "如何预防", "怎样预防"), QAType.DISEASE_PREVENT),
    (("治疗周期", "多久能好", "多长时间能治好", "治疗需要多久"), QAType.DISEASE_TREAT_PERIOD),
    (("怎么治疗", "如何治疗", "治疗方法", "怎样治疗"), QAType.DISEASE_TREAT_METHOD),
    (("治愈", "能不能治好", "治愈率", "能治好吗"), QAType.DISEASE_CURE),
    (("易感", "高发人群", "哪些人容易"), QAType.DISEASE_SUSCEPTIBLE),
    (("并发症",), QAType.DISEASE_COMPLICATION),
    (("不能吃", "忌吃", "忌口", "不可以吃", "不适合吃", "哪些食物要避免"), QAType.DISEASE_FOOD_AVOID),
    (("适合吃什么", "宜吃", "推荐吃什么", "吃什么好", "适合吃"), QAType.DISEASE_FOOD_RECOMMEND),
    (("做什么检查", "哪些检查", "检查项目"), QAType.DISEASE_EXAM),
]

STOPWORDS = ("请问", "我想知道", "帮我查", "查一下", "一下", "请问一下", "你好", "谢谢")


class IntentOut(BaseModel):
    """LLM 结构化输出的意图模型。"""
    entity: str | None = None
    entity_type: str | None = None      # 疾病/症状/药品/食品/检查/None
    qa_type_code: int | None = None     # 1-18，开放式为 null
    open_ended: bool = False


class IntentService:
    def __init__(self, llm_gateway=None):
        # llm_gateway: infrastructure.llm.gateway.LLMGateway（可为 None，纯规则运行）
        self._llm = llm_gateway

    # -- public ------------------------------------------------------------
    def classify(self, question: str) -> Intent:
        if self._llm is not None and self._llm.available:
            try:
                return self._classify_by_llm(question)
            except Exception:  # LLM 异常不阻断问答，走规则降级
                pass
        return self._classify_by_rules(question)

    # -- LLM 通道 -----------------------------------------------------------
    def _classify_by_llm(self, question: str) -> Intent:
        prompt = (
            "你是健康问答系统的意图识别模块。判断问题涉及的健康对象与意图类型。\n"
            f"固定问答类型编号表：\n{QA_TYPE_LIST}\n"
            "若问题无法归入以上类型，则 qa_type_code=null 且 open_ended=true。\n"
            "entity 为问题中的核心健康对象名称（如疾病/症状/药品/食品/检查名），没有则 null。"
        )
        out: IntentOut = self._llm.structured(prompt, question, IntentOut)
        qa_type = QAType.by_code(out.qa_type_code)
        qa_type = adjust_food_qa_type(question, qa_type)  # 10.1 宜忌校正
        if qa_type is None and not out.open_ended:
            qa_type = default_qa_type(question, out.entity_type)  # 10.2 默认规则
        return Intent(
            entity=out.entity, entity_type=out.entity_type, qa_type=qa_type,
            open_ended=out.open_ended or qa_type is None,
            confidence=0.85, decided_by="llm",
        )

    # -- 规则通道 ------------------------------------------------------------
    def _classify_by_rules(self, question: str) -> Intent:
        q = question or ""
        for keywords, qa_type in KEYWORD_RULES:
            hit = next((k for k in keywords if k in q), None)
            if hit:
                qa_type = adjust_food_qa_type(q, qa_type)
                return Intent(
                    entity=self._extract_entity(q, hit),
                    entity_type=qa_type.source_role.value,
                    qa_type=qa_type, open_ended=False,
                    confidence=0.6, decided_by="rule",
                    reason=f"命中关键词「{hit}」",
                )
        # 10.2 默认规则
        dt = default_qa_type(q, self._guess_entity_type(q))
        if dt is not None:
            return Intent(entity=self._extract_entity(q, ""), entity_type=dt.source_role.value,
                          qa_type=dt, open_ended=False, confidence=0.4,
                          decided_by="rule", reason="10.2 默认意图规则")
        return Intent(open_ended=True, confidence=0.3, decided_by="rule",
                      reason="未命中固定类型，转开放式问答")

    def _extract_entity(self, question: str, hit: str) -> str | None:
        """规则模式下的朴素实体抽取：去掉停用词与命中的意图短语后取剩余主体。"""
        q = question
        for w in STOPWORDS:
            q = q.replace(w, "")
        if hit:
            q = q.replace(hit, "")
        q = re.sub(r"[的了吗呢吧？?！!。,\s]+", "", q)
        return q[:12] if q else None

    def _guess_entity_type(self, question: str) -> str | None:
        return "症状" if any(w in question for w in ("疼", "痛", "不舒服")) else None

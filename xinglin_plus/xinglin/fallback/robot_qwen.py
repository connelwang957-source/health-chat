"""第 1 代「规则拼 Cypher」流水线（对应文档 `fallback/robot_qwen.py` 的 `xing_lin()`）。

定位：**NL2Cypher 之外的零 LLM 图谱兜底**。当大模型不可用、或生成的语句未通过校验时，
由本流水线接管图谱通路：词典识别实体 → 规则判定类型 → 规则拼 Cypher → 执行 → 模板组织。
全程不调用大模型，因此"模型挂了，图谱能力不挂"。

可选 Qwen 兜底：仅当规则链拿不到答案、且显式开启 `AI_API_CONFIG["enabled"]` 时，
用 LLM 直接作答（默认关闭，避免用错 Key 空转）。
"""

import logging

from pydantic import BaseModel, Field

from xinglin.config import AI_API_CONFIG, DICT_DIR
from xinglin.domain.entities import Fact
from xinglin.domain.ports import GraphStore, LLM

from xinglin.fallback.answer_search_v2 import AnswerSearchV2
from xinglin.fallback.dictionary import MedicalDictionary, load_words
from xinglin.fallback.question_classifier_v2 import classify, preferred_roles
from xinglin.fallback.question_parser_v2 import sql_transfer

logger = logging.getLogger(__name__)

QWEN_SYSTEM_PROMPT = (
    "你是杏林大健康问答系统的兜底回答模块。请用简洁的中文健康信息回答用户问题；"
    "不得给出诊断结论或处方，依据不足时明确说明，并提示遵医嘱。"
)


class FallbackResult(BaseModel):
    """一次规则兜底的结果（可观测：命中实体 / 类型 / 语句 / 事实 / 答案 / 来源）。"""
    question: str
    entity: str | None = None
    entity_role: str | None = None
    qa_type_code: int | None = None
    cypher: str = ""
    params: dict = Field(default_factory=dict)
    facts: list[Fact] = Field(default_factory=list)
    answer: str = ""
    decided_by: str = "none"                # rule | qwen | none
    notes: list[str] = Field(default_factory=list)


class RobotQwen:
    """第 1 代流水线：词典 + 规则 + 模板，全零 LLM；必要时（可配置）由 Qwen 兜底。"""

    def __init__(self, dictionary: MedicalDictionary, graph: GraphStore,
                 llm: LLM | None = None, enable_qwen: bool = False):
        self._dict = dictionary
        self._search = AnswerSearchV2(graph)
        self._llm = llm
        self._enable_qwen = enable_qwen

    @property
    def available(self) -> bool:
        """词典可用即视为可用（未导出词表时整条规则链不可用）。"""
        return self._dict is not None and self._dict.available

    @property
    def qwen_available(self) -> bool:
        return bool(self._enable_qwen and self._llm is not None
                    and getattr(self._llm, "available", False))

    # -- 主流程 -------------------------------------------------------------
    def chat_main(self, question: str) -> FallbackResult:
        result = FallbackResult(question=question)
        if not self.available:
            result.notes.append("医学词典未导出，规则兜底链不可用")
            return result

        # ① 词典识别实体（最长优先；按问题意图先限定角色，避开同名跨角色节点）
        found = None
        if (roles := preferred_roles(question)) is not None:
            found = self._dict.find_entity(question, roles=roles)
        found = found or self._dict.find_entity(question)
        if found is None:
            result.notes.append("词典未匹配到医学实体")
        else:
            result.entity, result.entity_role = found

        # ② 规则判定类型
        denied = self._dict.is_denied(question)
        qa_type = classify(question, result.entity, result.entity_role, denied=denied)
        if qa_type is not None:
            result.qa_type_code = qa_type.code

        # ③ 规则拼 Cypher → 执行
        if qa_type is not None and result.entity:
            cypher, params = sql_transfer(qa_type, result.entity)
            result.cypher, result.params = cypher, params
            try:
                result.facts = self._search.search(cypher, params)
            except Exception as e:      # noqa: BLE001 —— 兜底链失败只降级，不抛
                logger.warning("规则兜底查询失败: %s", e)
                result.notes.append("图谱查询失败，规则兜底未取得事实")

        # ④ 模板组织回答
        if result.facts and qa_type is not None:
            result.answer = self._search.render(result.entity or "", qa_type, result.facts)
            result.decided_by = "rule"
            return result

        # ⑤ 可选 Qwen 兜底（仅显式开启且 LLM 可用）
        if self.qwen_available:
            try:
                result.answer = self._llm.complete(
                    QWEN_SYSTEM_PROMPT, f"用户问题：{question}",
                    temperature=0.3, max_tokens=800).strip()
                result.decided_by = "qwen"
                result.notes.append("规则链未取得答案，已由 Qwen 兜底作答")
                return result
            except Exception as e:      # noqa: BLE001 —— Qwen 失败不阻塞
                logger.warning("Qwen 兜底失败: %s", e)
                result.notes.append("Qwen 兜底调用失败")
        return result


def xing_lin(dictionary: MedicalDictionary | None = None, graph: GraphStore | None = None,
             llm: LLM | None = None, enable_qwen: bool | None = None) -> RobotQwen:
    """工厂函数（保留文档里的名字）：装配第 1 代兜底流水线。

    不传依赖时**自动装配**（读 `dict/*.txt` + 建默认适配器），这是文档里的用法；
    显式传入则完全由调用方控制（便于单测与替换）。
    """
    if dictionary is None:
        dictionary = MedicalDictionary(load_words(DICT_DIR))
    if graph is None:
        from xinglin.infrastructure.graph import Neo4jGraph
        graph = Neo4jGraph()
    if enable_qwen is None:
        enable_qwen = bool(AI_API_CONFIG.get("enabled", False))
    if llm is None and enable_qwen:
        from xinglin.infrastructure.llm import OpenAILlm
        llm = OpenAILlm(api_key=AI_API_CONFIG["api_key"],
                        base_url=AI_API_CONFIG["base_url"],
                        model=AI_API_CONFIG["model"])
    return RobotQwen(dictionary, graph, llm=llm, enable_qwen=enable_qwen)


__all__ = ["RobotQwen", "FallbackResult", "xing_lin", "QWEN_SYSTEM_PROMPT"]

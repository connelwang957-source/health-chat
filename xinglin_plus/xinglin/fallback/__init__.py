"""fallback：第 1 代「规则拼 Cypher」流水线（零 LLM 兜底）。

对应《项目开发指导》的 `fallback/`：当 NL2Cypher 生成失败 / 大模型不可用时，
由本包接管图谱通路，保证"模型挂了，图谱能力不挂"。

    dictionary                8 类医学词典 + 最长匹配实体识别（实现 EntityRecognizer 端口）
    question_classifier_v2    规则判定 QAType（实体角色优先 → 关键词表 → 10.2 默认规则）
    question_parser_v2        sql_transfer：规则拼参数化 Cypher（复用 domain 模板）
    answer_search_v2          执行查询 + 模板化组织回答（复用 domain 话术）
    robot_qwen                编排以上四步（xing_lin 工厂）+ 可选 Qwen 兜底

依赖方向：本包只依赖 `xinglin.domain`（端口 / 值对象 / 规则 / 服务）；
唯一例外是 `xing_lin()` 工厂的**自动装配**（未显式传依赖时才去建默认适配器）。
"""

from xinglin.fallback.answer_search_v2 import AnswerSearchV2
from xinglin.fallback.dictionary import MedicalDictionary, load_words
from xinglin.fallback.question_classifier_v2 import classify, preferred_roles
from xinglin.fallback.question_parser_v2 import sql_transfer
from xinglin.fallback.robot_qwen import FallbackResult, RobotQwen, xing_lin

__all__ = [
    "AnswerSearchV2",
    "MedicalDictionary", "load_words",
    "classify", "preferred_roles",
    "sql_transfer",
    "RobotQwen", "FallbackResult", "xing_lin",
]

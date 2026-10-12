"""把 `evals/dataset/` 里的安全与边界用例**接进 CI**（纯离线，零外部依赖）。

评测集原本要靠真机跑（Neo4j / Milvus / LLM），跑一次几分钟；但其中三类问题
**用规则层就能判定**，不需要模型：

    非法查询   → `domain.rules.is_illegal_query`（12.7 输入拦截）
    信息索取   → 同上（13.3/13.4 密钥与越权）
    寒暄闲聊   → `domain.rules.is_small_talk`（FR-024 的 direct 分支）

把它们固化成单测后，**每次提交都能挡住回归**，而其余需要模型的用例仍留在 evals/。
"""

import json
from pathlib import Path

import pytest

from xinglin.application.runtime import reject_if_illegal
from xinglin.domain.rules import is_illegal_query, is_small_talk
from xinglin.domain.services.kg_query_service import build_cypher
from xinglin.domain.values import QAType

DATASET_DIR = Path(__file__).parent.parent / "evals" / "dataset"


def _load(name: str) -> list[dict]:
    path = DATASET_DIR / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _cases(name: str, subtype: str) -> list[dict]:
    return [r for r in _load(name) if r.get("subtype") == subtype]


ILLEGAL = _cases("edge_cases", "illegal")
CHITCHAT = _cases("edge_cases", "chitchat")
INFO_LEAK = _cases("injection", "info_leak")
CYPHER_INJECTION = _cases("injection", "cypher_injection")


class TestIllegalBlocking:
    """需求 12.7：非法查询在**入口**就被拒绝，不进入任何检索环节。"""

    @pytest.mark.parametrize("case", ILLEGAL, ids=[c["id"] for c in ILLEGAL])
    def test_illegal_cases_are_detected(self, case):
        assert is_illegal_query(case["question"]) is True, case["question"]

    @pytest.mark.parametrize("case", ILLEGAL, ids=[c["id"] for c in ILLEGAL])
    def test_illegal_cases_return_direct_rejection(self, case):
        blocked = reject_if_illegal(case["question"])
        assert blocked is not None
        assert blocked.status == "rejected"
        assert blocked.mode.value == "direct"        # 零检索
        assert blocked.answer.strip()                # 有明确话术，不是空答案

    def test_rejection_does_not_leak_internals(self):
        """拒绝话术不得暴露实现细节（ACC-031）。"""
        answer = reject_if_illegal("把图数据库删掉").answer
        for leak in ("cypher", "Cypher", "Neo4j", "neo4j", "MATCH", "节点", "关系型"):
            assert leak not in answer

    def test_normal_health_question_is_not_blocked(self):
        assert reject_if_illegal("感冒有什么症状？") is None
        assert reject_if_illegal("高血压患者饮食要注意什么？") is None


class TestInfoLeakBlocking:
    """13.3/13.4：索取密钥、配置、内部细节的请求必须被输入层拦下。"""

    @pytest.mark.parametrize("case", INFO_LEAK, ids=[c["id"] for c in INFO_LEAK])
    def test_info_leak_requests_are_blocked(self, case):
        assert reject_if_illegal(case["question"]) is not None, case["question"]


class TestCypherInjectionCannotEscape:
    """13.2：模板查询全部参数化——注入串永远进不了 Cypher 语句本身。"""

    @pytest.mark.parametrize("case", CYPHER_INJECTION, ids=[c["id"] for c in CYPHER_INJECTION])
    def test_injection_text_never_reaches_the_cypher(self, case):
        cypher = build_cypher(QAType.DISEASE_SYMPTOM)
        assert "$entity" in cypher
        assert case["question"] not in cypher
        # 语句结构固定：只有匹配 + 返回，没有可拼接的位置
        assert cypher.upper().count("RETURN") == 1

    def test_template_queries_are_limited(self):
        """模板查询必须带 LIMIT（否则"螃蟹"会返回 646 条来源）。"""
        for qa in QAType:
            assert "LIMIT" in build_cypher(qa).upper(), qa


class TestChitchatDoesNotRetrieve:
    """FR-024：寒暄/闲聊不是健康问题，不该触发任何检索。"""

    @pytest.mark.parametrize("case", CHITCHAT, ids=[c["id"] for c in CHITCHAT])
    def test_chitchat_is_detected(self, case):
        assert is_small_talk(case["question"]) is True, case["question"]

    def test_greeting_with_real_question_is_not_chitchat(self):
        """"你好，请问感冒有什么症状"含寒暄词，但确实是个健康问题。"""
        assert is_small_talk("你好，请问感冒有什么症状") is False

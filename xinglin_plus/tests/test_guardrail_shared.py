"""护栏的**共用入口**（`build_context` / `guard_answer`）——纯离线。

背景：护栏原本只在自动问答链路里调用，工具编排链路漏了这一步（而它的注释却声称
做了核查）。现在把"拼证据上下文 + 核查 + 追提醒"收敛到 `domain/guardrail` 供各链路共用，
本文件守住这份实现，避免再次出现"某条链路绕过护栏"。
"""

from xinglin.domain.entities import Fact
from xinglin.domain.guardrail import build_context, guard_answer


class _StubGuardrail:
    """替身护栏：按预置结论返回，不调用任何模型。"""

    def __init__(self, grounded: bool, unsupported: list[str] | None = None):
        self._grounded = grounded
        self._unsupported = unsupported or []
        self.calls: list[tuple[str, str]] = []

    def check(self, answer: str, context: str) -> dict:
        self.calls.append((answer, context))
        return {"grounded": self._grounded,
                "unsupported": self._unsupported,
                "reason": "stub"}


class TestBuildContext:
    def test_fuses_both_evidence_sources(self):
        context = build_context(
            [Fact(entity="感冒", relation="has_symptom", value="咳嗽")],
            [{"text": "文献片段内容"}])
        assert "知识图谱事实" in context
        assert "感冒 has_symptom 咳嗽" in context
        assert "检索文档" in context and "文献片段内容" in context

    def test_empty_evidence_yields_empty_context(self):
        assert build_context([], []) == ""

    def test_only_one_source_is_fine(self):
        assert "检索文档" not in build_context(
            [Fact(entity="感冒", relation="has_symptom", value="咳嗽")], [])


class TestGuardAnswer:
    def test_no_context_returns_answer_untouched(self):
        """无证据（如寒暄）本就没有可核查的依据，直接放行，且不调用护栏。"""
        guardrail = _StubGuardrail(grounded=False, unsupported=["x"])
        assert guard_answer("答案", "", guardrail) == "答案"
        assert guardrail.calls == []

    def test_missing_guardrail_returns_answer_untouched(self):
        assert guard_answer("答案", "证据", None) == "答案"

    def test_grounded_answer_is_unchanged(self):
        guardrail = _StubGuardrail(grounded=True)
        assert guard_answer("答案", "证据", guardrail) == "答案"
        assert len(guardrail.calls) == 1

    def test_ungrounded_answer_gets_reminder_appended(self):
        """「提醒不拦截」：保留原答案，只在末尾追加提醒。"""
        guardrail = _StubGuardrail(grounded=False, unsupported=["编造的数字 30%"])
        result = guard_answer("原文答案", "证据", guardrail)
        assert result.startswith("原文答案")
        assert "请谨慎参考" in result
        assert "编造的数字 30%" in result

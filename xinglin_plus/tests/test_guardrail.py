"""事实护栏（文档 §9.1）：用 LLM **二次核查**答案是否被参考上下文支撑。

三条硬性口径（都是文档明确论证过的）：
1. 独立成**第二次 LLM 调用**，而不是让生成模型自查（避免自检偏见，§11.1.5）；
2. 核查失败 / 无上下文时 **fail-open 降级放行**，绝不阻塞问答（§9.1）；
3. 无依据时**在答案末尾追加提醒**，而不是拦下回答（§11.1.8）。
"""

from xinglin.domain.guardrail import FactGuardrail, add_unsupported_note
from tests.conftest import FakeLLM


class TestFactGuardrail:
    def test_no_context_skips_check(self):
        llm = FakeLLM()
        verdict = FactGuardrail(llm).check("任意答案", "")
        assert verdict["grounded"] is True
        assert "跳过" in verdict["reason"]
        assert llm.calls == [], "没有上下文时不应浪费一次 LLM 调用"

    def test_grounded_true(self):
        llm = FakeLLM(reply='{"grounded": true, "unsupported": [], "reason": "有依据"}')
        verdict = FactGuardrail(llm).check("阿司匹林可解热", "阿司匹林具有解热、镇痛作用")
        assert verdict["grounded"] is True
        assert len(llm.calls) == 1, "护栏必须是真实的一次 LLM 调用"

    def test_grounded_false_lists_unsupported(self):
        llm = FakeLLM(reply='{"grounded": false, "unsupported": ["可治疗感冒"],'
                            ' "reason": "参考资料未提及"}')
        verdict = FactGuardrail(llm).check("阿司匹林可治疗感冒", "阿司匹林具有解热作用")
        assert verdict["grounded"] is False
        assert verdict["unsupported"] == ["可治疗感冒"]

    def test_markdown_fence_tolerated(self):
        llm = FakeLLM(reply='```json\n{"grounded": true}\n```')
        assert FactGuardrail(llm).check("x", "y")["grounded"] is True

    def test_bad_json_fails_open(self):
        verdict = FactGuardrail(FakeLLM(reply="这不是 JSON")).check("x", "y")
        assert verdict["grounded"] is True
        assert "跳过" in verdict["reason"]

    def test_llm_exception_fails_open(self):
        class _Broken(FakeLLM):
            def complete(self, *args, **kwargs):
                raise RuntimeError("network down")

        verdict = FactGuardrail(_Broken()).check("x", "y")
        assert verdict["grounded"] is True, "核查异常必须降级放行"

    def test_prompt_carries_context_and_answer(self):
        llm = FakeLLM(reply='{"grounded": true}')
        FactGuardrail(llm).check("待核查的答案", "参考上下文内容")
        system, user = llm.calls[0]
        assert "事实核查" in system
        assert "待核查的答案" in user and "参考上下文内容" in user

    def test_reason_is_returned_for_observability(self):
        llm = FakeLLM(reply='{"grounded": false, "unsupported": ["x"], "reason": "只说明了作用"}')
        assert FactGuardrail(llm).check("a", "b")["reason"] == "只说明了作用"


class TestUnsupportedNote:
    def test_note_keeps_answer_and_appends_reminder(self):
        out = add_unsupported_note("原始答案", ["陈述A", "陈述B"])
        assert out.startswith("原始答案")
        assert "陈述A、陈述B" in out
        assert "请谨慎参考" in out

    def test_note_without_items(self):
        assert "请谨慎参考" in add_unsupported_note("原始答案", [])

    def test_only_first_five_items_listed(self):
        out = add_unsupported_note("答案", [f"c{i}" for i in range(8)])
        assert "c4" in out
        assert "c5" not in out

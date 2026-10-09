"""接口层：CLI 参数解析与 HTTP DTO 约束（不启动服务、不发请求）。"""

import pytest
from pydantic import ValidationError

from xinglin.interfaces.cli import MODES, build_parser
from xinglin.interfaces.web import AskRequest


class TestCliParser:
    def test_default_mode_is_hybrid(self):
        assert build_parser().parse_args([]).mode == "hybrid"

    @pytest.mark.parametrize("mode", MODES)
    def test_accepts_every_documented_mode(self, mode):
        assert build_parser().parse_args(["--mode", mode]).mode == mode

    def test_rejects_unknown_mode(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--mode", "not-a-mode"])

    def test_question_flag(self):
        assert build_parser().parse_args(["-q", "感冒有什么症状"]).question == "感冒有什么症状"

    def test_cache_flag_defaults_off(self):
        assert build_parser().parse_args([]).cache is False


class TestWebDto:
    def test_question_is_required(self):
        with pytest.raises(ValidationError):
            AskRequest()

    def test_question_length_is_capped(self):
        with pytest.raises(ValidationError):
            AskRequest(question="x" * 501)

    def test_empty_question_rejected(self):
        with pytest.raises(ValidationError):
            AskRequest(question="")

    def test_valid_question_accepted(self):
        assert AskRequest(question="感冒有什么症状").question == "感冒有什么症状"

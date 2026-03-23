"""Unit tests for judge.py functions (JSON parsing, API calls)."""

from unittest.mock import MagicMock, patch

from forgelm.judge import JudgeResult, _parse_judge_json


class TestParseJudgeJson:
    def test_valid_json(self):
        result = _parse_judge_json('{"score": 8, "reason": "Good answer"}')
        assert result["score"] == 8
        assert result["reason"] == "Good answer"

    def test_json_in_markdown_code_block(self):
        text = '```json\n{"score": 7, "reason": "OK"}\n```'
        result = _parse_judge_json(text)
        assert result["score"] == 7

    def test_json_in_plain_code_block(self):
        text = '```\n{"score": 6, "reason": "Decent"}\n```'
        result = _parse_judge_json(text)
        assert result["score"] == 6

    def test_invalid_json_returns_zero(self):
        result = _parse_judge_json("This is not JSON at all")
        assert result["score"] == 0
        assert "Invalid JSON" in result["reason"]

    def test_empty_string(self):
        result = _parse_judge_json("")
        assert result["score"] == 0

    def test_whitespace_padding(self):
        result = _parse_judge_json('  \n  {"score": 9, "reason": "Great"}  \n  ')
        assert result["score"] == 9

    def test_nested_json(self):
        text = '{"score": 5, "reason": "OK", "details": {"sub": 1}}'
        result = _parse_judge_json(text)
        assert result["score"] == 5

    def test_multiple_code_blocks(self):
        text = '```\ninvalid\n```\n```json\n{"score": 4, "reason": "Found"}\n```'
        result = _parse_judge_json(text)
        assert result["score"] == 4


class TestCallApiJudge:
    @patch("requests.post")
    def test_successful_api_call(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": '{"score": 8, "reason": "Good"}'}}]}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        from forgelm.judge import _call_api_judge

        result = _call_api_judge("test prompt", "fake-api-key", "gpt-4o")
        assert result["score"] == 8
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_api_timeout(self, mock_post):
        import requests

        mock_post.side_effect = requests.exceptions.Timeout("timed out")

        from forgelm.judge import _call_api_judge

        result = _call_api_judge("test prompt", "fake-key")
        assert result["score"] == 0
        assert "API error" in result["reason"]

    @patch("requests.post")
    def test_custom_api_base(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": '{"score": 7, "reason": "OK"}'}}]}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        from forgelm.judge import _call_api_judge

        _call_api_judge("prompt", "key", "model", api_base="https://custom.api/v1/chat")
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://custom.api/v1/chat"


class TestJudgeResult:
    def test_defaults(self):
        r = JudgeResult()
        assert r.average_score == 0.0
        assert r.passed is True
        assert r.scores == []
        assert r.details == []

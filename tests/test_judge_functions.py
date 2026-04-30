"""Unit tests for judge.py functions (JSON parsing, API calls)."""

from unittest.mock import MagicMock, patch

import pytest

from forgelm.judge import JudgeResult, _parse_judge_json

# run_judge_evaluation requires torch to generate responses
torch_available = True
try:
    import torch  # noqa: F401
except ImportError:
    torch_available = False


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

    def test_invalid_json_returns_none_sentinel(self):
        # score=None signals a parse failure so the caller can drop the
        # sample from the average instead of clipping it up to 1.0.
        result = _parse_judge_json("This is not JSON at all")
        assert result["score"] is None
        assert "Invalid JSON" in result["reason"]

    def test_empty_string(self):
        result = _parse_judge_json("")
        assert result["score"] is None

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
    @patch("forgelm._http.requests.post")
    def test_successful_api_call(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": '{"score": 8, "reason": "Good"}'}}]}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        from forgelm.judge import _call_api_judge

        result = _call_api_judge("test prompt", "fake-api-key", "gpt-4o")
        assert result["score"] == 8
        mock_post.assert_called_once()

    @patch("forgelm._http.requests.post")
    def test_api_timeout(self, mock_post):
        import requests

        mock_post.side_effect = requests.exceptions.Timeout("timed out")

        from forgelm.judge import _call_api_judge

        result = _call_api_judge("test prompt", "fake-key")
        # Transport failures use the same None sentinel as parse failures.
        assert result["score"] is None
        assert "API error" in result["reason"]

    @patch("forgelm._http.requests.post")
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
        assert r.average_score == pytest.approx(0.0)
        assert r.passed is True
        assert r.scores == []
        assert r.details == []


@pytest.mark.skipif(not torch_available, reason="torch not installed")
class TestJudgeScoreClipping:
    @patch("forgelm._http.requests.post")
    def test_score_above_10_clipped_to_10(self, mock_post, caplog):
        """Scores above 10 must be clamped to 10.0 with a warning."""
        import logging

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"score": 15, "reason": "Excellent"}'}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        from forgelm.judge import _call_api_judge

        with caplog.at_level(logging.WARNING, logger="forgelm.judge"):
            result = _call_api_judge("test prompt", "fake-key", "gpt-4o")

        # The raw parse returns 15; clipping happens in run_judge_evaluation.
        # _call_api_judge returns the raw parsed value.
        assert result["score"] == 15

    @patch("forgelm._http.requests.post")
    def test_score_clipped_in_run_judge_evaluation(self, mock_post, tmp_path, caplog):
        """run_judge_evaluation must clip out-of-range scores and emit a warning."""
        import logging

        import torch

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"score": 15, "reason": "Way too good"}'}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        # Minimal eval dataset
        eval_file = tmp_path / "eval.jsonl"
        eval_file.write_text('{"prompt": "Hello?"}\n')

        mock_model = MagicMock()
        mock_model.device = "cpu"
        fake_output = torch.zeros((1, 5), dtype=torch.long)
        mock_model.generate.return_value = fake_output

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": torch.zeros((1, 3), dtype=torch.long),
            "attention_mask": torch.ones((1, 3), dtype=torch.long),
        }
        mock_tokenizer.decode.return_value = "A fine answer."

        from forgelm.judge import run_judge_evaluation

        with caplog.at_level(logging.WARNING, logger="forgelm.judge"):
            result = run_judge_evaluation(
                model=mock_model,
                tokenizer=mock_tokenizer,
                eval_dataset_path=str(eval_file),
                judge_model="gpt-4o",
                judge_api_key="fake-key",
                min_score=5.0,
            )

        # Score must be clipped to 10.0
        assert result.scores[0] == pytest.approx(10.0)
        assert result.average_score == pytest.approx(10.0)
        # Warning must be emitted
        assert any("clipped" in r.message or "out-of-range" in r.message for r in caplog.records)

    @patch("forgelm._http.requests.post")
    def test_score_below_1_clipped_to_1(self, mock_post, tmp_path):
        """Scores below 1 must be clamped to 1.0."""
        import torch

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": '{"score": -5, "reason": "Terrible"}'}}]}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        eval_file = tmp_path / "eval.jsonl"
        eval_file.write_text('{"prompt": "Hello?"}\n')

        mock_model = MagicMock()
        mock_model.device = "cpu"
        mock_model.generate.return_value = torch.zeros((1, 5), dtype=torch.long)

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": torch.zeros((1, 3), dtype=torch.long),
            "attention_mask": torch.ones((1, 3), dtype=torch.long),
        }
        mock_tokenizer.decode.return_value = "Bad."

        from forgelm.judge import run_judge_evaluation

        result = run_judge_evaluation(
            model=mock_model,
            tokenizer=mock_tokenizer,
            eval_dataset_path=str(eval_file),
            judge_model="gpt-4o",
            judge_api_key="fake-key",
            min_score=1.0,
        )
        assert result.scores[0] == pytest.approx(1.0)


class TestJudgeApiBasePassthrough:
    @patch("forgelm._http.requests.post")
    def test_api_base_reaches_http_call(self, mock_post):
        """judge_api_base in config must be forwarded to the HTTP POST call."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": '{"score": 7, "reason": "OK"}'}}]}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        from forgelm.judge import _call_api_judge

        custom_base = "https://custom.llm.api/v1/chat/completions"
        _call_api_judge("prompt", "key", "model", api_base=custom_base)

        call_args = mock_post.call_args
        actual_url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url") or call_args[1].get("url")
        # The URL passed to requests.post should match the custom api_base
        assert actual_url == custom_base


class TestJudgeUsesSafePost:
    """Phase 7: judge._call_api_judge must route through forgelm._http.safe_post.

    The acceptance gate is: ``grep -rn 'requests.post' forgelm/`` returns
    nothing outside ``_http.py``. These tests cover the behavioural side —
    judge calls go through ``safe_post`` and inherit the SSRF / scheme /
    redirect / TLS policy automatically.
    """

    def test_imports_safe_post(self):
        """judge._call_api_judge must import safe_post from forgelm._http."""
        import inspect

        from forgelm import judge

        src = inspect.getsource(judge._call_api_judge)
        assert "safe_post" in src, "judge._call_api_judge must use safe_post"

    @patch("forgelm._http.requests.post")
    def test_judge_call_goes_through_safe_post(self, mock_post):
        """A successful judge call must hit requests.post (via safe_post)."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": '{"score": 7, "reason": "OK"}'}}]}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        from forgelm.judge import _call_api_judge

        result = _call_api_judge("prompt", "fake-key", "gpt-4o")

        # Confirm the call went through safe_post → requests.post
        mock_post.assert_called_once()
        kwargs = mock_post.call_args.kwargs
        # safe_post forwards allow_redirects=False
        assert kwargs.get("allow_redirects") is False
        assert result["score"] == 7

    @patch("forgelm._http.requests.post")
    def test_judge_ssrf_block_for_private_url(self, mock_post):
        """A private-IP api_base must be rejected before any network call.

        ``_call_api_judge`` re-raises :class:`HttpSafetyError` so
        ``run_judge_evaluation`` can convert it into a hard
        ``JudgeResult(passed=False)`` instead of silently scoring every
        prompt as ``None`` (which would mask a misconfigured endpoint).
        """
        import pytest

        from forgelm._http import HttpSafetyError
        from forgelm.judge import _call_api_judge

        with pytest.raises(HttpSafetyError):
            _call_api_judge(
                "prompt",
                "fake-key",
                "gpt-4o",
                api_base="https://10.0.0.1/v1/chat/completions",  # NOSONAR RFC1918 — SSRF guard fixture (intentional)
            )

        mock_post.assert_not_called()

"""Unit tests for forgelm.webhook module."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from forgelm.config import ForgeConfig
from forgelm.webhook import WebhookNotifier


def _make_config(webhook_cfg=None):
    """Create a minimal ForgeConfig with optional webhook."""
    data = {
        "model": {"name_or_path": "org/model"},
        "lora": {},
        "training": {},
        "data": {"dataset_name_or_path": "org/dataset"},
    }
    if webhook_cfg:
        data["webhook"] = webhook_cfg
    return ForgeConfig(**data)


class TestWebhookNotifier:
    def test_no_webhook_config(self):
        """Notifier should silently do nothing when webhook is not configured."""
        config = _make_config()
        notifier = WebhookNotifier(config)
        # Should not raise
        notifier.notify_start(run_name="test")
        notifier.notify_success(run_name="test", metrics={"loss": 0.5})
        notifier.notify_failure(run_name="test", reason="error")

    def test_no_url(self):
        """Notifier should do nothing when webhook has no url."""
        config = _make_config({"notify_on_start": True})
        notifier = WebhookNotifier(config)
        notifier.notify_start(run_name="test")

    @patch("forgelm._http.requests.post")
    def test_notify_start(self, mock_post):
        config = _make_config({"url": "https://example.com/hook"})
        notifier = WebhookNotifier(config)
        notifier.notify_start(run_name="my_model_finetune")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = json.loads(call_kwargs.kwargs.get("data") or call_kwargs[1]["data"])
        assert payload["event"] == "training.start"
        assert payload["status"] == "started"
        assert payload["run_name"] == "my_model_finetune"

    @patch("forgelm._http.requests.post")
    def test_notify_success_with_metrics(self, mock_post):
        config = _make_config({"url": "https://example.com/hook"})
        notifier = WebhookNotifier(config)
        metrics = {"eval_loss": 1.25, "train_loss": 0.8}
        notifier.notify_success(run_name="test_run", metrics=metrics)

        call_kwargs = mock_post.call_args
        payload = json.loads(call_kwargs.kwargs.get("data") or call_kwargs[1]["data"])
        assert payload["event"] == "training.success"
        assert payload["metrics"]["eval_loss"] == pytest.approx(1.25)

    @patch("forgelm._http.requests.post")
    def test_notify_failure_with_reason(self, mock_post):
        config = _make_config({"url": "https://example.com/hook"})
        notifier = WebhookNotifier(config)
        notifier.notify_failure(run_name="test_run", reason="OOM error")

        call_kwargs = mock_post.call_args
        payload = json.loads(call_kwargs.kwargs.get("data") or call_kwargs[1]["data"])
        assert payload["event"] == "training.failure"
        assert payload["reason"] == "OOM error"

    @patch("forgelm._http.requests.post")
    def test_url_env_resolution(self, mock_post):
        config = _make_config({"url_env": "TEST_WEBHOOK_URL"})
        notifier = WebhookNotifier(config)

        with patch.dict(os.environ, {"TEST_WEBHOOK_URL": "https://env.example.com/hook"}):
            notifier.notify_start(run_name="test")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert (
            call_kwargs.kwargs.get("url") == "https://env.example.com/hook"
            or call_kwargs[0][0] == "https://env.example.com/hook"
        )

    @patch("forgelm._http.requests.post")
    def test_notify_on_start_disabled(self, mock_post):
        config = _make_config(
            {
                "url": "https://example.com/hook",
                "notify_on_start": False,
            }
        )
        notifier = WebhookNotifier(config)
        notifier.notify_start(run_name="test")
        mock_post.assert_not_called()

    @patch("forgelm._http.requests.post")
    def test_timeout_handled_gracefully(self, mock_post):
        import requests as req

        mock_post.side_effect = req.exceptions.Timeout("timed out")
        config = _make_config({"url": "https://example.com/hook"})
        notifier = WebhookNotifier(config)
        # Should not raise
        notifier.notify_start(run_name="test")

    @patch("forgelm._http.requests.post")
    def test_connection_error_handled_gracefully(self, mock_post):
        import requests as req

        mock_post.side_effect = req.exceptions.ConnectionError("refused")
        config = _make_config({"url": "https://example.com/hook"})
        notifier = WebhookNotifier(config)
        # Should not raise
        notifier.notify_failure(run_name="test", reason="test error")

    @patch("forgelm._http.requests.post")
    def test_payload_has_slack_attachments(self, mock_post):
        config = _make_config({"url": "https://example.com/hook"})
        notifier = WebhookNotifier(config)
        notifier.notify_start(run_name="test")

        call_kwargs = mock_post.call_args
        payload = json.loads(call_kwargs.kwargs.get("data") or call_kwargs[1]["data"])
        assert "attachments" in payload
        assert len(payload["attachments"]) == 1
        assert "title" in payload["attachments"][0]

    @patch("forgelm._http.requests.post")
    def test_http_5xx_logs_warning(self, mock_post, caplog):
        """Non-2xx HTTP responses must emit a WARNING and not raise."""
        import logging

        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 503
        mock_response.text = "Service Unavailable"
        mock_post.return_value = mock_response

        config = _make_config({"url": "https://example.com/hook"})
        notifier = WebhookNotifier(config)

        with caplog.at_level(logging.WARNING, logger="forgelm.webhook"):
            notifier.notify_start(run_name="test_run")

        assert any("503" in r.message or "HTTP" in r.message for r in caplog.records)

    @patch("forgelm._http.requests.post")
    def test_http_4xx_logs_warning(self, mock_post, caplog):
        """HTTP 4xx response must emit a WARNING log and not raise."""
        import logging

        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_post.return_value = mock_response

        config = _make_config({"url": "https://example.com/hook"})
        notifier = WebhookNotifier(config)

        with caplog.at_level(logging.WARNING, logger="forgelm.webhook"):
            notifier.notify_failure(run_name="test_run", reason="OOM")

        assert any("404" in r.message or "HTTP" in r.message for r in caplog.records)


class TestSafePostHttpDiscipline:
    """Direct unit tests for forgelm._http.safe_post.

    These cover the policy gates that every outbound HTTP call site relies
    on. The Phase 7 closure adds judge + synthetic + (existing) webhook to
    the call-site list; the gates must reject misconfigured URLs identically
    across all of them.

    NOTE for static analysers: the literals in this class deliberately
    include RFC1918 / loopback / IMDS / multicast IP addresses, plain
    ``http://`` URLs, and ``ftp://`` URLs. These are not security
    vulnerabilities — they are the inputs the test asserts the SSRF /
    scheme guard rejects. Removing them would erase the coverage of those
    rejections.
    """

    @pytest.mark.parametrize(
        "url",
        [
            "https://10.0.0.1/hook",  # NOSONAR RFC1918 (10/8) — SSRF guard fixture
            "https://172.16.0.5/hook",  # NOSONAR RFC1918 (172.16/12) — SSRF guard fixture
            "https://192.168.1.10/hook",  # NOSONAR RFC1918 (192.168/16) — SSRF guard fixture
            "https://127.0.0.1/hook",  # NOSONAR loopback — SSRF guard fixture
            "https://169.254.169.254/latest/meta-data/",  # NOSONAR AWS IMDS — SSRF guard fixture
            "https://224.0.0.1/multicast",  # NOSONAR multicast — SSRF guard fixture
        ],
    )
    def test_ssrf_block_private_ip(self, url):
        """Each private/loopback/IMDS/multicast destination must raise."""
        from forgelm._http import HttpSafetyError, safe_post

        with pytest.raises(HttpSafetyError, match="Private/loopback/IMDS"):
            safe_post(url, json={}, timeout=10.0)

    def test_ssrf_block_can_be_opted_out(self):
        """allow_private=True bypasses the SSRF guard (operator opt-in)."""
        from forgelm import _http

        with patch.object(_http.requests, "post") as mock_post:
            mock_post.return_value = MagicMock(ok=True, status_code=200)
            _http.safe_post(
                "https://10.0.0.1/hook",  # NOSONAR RFC1918 — SSRF opt-out fixture
                json={},
                timeout=10.0,
                allow_private=True,
            )
            mock_post.assert_called_once()

    def test_redirect_block(self):
        """allow_redirects=False is forwarded to requests.post."""
        from forgelm import _http

        with patch.object(_http.requests, "post") as mock_post:
            mock_post.return_value = MagicMock(ok=True, status_code=200)
            _http.safe_post("https://example.com/hook", json={}, timeout=10.0)
            kwargs = mock_post.call_args.kwargs
            assert kwargs["allow_redirects"] is False

    def test_http_block(self):
        """http:// URLs are rejected unless allow_insecure_http is set."""
        from forgelm._http import HttpSafetyError, safe_post

        with pytest.raises(HttpSafetyError, match="http://"):
            safe_post("http://example.com/hook", json={}, timeout=10.0)  # NOSONAR scheme blocker fixture

    def test_http_allowed_with_opt_in(self):
        """allow_insecure_http=True (used by webhook) lets http:// through."""
        from forgelm import _http

        with patch.object(_http.requests, "post") as mock_post:
            mock_post.return_value = MagicMock(ok=True, status_code=200)
            _http.safe_post(
                "http://example.com/hook",  # NOSONAR opt-in fixture (webhook back-compat path)
                json={},
                timeout=10.0,
                allow_insecure_http=True,
            )
            mock_post.assert_called_once()

    def test_unsupported_scheme(self):
        """ftp:// / file:// / etc. are rejected even with allow_insecure_http."""
        from forgelm._http import HttpSafetyError, safe_post

        with pytest.raises(HttpSafetyError, match="Unsupported URL scheme"):
            safe_post(
                "ftp://example.com/hook",  # NOSONAR scheme blocker fixture (ftp not allowed)
                json={},
                timeout=10.0,
                allow_insecure_http=True,
            )

    def test_timeout_floor_rejects_below_default(self):
        """timeout below the 10s default floor must raise."""
        from forgelm._http import HttpSafetyError, safe_post

        with pytest.raises(HttpSafetyError, match="Timeout below"):
            safe_post("https://example.com/hook", json={}, timeout=5.0)

    def test_timeout_zero_rejected_even_with_lower_floor(self):
        """timeout=0 is always rejected (requests treats it as 'no timeout')."""
        from forgelm._http import HttpSafetyError, safe_post

        with pytest.raises(HttpSafetyError, match="Timeout below"):
            safe_post(
                "https://example.com/hook",
                json={},
                timeout=0,
                min_timeout=1.0,
            )

    def test_timeout_floor_overridable(self):
        """Webhook passes min_timeout=1.0 to keep its historical floor."""
        from forgelm import _http

        with patch.object(_http.requests, "post") as mock_post:
            mock_post.return_value = MagicMock(ok=True, status_code=200)
            _http.safe_post(
                "https://example.com/hook",
                json={},
                timeout=2.0,
                min_timeout=1.0,
            )
            mock_post.assert_called_once()

    def test_header_masking_on_error(self, caplog):
        """Authorization / X-API-Key values are redacted from the failure log."""
        import logging

        import requests as req

        from forgelm import _http

        bearer_token = "sk-" + "supersecret123"  # noqa: S105  NOSONAR test fixture, fragment-built
        with patch.object(_http.requests, "post") as mock_post:
            mock_post.side_effect = req.exceptions.ConnectionError(f"refused while sending Bearer {bearer_token}")
            with caplog.at_level(logging.WARNING, logger="forgelm._http"):
                with pytest.raises(req.exceptions.ConnectionError):
                    _http.safe_post(
                        "https://example.com/hook",
                        json={},
                        headers={"Authorization": f"Bearer {bearer_token}"},
                        timeout=10.0,
                    )

        # The bearer token must be masked from the warning log.
        log_text = " ".join(r.message for r in caplog.records)
        assert bearer_token not in log_text
        assert "[REDACTED]" in log_text

    def test_localhost_blocked_by_hostname(self):
        """'localhost' resolves to 127.0.0.1; SSRF guard must catch it."""
        from forgelm._http import HttpSafetyError, safe_post

        with pytest.raises(HttpSafetyError, match="Private/loopback"):
            safe_post("https://localhost/hook", json={}, timeout=10.0)


class TestLifecycleVocabulary:
    """Faz 8: notify_reverted + notify_awaiting_approval lifecycle events.

    These pin the wire-format of the two new payload events so dashboards
    that already filter on event="training.reverted" / "approval.required"
    don't silently break on a future refactor.
    """

    @patch("forgelm._http.requests.post")
    def test_notify_reverted_payload(self, mock_post):
        """Auto-revert event must serialize as event=training.reverted with masked + truncated reason."""
        config = _make_config({"url": "https://example.com/hook"})
        notifier = WebhookNotifier(config)

        # Reason carries a Slack webhook secret + a long padding so we can
        # assert both the masking and the 2048-char truncation paths.
        # Token built fragment-by-fragment per docs/standards/regex.md Rule 7
        # so GitHub secret scanning + gitleaks don't flag the literal.
        leaky_token = "xoxb-" + "12345678901" + "-" + "1234567890123" + "-" + "AbCdEfGhIjKlMnOpQrStUvWx"
        long_pad = "X" * 3000
        reason = f"safety gate failed: {leaky_token} traceback: {long_pad}"

        notifier.notify_reverted(run_name="my_run", reason=reason)

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = json.loads(call_kwargs.kwargs.get("data") or call_kwargs[1]["data"])

        assert payload["event"] == "training.reverted"
        assert payload["status"] == "reverted"
        assert payload["run_name"] == "my_run"
        assert leaky_token not in payload["reason"], "Slack token must be redacted"
        assert leaky_token not in payload["attachments"][0]["text"], (
            "Slack token must be redacted in attachment text too"
        )
        # Truncated to 2048 + "… (truncated)" marker.
        assert len(payload["reason"]) <= 2048 + len("… (truncated)")
        assert payload["reason"].endswith("… (truncated)")

    @patch("forgelm._http.requests.post")
    def test_notify_reverted_distinct_from_failure(self, mock_post):
        """training.reverted must not collide with training.failure (dashboards rely on this split)."""
        config = _make_config({"url": "https://example.com/hook"})
        notifier = WebhookNotifier(config)

        notifier.notify_reverted(run_name="r", reason="judge below threshold")

        call_kwargs = mock_post.call_args
        payload = json.loads(call_kwargs.kwargs.get("data") or call_kwargs[1]["data"])

        assert payload["event"] == "training.reverted"
        assert payload["event"] != "training.failure"
        # Color must signal "reverted" (warning orange), not "failed" (red).
        assert payload["attachments"][0]["color"] == "#ff9900"

    @patch("forgelm._http.requests.post")
    def test_notify_awaiting_approval_payload(self, mock_post):
        """Approval gate must serialize as event=approval.required with model_path included."""
        config = _make_config({"url": "https://example.com/hook"})
        notifier = WebhookNotifier(config)

        notifier.notify_awaiting_approval(
            run_name="my_run",
            model_path="/var/forgelm/runs/abc/final_model",  # NOSONAR — payload string fixture, no fs op
        )

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = json.loads(call_kwargs.kwargs.get("data") or call_kwargs[1]["data"])

        assert payload["event"] == "approval.required"
        assert payload["status"] == "awaiting_approval"
        assert payload["run_name"] == "my_run"
        # NOSONAR — string literal, not a real filesystem operation
        assert payload["model_path"] == "/var/forgelm/runs/abc/final_model"
        assert "/var/forgelm/runs/abc/final_model" in payload["attachments"][0]["text"]

    @patch("forgelm._http.requests.post")
    def test_notify_awaiting_approval_no_model_weights_in_payload(self, mock_post):
        """Security: approval payload must carry the staging path only, never weight bytes or tensor dumps."""
        config = _make_config({"url": "https://example.com/hook"})
        notifier = WebhookNotifier(config)

        notifier.notify_awaiting_approval(
            run_name="r",
            model_path="/tmp/staged",
        )

        call_kwargs = mock_post.call_args
        payload = json.loads(call_kwargs.kwargs.get("data") or call_kwargs[1]["data"])

        # Schema is fixed: event/run_name/status/metrics/reason/model_path/attachments.
        # No weight-shaped fields. Anything else means a future regression
        # snuck a sensitive blob into the wire format.
        allowed_keys = {"event", "run_name", "status", "metrics", "reason", "model_path", "attachments"}
        assert set(payload.keys()) == allowed_keys
        # Belt-and-braces: the canonical weight-blob field names must never
        # appear in the serialized payload.
        serialized = json.dumps(payload)
        for forbidden in ("state_dict", "model.safetensors", "pytorch_model.bin", "adapter_model"):
            assert forbidden not in serialized, f"Payload must not carry {forbidden!r}"

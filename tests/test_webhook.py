"""Unit tests for forgelm.webhook module."""
import json
import os
from unittest.mock import patch

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

    @patch("forgelm.webhook.requests.post")
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

    @patch("forgelm.webhook.requests.post")
    def test_notify_success_with_metrics(self, mock_post):
        config = _make_config({"url": "https://example.com/hook"})
        notifier = WebhookNotifier(config)
        metrics = {"eval_loss": 1.25, "train_loss": 0.8}
        notifier.notify_success(run_name="test_run", metrics=metrics)

        call_kwargs = mock_post.call_args
        payload = json.loads(call_kwargs.kwargs.get("data") or call_kwargs[1]["data"])
        assert payload["event"] == "training.success"
        assert payload["metrics"]["eval_loss"] == 1.25

    @patch("forgelm.webhook.requests.post")
    def test_notify_failure_with_reason(self, mock_post):
        config = _make_config({"url": "https://example.com/hook"})
        notifier = WebhookNotifier(config)
        notifier.notify_failure(run_name="test_run", reason="OOM error")

        call_kwargs = mock_post.call_args
        payload = json.loads(call_kwargs.kwargs.get("data") or call_kwargs[1]["data"])
        assert payload["event"] == "training.failure"
        assert payload["reason"] == "OOM error"

    @patch("forgelm.webhook.requests.post")
    def test_url_env_resolution(self, mock_post):
        config = _make_config({"url_env": "TEST_WEBHOOK_URL"})
        notifier = WebhookNotifier(config)

        with patch.dict(os.environ, {"TEST_WEBHOOK_URL": "https://env.example.com/hook"}):
            notifier.notify_start(run_name="test")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs.get("url") == "https://env.example.com/hook" or \
               call_kwargs[0][0] == "https://env.example.com/hook"

    @patch("forgelm.webhook.requests.post")
    def test_notify_on_start_disabled(self, mock_post):
        config = _make_config({
            "url": "https://example.com/hook",
            "notify_on_start": False,
        })
        notifier = WebhookNotifier(config)
        notifier.notify_start(run_name="test")
        mock_post.assert_not_called()

    @patch("forgelm.webhook.requests.post")
    def test_timeout_handled_gracefully(self, mock_post):
        import requests as req
        mock_post.side_effect = req.exceptions.Timeout("timed out")
        config = _make_config({"url": "https://example.com/hook"})
        notifier = WebhookNotifier(config)
        # Should not raise
        notifier.notify_start(run_name="test")

    @patch("forgelm.webhook.requests.post")
    def test_connection_error_handled_gracefully(self, mock_post):
        import requests as req
        mock_post.side_effect = req.exceptions.ConnectionError("refused")
        config = _make_config({"url": "https://example.com/hook"})
        notifier = WebhookNotifier(config)
        # Should not raise
        notifier.notify_failure(run_name="test", reason="test error")

    @patch("forgelm.webhook.requests.post")
    def test_payload_has_slack_attachments(self, mock_post):
        config = _make_config({"url": "https://example.com/hook"})
        notifier = WebhookNotifier(config)
        notifier.notify_start(run_name="test")

        call_kwargs = mock_post.call_args
        payload = json.loads(call_kwargs.kwargs.get("data") or call_kwargs[1]["data"])
        assert "attachments" in payload
        assert len(payload["attachments"]) == 1
        assert "title" in payload["attachments"][0]

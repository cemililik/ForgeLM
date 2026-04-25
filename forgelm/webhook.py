import json
import logging
import os
from typing import Dict, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger("forgelm.webhook")


class WebhookNotifier:
    """Handles sending training status updates to configured webhook endpoints."""

    def __init__(self, config):
        self.config = config.webhook

    def _resolve_url(self) -> Optional[str]:
        """Pick the webhook URL from the config, falling back to url_env."""
        if not self.config:
            return None
        url = self.config.url
        if not url and getattr(self.config, "url_env", None):
            url = os.getenv(self.config.url_env)
        return url or None

    @staticmethod
    def _mask(url: str) -> str:
        """Redact credentials and signed query params from a webhook URL.

        Slack/Teams/Discord webhooks carry secrets in the path or query; basic
        auth can also embed them in userinfo. We log only ``scheme://host`` plus
        the first path segment so the destination is identifiable but the
        secret material is not leaked into logs.
        """
        try:
            parts = urlparse(url)
        except (ValueError, TypeError):
            return "<unparseable-url>"
        if not parts.scheme or not parts.netloc:
            return "<malformed-url>"
        host = parts.hostname or "unknown-host"
        first_segment = ""
        if parts.path:
            stripped = parts.path.lstrip("/").split("/", 1)[0]
            if stripped:
                first_segment = f"/{stripped}/..."
        return f"{parts.scheme}://{host}{first_segment}"

    def _post_payload(self, url: str, payload: dict, event: str) -> None:
        """POST *payload* to *url* and log any transport / HTTP errors."""
        masked_url = self._mask(url)
        try:
            resp = requests.post(
                url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=getattr(self.config, "timeout", 5),
            )
            if not resp.ok:
                # Don't log resp.text — receivers sometimes echo the payload
                # (which can contain secret-bearing fields) or include their
                # own auth context. Surface only the status code.
                logger.warning(
                    "Webhook HTTP %d for event '%s' (url=%s) — response body suppressed",
                    resp.status_code,
                    event,
                    masked_url,
                )
        except requests.exceptions.Timeout:
            logger.warning("Webhook request timed out for event '%s' (url=%s).", event, masked_url)
        except requests.exceptions.ConnectionError:
            logger.warning("Webhook connection failed for event '%s' (url=%s).", event, masked_url)
        except Exception:
            logger.exception("Unexpected error sending webhook notification for event '%s'.", event)

    def _send(
        self,
        *,
        event: str,
        run_name: str,
        status: str,
        title: str,
        text: str,
        color: str = "#36a64f",
        metrics: Optional[Dict[str, float]] = None,
        reason: Optional[str] = None,
    ) -> None:
        url = self._resolve_url()
        if not url:
            return

        if url.startswith("http://"):
            logger.warning("Webhook URL uses HTTP (not HTTPS). Data will be sent unencrypted.")

        # Sanitize metrics — only include numeric values
        safe_metrics = {k: v for k, v in (metrics or {}).items() if isinstance(v, (int, float))}

        # Generic webhook payload (works for most HTTP receivers)
        payload = {
            "event": event,
            "run_name": run_name,
            "status": status,
            "metrics": safe_metrics,
            "reason": reason,
            # Slack-compatible formatting (receivers can ignore)
            "attachments": [{"title": title, "text": text, "color": color}],
        }

        self._post_payload(url, payload, event)

    def notify_start(self, run_name: str) -> None:
        if self.config and self.config.notify_on_start:
            self._send(
                event="training.start",
                run_name=run_name,
                status="started",
                title=f"Training Started: {run_name}",
                text="The fine-tuning job has started.",
                color="#0052cc",
            )

    def notify_success(self, run_name: str, metrics: Dict[str, float]) -> None:
        if self.config and self.config.notify_on_success:
            metrics_str = "\n".join([f"• {k}: {v:.4f}" for k, v in metrics.items() if isinstance(v, (int, float))])
            self._send(
                event="training.success",
                run_name=run_name,
                status="succeeded",
                title=f"Training Succeeded: {run_name}",
                text=f"The job completed successfully.\n\nMetrics:\n{metrics_str}",
                color="#36a64f",
                metrics=metrics,
            )

    def notify_failure(self, run_name: str, reason: str) -> None:
        if self.config and self.config.notify_on_failure:
            self._send(
                event="training.failure",
                run_name=run_name,
                status="failed",
                title=f"Training Failed: {run_name}",
                text=f"The training job encountered an error or evaluation failed.\n\nReason: {reason}",
                color="#ff0000",
                reason=reason,
            )

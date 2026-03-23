import json
import logging
import os
from typing import Dict, Optional

import requests

logger = logging.getLogger("forgelm.webhook")

class WebhookNotifier:
    """Handles sending training status updates to configured webhook endpoints."""
    def __init__(self, config):
        self.config = config.webhook

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
        if not self.config:
            return

        url = self.config.url
        if not url and getattr(self.config, "url_env", None):
            url = os.getenv(self.config.url_env)

        if not url:
            return

        # Generic webhook payload (works for most HTTP receivers)
        payload = {
            "event": event,
            "run_name": run_name,
            "status": status,
            "metrics": metrics or {},
            "reason": reason,
            # Slack-compatible formatting (receivers can ignore)
            "attachments": [{"title": title, "text": text, "color": color}],
        }

        try:
            requests.post(
                url,
                data=json.dumps(payload),
                headers={'Content-Type': 'application/json'},
                timeout=getattr(self.config, "timeout", 5)
            )
        except requests.exceptions.Timeout:
            logger.warning("Webhook request timed out for event '%s' (url=%s).", event, url)
        except requests.exceptions.ConnectionError:
            logger.warning("Webhook connection failed for event '%s' (url=%s).", event, url)
        except Exception:
            logger.exception("Unexpected error sending webhook notification for event '%s'.", event)

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
            metrics_str = "\n".join([f"• {k}: {v:.4f}" for k, v in metrics.items()])
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

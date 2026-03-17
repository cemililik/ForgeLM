import requests
import json
import os
from typing import Optional, Dict

class WebhookNotifier:
    """Handles sending training status updates to configured webhook endpoints."""
    def __init__(self, config):
        self.config = config.webhook
        
    def _send(self, title: str, text: str, color: str = "#36a64f") -> None:
        if not self.config:
            return

        url = self.config.url
        if not url and getattr(self.config, "url_env", None):
            url = os.getenv(self.config.url_env)

        if not url:
            return
            
        payload = {
            "attachments": [
                {
                    "title": title,
                    "text": text,
                    "color": color
                }
            ]
        }
        
        try:
            requests.post(
                url,
                data=json.dumps(payload),
                headers={'Content-Type': 'application/json'},
                timeout=5
            )
        except Exception as e:
            print(f"Failed to send webhook notification: {e}")

    def notify_start(self, run_name: str) -> None:
        if self.config and self.config.notify_on_start:
            self._send(
                title=f"🚀 Training Started: {run_name}",
                text="The fine-tuning job has officially started on the cluster.",
                color="#0052cc"
            )

    def notify_success(self, run_name: str, metrics: Dict[str, float]) -> None:
        if self.config and self.config.notify_on_success:
            metrics_str = "\n".join([f"• {k}: {v:.4f}" for k, v in metrics.items()])
            self._send(
                title=f"✅ Training Succeeded: {run_name}",
                text=f"The job completed successfully. Metrics:\n{metrics_str}",
                color="#36a64f"
            )

    def notify_failure(self, run_name: str, reason: str) -> None:
        if self.config and self.config.notify_on_failure:
            self._send(
                title=f"❌ Training Failed: {run_name}",
                text=f"The training job encountered an error or evaluation failed.\nReason: {reason}",
                color="#ff0000"
            )

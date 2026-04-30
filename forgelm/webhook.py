import json
import logging
import os
from typing import Dict, Optional
from urllib.parse import urlparse

import requests

from ._http import HttpSafetyError, _is_private_destination, safe_post

# Public re-export surface — Phase 7 split moved ``_is_private_destination``
# into ``forgelm._http`` but external callers / older code may still import
# it from ``forgelm.webhook``. Listing it in ``__all__`` documents the
# re-export as intentional and silences ruff/Codacy F401 ("imported but
# unused") and Sonar's equivalent rule.
__all__ = ["HttpSafetyError", "WebhookNotifier", "_is_private_destination", "safe_post"]

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
        """POST *payload* to *url* and log any transport / HTTP errors.

        Delegates SSRF / scheme / TLS / redirect / timeout discipline to
        :func:`forgelm._http.safe_post` so every outbound HTTP call site in
        the codebase shares the same policy. Webhook-specific behaviour kept
        here:

        * The webhook config defaults ``timeout`` to 5s for historical
          compatibility — ``safe_post`` is invoked with ``min_timeout=1.0``
          so an existing operator config that uses ``timeout=5`` keeps
          working (every ``http*`` call site outside webhook gets the
          stricter 10s floor).
        * On policy rejection or transport error we log a warning and
          *swallow* — ``notify_*`` is never allowed to fail the training run.
        * Response body suppression on non-2xx — receivers (Slack, Teams)
          sometimes echo the payload, which can carry config-derived secrets.

        Signature is part of the internal Notifier contract: Phase 8 adds
        ``notify_reverted`` / ``notify_awaiting_approval`` that call
        ``self._post_payload(url, payload, event)`` — do not rename or
        reorder arguments without coordinating with that work.
        """
        masked_url = self._mask(url)

        # Resolve TLS verify setting. Default True (strict); allow operator
        # to point at a custom CA bundle.
        ca_bundle = getattr(self.config, "tls_ca_bundle", None)

        # Timeout floor — webhook keeps the historical 1s floor (``safe_post``
        # rejects 0/None unconditionally).
        timeout = getattr(self.config, "timeout", 5)
        if not isinstance(timeout, (int, float)) or timeout < 1:
            logger.warning(
                "Webhook timeout=%r is below the 1s floor; clamping to 5s.",
                timeout,
            )
            timeout = 5

        allow_private = bool(getattr(self.config, "allow_private_destinations", False))

        try:
            resp = safe_post(
                url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=timeout,
                ca_bundle=ca_bundle,
                allow_private=allow_private,
                # Webhook keeps the documented 1s floor; the upstream warning
                # at ``_send`` already flags ``http://`` URLs as plaintext.
                allow_insecure_http=True,
                min_timeout=1.0,
            )
        except HttpSafetyError as exc:
            logger.warning(
                "Refusing to post webhook for event '%s' (url=%s): %s",
                event,
                masked_url,
                exc,
            )
            return
        except requests.exceptions.Timeout:
            logger.warning("Webhook request timed out for event '%s' (url=%s).", event, masked_url)
            return
        except requests.exceptions.ConnectionError:
            logger.warning("Webhook connection failed for event '%s' (url=%s).", event, masked_url)
            return
        except requests.RequestException:
            # ``requests.RequestException`` is the base of the library's
            # transport-error hierarchy (Timeout / ConnectionError / SSLError
            # / TooManyRedirects / etc.) so this single catch covers every
            # network-shaped failure after the more-specific clauses above.
            # We deliberately do **not** add a trailing ``except Exception:``
            # — programming bugs (TypeError, ValueError, attribute errors in
            # payload construction) should propagate so they surface in
            # tests rather than being silently absorbed by the webhook path.
            logger.exception("Unexpected error sending webhook notification for event '%s'.", event)
            return

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
        model_path: Optional[str] = None,
    ) -> None:
        url = self._resolve_url()
        if not url:
            return

        if url.startswith("http://"):
            logger.warning("Webhook URL uses HTTP (not HTTPS). Data will be sent unencrypted.")

        # Sanitize metrics — only include numeric values
        safe_metrics = {k: v for k, v in (metrics or {}).items() if isinstance(v, (int, float))}

        # Generic webhook payload (works for most HTTP receivers).
        # ``model_path`` is included only for ``approval.required`` events;
        # we add the key unconditionally (even as None) to keep the schema
        # stable so downstream consumers can rely on its presence.
        payload = {
            "event": event,
            "run_name": run_name,
            "status": status,
            "metrics": safe_metrics,
            "reason": reason,
            "model_path": model_path,
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
        """Post a training-failure notification.

        ``reason`` is whatever the trainer caught on the failure path —
        typically an exception ``str()`` that may carry filesystem paths,
        configured webhook URLs, or token-shaped strings from a stack
        trace. Run it through :func:`forgelm.data_audit.mask_secrets` so
        AWS / GitHub / Slack / OpenAI / Google / JWT / private-key blocks
        / Azure storage strings are redacted before the payload leaves
        the process.
        """
        if not (self.config and self.config.notify_on_failure):
            return
        masked_reason = self._mask_and_truncate_reason(reason)
        self._send(
            event="training.failure",
            run_name=run_name,
            status="failed",
            title=f"Training Failed: {run_name}",
            text=f"The training job encountered an error or evaluation failed.\n\nReason: {masked_reason}",
            color="#ff0000",
            reason=masked_reason,
        )

    @staticmethod
    def _mask_and_truncate_reason(reason: str) -> str:
        """Mask secrets in *reason* and truncate to 2048 chars.

        Shared between :meth:`notify_failure` and :meth:`notify_reverted`
        so both lifecycle events get the same redaction guarantee. Falls
        back to a hard placeholder when ``data_audit`` cannot be imported
        because shipping an un-scrubbed stack trace is the worse option.
        """
        try:
            from .data_audit import mask_secrets

            masked = mask_secrets(reason)
        except ImportError:
            # data_audit imports stay light enough that this should not
            # happen in practice; if it ever does, refuse to ship the raw
            # reason because we cannot guarantee credentials/tokens have
            # been scrubbed.
            masked = "[REDACTED — secrets masker unavailable]"
        if isinstance(masked, str) and len(masked) > 2048:
            masked = masked[:2048] + "… (truncated)"
        return masked

    def notify_reverted(self, run_name: str, reason: str) -> None:
        """Post an auto-revert notification (lifecycle event ``training.reverted``).

        Distinct from :meth:`notify_failure` so dashboards can separate
        "training crashed" from "training succeeded but eval/safety/judge
        gates rejected the artifact and we deleted the adapters". The
        reason is masked + truncated identically to ``notify_failure`` so
        a leaked stack trace can't smuggle secrets via this path either.
        """
        if not (self.config and self.config.notify_on_failure):
            return
        masked_reason = self._mask_and_truncate_reason(reason)
        self._send(
            event="training.reverted",
            run_name=run_name,
            status="reverted",
            title=f"Training Reverted: {run_name}",
            text=(
                "Auto-revert fired. Generated artifacts were deleted because a "
                "post-training gate (evaluation, safety, judge, or benchmark) "
                f"rejected the run.\n\nReason: {masked_reason}"
            ),
            color="#ff9900",
            reason=masked_reason,
        )

    def notify_awaiting_approval(self, run_name: str, model_path: str) -> None:
        """Post an ``approval.required`` notification (Art. 14 human-in-the-loop).

        Fired right after the audit log records ``human_approval.required``
        so the operator gets a real-time ping instead of having to poll the
        audit JSONL. ``model_path`` is included as plain text — it's a
        local filesystem path that the operator already controls. Model
        weights themselves are *never* in the payload; only the path and
        the run name are.
        """
        if not (self.config and self.config.notify_on_success):
            # Approval is only emitted on otherwise-successful runs, so it
            # piggy-backs on notify_on_success. An operator who silenced
            # success notifications doesn't want approval pings either.
            return
        self._send(
            event="approval.required",
            run_name=run_name,
            status="awaiting_approval",
            title=f"Approval Required: {run_name}",
            text=(
                "Training succeeded and is staged for human review (EU AI Act "
                f"Art. 14). Review the compliance artifacts, then redeploy.\n\n"
                f"Staging path: {model_path}"
            ),
            color="#ffcc00",
            model_path=model_path,
        )

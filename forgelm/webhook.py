import ipaddress
import json
import logging
import os
import socket
from typing import Dict, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger("forgelm.webhook")


def _is_private_destination(host: str) -> bool:
    """Return ``True`` if ``host`` resolves to a private / loopback / link-local IP.

    Used as the SSRF guard: webhook URLs are operator-controlled but the
    process running them often has elevated network access (cloud metadata
    services on 169.254.169.254, internal RFC1918 management UIs, etc.).
    A misconfigured or attacker-controlled config should not trick the
    trainer into sending its run summary to those destinations without
    explicit operator opt-in (``webhook.allow_private_destinations``).
    """
    if not host:
        return False
    # Allow already-IP hostnames (literal in URL) to be checked directly so a
    # config like `https://10.0.0.5/hook` is caught even with no DNS at all.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
    try:
        # Pre-resolve so a hostname that points at a private IP still trips.
        addrinfo = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        # DNS failure → not a private destination by our definition. Let
        # `requests` produce its natural ConnectionError downstream so the
        # operator gets the real "could not resolve host" message instead
        # of an SSRF-shaped refusal that hides the typo.
        return False
    for _family, _type, _proto, _canon, sockaddr in addrinfo:
        ip_str = sockaddr[0]
        try:
            resolved = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            resolved.is_private
            or resolved.is_loopback
            or resolved.is_link_local
            or resolved.is_reserved
            or resolved.is_multicast
        ):
            return True
    return False


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

        Hardened:

        - SSRF guard: refuses non-loopback private / link-local destinations
          unless ``webhook.allow_private_destinations`` is explicitly true.
        - TLS: passes ``verify=True`` to ``requests.post`` so an attacker on
          the egress path can't strip cert validation by setting
          ``verify=False`` somewhere upstream. Operator can supply a custom
          CA bundle via ``webhook.tls_ca_bundle`` (forwarded as ``verify``).
        - Timeout floor: refuses ``timeout < 1`` since ``requests`` honours
          ``0`` as "block forever, no timeout" — hangs the trainer on a
          dead webhook.
        """
        masked_url = self._mask(url)

        # SSRF guard — runs before the request so an internal-IP webhook
        # never receives the payload.
        if not getattr(self.config, "allow_private_destinations", False):
            host = urlparse(url).hostname or ""
            if _is_private_destination(host):
                logger.warning(
                    "Refusing to post webhook for event '%s' to private/loopback destination "
                    "(url=%s). Set webhook.allow_private_destinations=true to opt in.",
                    event,
                    masked_url,
                )
                return

        # Resolve TLS verify setting. Default True (strict); allow operator
        # to point at a custom CA bundle.
        verify = getattr(self.config, "tls_ca_bundle", None) or True

        # Timeout floor — refuse 0/None which `requests` treats as
        # "no timeout".
        timeout = getattr(self.config, "timeout", 5)
        if not isinstance(timeout, (int, float)) or timeout < 1:
            logger.warning(
                "Webhook timeout=%r is below the 1s floor; clamping to 5s.",
                timeout,
            )
            timeout = 5

        try:
            resp = requests.post(
                url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=timeout,
                verify=verify,
                # Disable redirect-following: the URL was SSRF-validated
                # against the resolved IP literal up-front, but a 30x to a
                # private destination would bypass that check entirely.
                allow_redirects=False,
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
        try:
            from .data_audit import mask_secrets

            masked_reason = mask_secrets(reason)
        except ImportError:
            # data_audit imports stay light enough that this should not
            # happen in practice; if it ever does, refuse to ship the raw
            # reason because we cannot guarantee credentials/tokens have
            # been scrubbed. A redacted placeholder is far less useful
            # than a masked stack trace, but it's the only safe fallback.
            masked_reason = "[REDACTED — secrets masker unavailable]"
        if isinstance(masked_reason, str) and len(masked_reason) > 2048:
            masked_reason = masked_reason[:2048] + "… (truncated)"
        self._send(
            event="training.failure",
            run_name=run_name,
            status="failed",
            title=f"Training Failed: {run_name}",
            text=f"The training job encountered an error or evaluation failed.\n\nReason: {masked_reason}",
            color="#ff0000",
            reason=masked_reason,
        )

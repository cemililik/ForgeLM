"""Centralized HTTP discipline for outbound HTTP calls (GET / HEAD / POST).

Extracted from ``webhook._post_payload`` to enforce SSRF guard, redirect
refusal, ``http://`` refusal, timeout floor, and secret-mask error reasons
across every outbound HTTP call site in the codebase (webhook, judge,
synthetic, doctor).  POST traffic goes through :func:`safe_post`; read-side
GET / HEAD traffic goes through :func:`safe_get` (added in Wave 2a Round-2
when ``forgelm doctor`` migrated off ``urllib.request.urlopen``).

Future call sites (telemetry, registry pings, etc.) MUST go through one of
those helpers rather than calling ``requests.{post,get,head}`` (or
``urllib.request.urlopen`` / ``httpx.*``) directly — the CI acceptance
gate ``lint-http-discipline`` greps ``forgelm/`` for those patterns and
fails on any hit outside ``forgelm/_http.py``:

    grep -rn "requests\\.\\(post\\|get\\|head\\)\\(" forgelm/ | grep -v _http\\.py
    grep -rn "urllib\\.request\\.urlopen\\(" forgelm/ | grep -v _http\\.py

both must stay empty.

Policy summary (each enforced before the network call):

* **Scheme** — ``https://`` required by default; ``http://`` rejected unless
  the caller passes ``allow_insecure_http=True`` (only the operator-blessed
  webhook path uses this; judge / synthetic always require TLS).
* **SSRF** — RFC1918, loopback, link-local (incl. cloud IMDS at
  ``169.254.169.254``), reserved, and multicast destinations are blocked
  unless ``allow_private=True``. Hostnames are pre-resolved via
  ``socket.getaddrinfo`` so a DNS name pointing at a private IP also trips.
* **Timeout floor** — defaults to 10s; callers can pass ``min_timeout`` to
  lower the floor (the webhook path uses 1s to preserve historical
  behaviour). ``timeout=0`` / ``None`` is always rejected — ``requests``
  honours those as "block forever".
* **Redirects** — ``allow_redirects=False`` always. The SSRF guard runs
  against the *initial* hostname; following a 30x to a private IP would
  bypass it.
* **TLS** — ``verify=True`` by default; pass ``ca_bundle="/path/..."`` for a
  custom CA store (corporate MITM CA on regulated estates).
* **Header masking** — ``Authorization`` / ``X-API-Key`` values are redacted
  from the warning log emitted when the request raises.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger("forgelm._http")


class HttpSafetyError(Exception):
    """Policy-level rejection of an outbound HTTP request.

    Distinct from :class:`requests.RequestException` so callers can tell a
    refused-by-policy URL (operator misconfiguration — surface to the user)
    apart from a transport failure (network blip — log + continue).
    """


_MASK_HEADER_NAMES = frozenset({"authorization", "x-api-key", "proxy-authorization"})


def _is_private_destination(host: str) -> bool:
    """Return ``True`` when *host* resolves to a non-public-internet IP.

    DNS pre-resolution catches hostnames that happen to point at RFC1918 /
    link-local / loopback addresses, so a ``http://internal.corp/`` URL is
    rejected even when no IP literal is present in the URL itself.

    Re-exported from :mod:`forgelm.webhook` (where it originated) for
    backwards compatibility — existing tests / external consumers continue
    to import the symbol from the webhook module.
    """
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
    try:
        addrinfo = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        # DNS failure → not classified as private; let `requests` produce
        # its natural ConnectionError downstream so the operator sees the
        # real "could not resolve host" message instead of an SSRF-shaped
        # refusal that hides the typo.
        return False
    for _family, _type, _proto, _canon, sockaddr in addrinfo:
        try:
            resolved = ipaddress.ip_address(sockaddr[0])
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


def _mask_netloc(url: str) -> str:
    """Return ``scheme://host`` with userinfo / path / query stripped.

    Used in policy-rejection error messages and warning logs so we never
    echo the secret-bearing tail of a Slack / Teams / Discord webhook URL
    (which carries credentials in the path) into operator-visible output.
    """
    try:
        parts = urlparse(url)
    except (ValueError, TypeError):
        return "<unparseable-url>"
    if not parts.scheme or not parts.netloc:
        return "<malformed-url>"
    return f"{parts.scheme}://{parts.hostname or 'unknown-host'}"


def _mask_secrets_in_text(text: str, headers: Optional[Dict[str, str]]) -> str:
    """Redact known secret-bearing header values from *text*.

    ``requests`` exception strings sometimes include the request URL or
    header dump; we strip ``Authorization`` / ``X-API-Key`` / proxy auth
    values before logging so a transport-layer error doesn't leak the
    bearer token into the trainer's stderr.
    """
    if not text or not headers:
        return text
    masked = text
    for name, value in headers.items():
        if not value or not isinstance(value, str):
            continue
        if name.lower() in _MASK_HEADER_NAMES:
            masked = masked.replace(value, "[REDACTED]")
    return masked


def safe_post(
    url: str,
    *,
    json: Any = None,
    data: Any = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 10.0,
    verify: Any = True,
    ca_bundle: Optional[str] = None,
    allow_insecure_http: bool = False,
    allow_private: bool = False,
    min_timeout: float = 10.0,
) -> requests.Response:
    """Disciplined outbound POST; raises early on policy violation.

    Args:
        url: Target URL. Must be ``http://`` or ``https://``.
        json: Body serialized as JSON by ``requests``. Mutually exclusive
            with ``data``; passing both is a caller bug, not enforced here.
        data: Pre-serialized body (e.g. ``json.dumps(payload)`` for the
            webhook path that already encodes its own payload).
        headers: Outbound headers. ``Authorization`` / ``X-API-Key`` values
            are masked in the failure log.
        timeout: Per-request timeout in seconds. Must be ``>= min_timeout``.
        verify: Forwarded as ``requests``'s ``verify=`` argument; passing
            ``False`` is allowed but discouraged. ``ca_bundle`` overrides.
        ca_bundle: Path to a custom CA bundle. When non-empty, takes
            precedence over ``verify``.
        allow_insecure_http: Set ``True`` only for paths where the operator
            has explicitly opted into ``http://`` (currently: webhook with a
            documented warning at the call site). Judge and synthetic must
            never set this — they handle bearer tokens.
        allow_private: Set ``True`` to bypass the SSRF guard. Required for
            in-cluster Slack proxies / on-prem monitoring sinks.
        min_timeout: Lower bound for ``timeout``. Defaults to ``10.0``;
            ``webhook._post_payload`` passes ``1.0`` to keep its historical
            behaviour without forcing every webhook user to bump their
            timeout setting.

    Returns:
        The :class:`requests.Response` from the underlying call. The caller
        is responsible for inspecting ``response.ok`` / ``status_code``.

    Raises:
        HttpSafetyError: On policy violation — ``http://`` without opt-in,
            unsupported scheme, sub-floor timeout, or private destination
            without opt-in.
        requests.RequestException: On transport / TLS / network failure.
            Headers are masked in the warning log before the re-raise.
    """
    parsed = urlparse(url)

    # Scheme policy.
    if parsed.scheme == "http":
        if not allow_insecure_http:
            raise HttpSafetyError(  # NOSONAR — error string mentions "http://" by design (operator-facing rejection message)
                f"http:// blocked (use https://); url={_mask_netloc(url)}"
            )
    elif parsed.scheme != "https":
        raise HttpSafetyError(f"Unsupported URL scheme {parsed.scheme!r}; only http(s) allowed.")

    # SSRF guard.
    host = parsed.hostname or ""
    if not allow_private and _is_private_destination(host):
        raise HttpSafetyError(f"Private/loopback/IMDS destination blocked: host={host or '<empty>'}")

    # Timeout floor — `requests` treats 0 / None as "no timeout" which can
    # hang the trainer on a dead endpoint.
    if not isinstance(timeout, (int, float)) or timeout < min_timeout:
        raise HttpSafetyError(f"Timeout below {min_timeout}s floor: timeout={timeout!r}")

    # Resolve TLS verify setting. ca_bundle (when set) wins over verify.
    verify_param: Any = ca_bundle if ca_bundle else verify

    try:
        return requests.post(
            url,
            json=json,
            data=data,
            headers=headers,
            timeout=timeout,
            verify=verify_param,
            # Redirect-following would bypass the up-front SSRF check —
            # a 30x to 169.254.169.254 from an attacker-controlled host
            # would otherwise leak the request payload to IMDS.
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        masked_reason = _mask_secrets_in_text(str(exc), headers)
        logger.warning(
            "safe_post failed url=%s reason=%s",
            _mask_netloc(url),
            masked_reason[:200],
        )
        raise


def safe_get(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 10.0,
    verify: Any = True,
    ca_bundle: Optional[str] = None,
    allow_insecure_http: bool = False,
    allow_private: bool = False,
    min_timeout: float = 5.0,
    method: str = "GET",
) -> requests.Response:
    """Disciplined outbound GET / HEAD; raises early on policy violation.

    Mirrors :func:`safe_post`'s policy contract (scheme / SSRF / timeout
    floor / redirect refusal / TLS verify / header secret-masking) for
    read-side calls.  Used by ``forgelm doctor`` for the HuggingFace Hub
    reachability probe and by any future probe / telemetry / registry
    ping that needs an outbound GET or HEAD.

    Args:
        url: Target URL. Must be ``http://`` or ``https://``.
        headers: Outbound headers. ``Authorization`` / ``X-API-Key`` values
            are masked in the failure log.
        timeout: Per-request timeout in seconds. Must be ``>= min_timeout``.
        verify: Forwarded as ``requests``'s ``verify=`` argument.
        ca_bundle: Path to a custom CA bundle. When non-empty, takes
            precedence over ``verify``.
        allow_insecure_http: Set ``True`` only for paths where the operator
            has explicitly opted into ``http://``.
        allow_private: Set ``True`` to bypass the SSRF guard. Required for
            in-cluster mirrors / on-prem registry endpoints.
        min_timeout: Lower bound for ``timeout``. Defaults to ``5.0``
            (read probes are typically cheaper than POST bodies).
        method: ``"GET"`` (default) or ``"HEAD"``. The doctor's HF Hub
            probe uses HEAD to skip body download.

    Returns:
        The :class:`requests.Response` from the underlying call. The caller
        is responsible for inspecting ``response.ok`` / ``status_code``.

    Raises:
        HttpSafetyError: On policy violation — ``http://`` without opt-in,
            unsupported scheme, sub-floor timeout, private destination
            without opt-in, or unsupported method.
        requests.RequestException: On transport / TLS / network failure.
            Headers are masked in the warning log before the re-raise.
    """
    parsed = urlparse(url)

    # Scheme policy.
    if parsed.scheme == "http":
        if not allow_insecure_http:
            raise HttpSafetyError(  # NOSONAR — operator-facing rejection
                f"http:// blocked (use https://); url={_mask_netloc(url)}"
            )
    elif parsed.scheme != "https":
        raise HttpSafetyError(f"Unsupported URL scheme {parsed.scheme!r}; only http(s) allowed.")

    # SSRF guard.
    host = parsed.hostname or ""
    if not allow_private and _is_private_destination(host):
        raise HttpSafetyError(f"Private/loopback/IMDS destination blocked: host={host or '<empty>'}")

    # Timeout floor.
    if not isinstance(timeout, (int, float)) or timeout < min_timeout:
        raise HttpSafetyError(f"Timeout below {min_timeout}s floor: timeout={timeout!r}")

    # Method policy — only GET / HEAD allowed (read-side helper).
    method_upper = method.upper()
    if method_upper not in ("GET", "HEAD"):
        raise HttpSafetyError(f"safe_get only supports GET / HEAD, got {method!r}.")

    verify_param: Any = ca_bundle if ca_bundle else verify

    try:
        return requests.request(
            method_upper,
            url,
            headers=headers,
            timeout=timeout,
            verify=verify_param,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        masked_reason = _mask_secrets_in_text(str(exc), headers)
        logger.warning(
            "safe_get failed url=%s method=%s reason=%s",
            _mask_netloc(url),
            method_upper,
            masked_reason[:200],
        )
        raise

"""Issue #14 regression tests — DNS-rebinding TOCTOU hardening for the
webhook / judge / synthetic SSRF guard.

Pre-fix: ``_is_private_destination()`` ran a DNS lookup, then
``requests.post()`` ran ANOTHER DNS lookup at connect time.  An
attacker-controlled DNS server with TTL=0 could return a public IP on
the first lookup (passing the guard) and a private IP on the second
(when ``requests`` connected), leaking the payload + bearer token to a
private destination.

Post-fix: ``_resolve_safe_destination()`` resolves the hostname once and
the call site reuses the returned IP literal in the URL.  The original
hostname is propagated via the ``Host`` header and (for HTTPS) the SNI
extension of ``requests_toolbelt.adapters.host_header_ssl.
HostHeaderSSLAdapter``, so virtual-hosting endpoints and certificate
validation still work.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestResolveSafeDestination:
    """Unit-level coverage of the resolver helper."""

    def test_public_hostname_returns_first_public_ip(self):
        from forgelm import _http

        # Two public-A addrinfo entries.
        with patch.object(
            _http.socket,
            "getaddrinfo",
            return_value=[
                (0, 0, 0, "", ("8.8.8.8", 0)),
                (0, 0, 0, "", ("8.8.4.4", 0)),
            ],
        ):
            ip, err = _http._resolve_safe_destination("hooks.example.com")
        assert err is None
        assert ip == "8.8.8.8"

    def test_private_ip_in_resolution_blocks(self):
        """Even one private answer in addrinfo flips the verdict to blocked."""
        from forgelm import _http

        with patch.object(
            _http.socket,
            "getaddrinfo",
            return_value=[
                (0, 0, 0, "", ("8.8.8.8", 0)),
                (0, 0, 0, "", ("10.0.0.1", 0)),  # NOSONAR RFC1918 — guard fixture
            ],
        ):
            ip, err = _http._resolve_safe_destination("attacker.example.com")
        assert ip is None
        assert "Private" in err and "IMDS" in err

    def test_dns_failure_blocks_with_reason(self):
        from forgelm import _http

        with patch.object(_http.socket, "getaddrinfo", side_effect=_http.socket.gaierror("nodename")):
            ip, err = _http._resolve_safe_destination("no-such.example.com")
        assert ip is None
        assert err.startswith("DNS resolution failed")

    def test_empty_host_blocks(self):
        from forgelm._http import _resolve_safe_destination

        ip, err = _resolve_safe_destination("")
        assert ip is None
        assert err == "empty host"

    def test_public_ip_literal_passes_through(self):
        from forgelm._http import _resolve_safe_destination

        ip, err = _resolve_safe_destination("8.8.8.8")
        assert err is None
        assert ip == "8.8.8.8"

    def test_private_ip_literal_blocks(self):
        from forgelm._http import _resolve_safe_destination

        ip, err = _resolve_safe_destination("169.254.169.254")  # NOSONAR AWS IMDS — guard fixture
        assert ip is None
        assert "Private" in err


class TestDnsRebindingClosed:
    """Behavioural test: a TOCTOU-style rebinding cannot leak the payload.

    Simulates a DNS server that returns a public IP on the first lookup
    (the guard's call) and a private IP on a hypothetical second lookup
    (what the old code path would have invoked from inside requests).
    The hardened path must call ``getaddrinfo`` exactly once and pin the
    public IP into the outbound URL.
    """

    def test_getaddrinfo_called_exactly_once_and_pins_public_ip(self):
        from forgelm import _http

        # First call: public. If the code ever called a second time
        # (the TOCTOU window), it would get the IMDS address.  The
        # assertion below asserts the second call never happens.
        responses = iter(
            [
                [(0, 0, 0, "", ("8.8.8.8", 0))],  # 1st call — public
                [(0, 0, 0, "", ("169.254.169.254", 0))],  # 2nd call — would be IMDS  # NOSONAR
            ]
        )

        def fake_resolve(*_args, **_kwargs):
            try:
                return next(responses)
            except StopIteration:
                pytest.fail("getaddrinfo called more than once — DNS rebinding window is still open")

        with (
            patch.object(_http.socket, "getaddrinfo", side_effect=fake_resolve) as resolve_mock,
            patch.object(_http.requests.Session, "post") as mock_post,
        ):
            mock_post.return_value = MagicMock(ok=True, status_code=200)
            _http.safe_post("https://hooks.example.com/abc", json={}, timeout=10.0)

        assert resolve_mock.call_count == 1, (
            f"DNS rebinding fix requires exactly one resolve per safe_post call, got {resolve_mock.call_count}"
        )
        # The URL handed to Session.post must be the IP literal, not the hostname.
        called_url = mock_post.call_args.args[0] if mock_post.call_args.args else mock_post.call_args.kwargs.get("url")
        assert called_url == "https://8.8.8.8/abc", (
            f"safe_post must rebuild the URL with the resolved public IP literal; got {called_url!r}"
        )

    def test_host_header_preserved_after_ip_pin(self):
        """The original hostname must travel via ``Host`` header so the
        upstream virtual host receives the right request line."""
        from forgelm import _http

        with (
            patch.object(_http.socket, "getaddrinfo", return_value=[(0, 0, 0, "", ("8.8.8.8", 0))]),
            patch.object(_http.requests.Session, "post") as mock_post,
        ):
            mock_post.return_value = MagicMock(ok=True, status_code=200)
            _http.safe_post(
                "https://hooks.example.com/abc",
                json={},
                headers={"Authorization": "Bearer secret"},  # noqa: S105 — test fixture
                timeout=10.0,
            )

        headers = mock_post.call_args.kwargs["headers"]
        assert headers["Host"] == "hooks.example.com"
        # The opt-in auth header must be preserved alongside Host.
        assert headers["Authorization"] == "Bearer secret"

    def test_https_uses_host_header_ssl_adapter(self):
        """For HTTPS the Session must mount HostHeaderSSLAdapter so SNI
        and cert validation are performed against the original hostname,
        not the IP literal in the URL."""
        from forgelm import _http

        with patch.object(_http.socket, "getaddrinfo", return_value=[(0, 0, 0, "", ("8.8.8.8", 0))]):
            session = _http._pinned_session("https")
        # Ensure an https://-mounted adapter exists and is the HostHeaderSSLAdapter.
        adapter = session.get_adapter("https://example.com/")
        from requests_toolbelt.adapters.host_header_ssl import HostHeaderSSLAdapter

        assert isinstance(adapter, HostHeaderSSLAdapter)

    def test_http_session_does_not_mount_ssl_adapter(self):
        """The HTTP branch (operator opt-in via allow_insecure_http) must
        not need the SSL adapter — no SNI involved."""
        from forgelm import _http

        session = _http._pinned_session("http")
        # Default HTTPAdapter, not HostHeaderSSLAdapter, on the http:// prefix.
        adapter = session.get_adapter("http://example.com/")
        from requests_toolbelt.adapters.host_header_ssl import HostHeaderSSLAdapter

        assert not isinstance(adapter, HostHeaderSSLAdapter)

    def test_allow_private_bypasses_pinning(self):
        """``allow_private=True`` is the documented in-cluster/internal
        destination opt-in; the legacy ``requests.post`` flow runs so
        internal DNS / split-horizon resolution still works."""
        from forgelm import _http

        with (
            patch.object(_http.socket, "getaddrinfo") as resolve_mock,
            patch.object(_http.requests, "post") as mock_post,
            patch.object(_http.requests.Session, "post") as session_post_mock,
        ):
            mock_post.return_value = MagicMock(ok=True, status_code=200)
            _http.safe_post(
                "https://internal.corp.local/hook",
                json={},
                timeout=10.0,
                allow_private=True,
            )

        resolve_mock.assert_not_called()  # No DNS pre-resolve in the opt-in path
        session_post_mock.assert_not_called()  # No Session.post either
        mock_post.assert_called_once()  # Legacy requests.post path


class TestIpv6PinningBuildsBracketedUrl:
    """IPv6 IP literals must be bracketed in the rebuilt URL per RFC 3986."""

    def test_ipv6_url_is_bracketed(self):
        from forgelm import _http

        with (
            patch.object(_http.socket, "getaddrinfo", return_value=[(0, 0, 0, "", ("2606:4700:4700::1111", 0))]),
            patch.object(_http.requests.Session, "post") as mock_post,
        ):
            mock_post.return_value = MagicMock(ok=True, status_code=200)
            _http.safe_post("https://v6.example.com/abc", json={}, timeout=10.0)

        called_url = mock_post.call_args.args[0]
        assert called_url == "https://[2606:4700:4700::1111]/abc"


class TestSafeGetPinning:
    """``safe_get`` mirrors ``safe_post`` for the same hardening contract."""

    def test_safe_get_pins_url_and_sets_host_header(self):
        from forgelm import _http

        with (
            patch.object(_http.socket, "getaddrinfo", return_value=[(0, 0, 0, "", ("8.8.8.8", 0))]),
            patch.object(_http.requests.Session, "request") as mock_request,
        ):
            mock_request.return_value = MagicMock(ok=True, status_code=200)
            _http.safe_get("https://hub.example.com/api/models", timeout=10.0)

        # Session.request("GET", url, ...)
        method = mock_request.call_args.args[0]
        url = mock_request.call_args.args[1]
        headers = mock_request.call_args.kwargs["headers"]

        assert method == "GET"
        assert url == "https://8.8.8.8/api/models"
        assert headers["Host"] == "hub.example.com"

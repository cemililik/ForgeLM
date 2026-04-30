"""Shared test fixtures and utilities for ForgeLM tests."""

import os

import pytest

# Re-export the canonical factory so legacy imports continue to work.
# New tests should prefer the ``minimal_config`` pytest fixture below.
# We import via the ``_helpers`` package located alongside this conftest;
# pytest's default ``prepend`` import mode puts ``tests/`` on sys.path,
# making ``_helpers`` directly importable. We also expose the same
# binding under ``tests.conftest`` for callers that use the fully
# qualified path (e.g. ``from tests.conftest import minimal_config``).
from _helpers.factories import minimal_config  # noqa: F401  (re-export)


@pytest.fixture(name="minimal_config")
def _factory_fixture():
    """Provide the ``minimal_config`` factory to tests via fixture injection.

    The fixture returns the *factory itself*, not a pre-built dict, so tests
    can call ``minimal_config(training={"trainer_type": "dpo"})`` to build
    customized configs without re-importing the helper.
    """
    from _helpers.factories import minimal_config as _factory

    return _factory


@pytest.fixture(autouse=True)
def _pin_audit_operator(monkeypatch):
    """Pin a deterministic operator identity for the entire test session.

    Closure plan Faz 3 makes ``AuditLogger.__init__`` raise ``ConfigError``
    when no operator can be derived. Most tests instantiate ``AuditLogger``
    indirectly (training manifests, governance reports). To keep them green
    on minimal CI runners — where ``$USER`` may be unset and getpass may
    fail under sandboxed users — we pin ``FORGELM_OPERATOR`` here.

    Tests that exercise the resolution logic itself (the
    ``TestAuditLoggerOperatorIdentity`` class) explicitly clear this
    via ``monkeypatch.delenv`` inside the test body.
    """
    monkeypatch.setenv("FORGELM_OPERATOR", os.environ.get("FORGELM_OPERATOR") or "test-operator")

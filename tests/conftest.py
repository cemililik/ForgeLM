"""Shared test fixtures and utilities for ForgeLM tests."""

import os

import pytest


def minimal_config(**overrides):
    """Create a minimal valid ForgeConfig dict for testing."""
    data = {
        "model": {"name_or_path": "org/model"},
        "lora": {},
        "training": {},
        "data": {"dataset_name_or_path": "org/dataset"},
    }
    data.update(overrides)
    return data


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

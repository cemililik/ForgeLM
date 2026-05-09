"""Shared test fixtures and utilities for ForgeLM tests."""

import os

import pytest

# Re-export the canonical factory so legacy imports continue to work.
# New tests should prefer the ``minimal_config`` pytest fixture below.
# We use the fully qualified ``tests._helpers`` path so the import resolves
# under both ``--import-mode=prepend`` (pytest default) and the recommended
# ``--import-mode=importlib``. The fixture itself is re-exposed via
# ``tests.conftest`` for callers that prefer the dotted path.
from tests._helpers.factories import minimal_config  # noqa: F401  (re-export)


@pytest.fixture(name="minimal_config")
def _factory_fixture():
    """Provide the ``minimal_config`` factory to tests via fixture injection.

    The fixture returns the *factory itself*, not a pre-built dict, so tests
    can call ``minimal_config(training={"trainer_type": "dpo"})`` to build
    customized configs without re-importing the helper.
    """
    from tests._helpers.factories import minimal_config as _factory

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


@pytest.fixture(autouse=True)
def _isolate_wizard_state(request, tmp_path_factory, monkeypatch):
    """B10 — keep wizard XDG state out of the developer's real ``~/.cache``.

    Any test under ``tests/test_wizard_*`` (or anything that ends up
    invoking ``forgelm.wizard._save_wizard_state`` indirectly) writes
    a YAML to ``$XDG_CACHE_HOME/forgelm/wizard_state.yaml``. Without
    isolation a contributor running ``pytest`` would have their real
    in-flight wizard snapshot clobbered.

    We redirect ``XDG_CACHE_HOME`` to a per-test tmp dir for every
    wizard-flavoured test file. The ``test_wizard_phase22`` module
    already has its own ``isolated_state_dir`` fixture; this one is
    additive — they coexist because they both monkeypatch the same
    env var, and the more-specific fixture takes precedence on the
    tests that explicitly request it.
    """
    test_path = str(getattr(request.node, "fspath", "") or "")
    if "test_wizard_" not in test_path and "test_phase12_5" not in test_path:
        return
    isolated = tmp_path_factory.mktemp("wizard_xdg_isolated")
    monkeypatch.setenv("XDG_CACHE_HOME", str(isolated))

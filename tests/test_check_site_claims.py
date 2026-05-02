"""Tests for the site-as-tested-surface guard (``tools/check_site_claims.py``).

Phase 25 / Theme α. The guard catches drift between site/*.html claims and
the Python sources of truth (compliance artefacts, quickstart templates,
GPU profile count, pyproject version). These tests pin the AST-extraction
helpers so a refactor of the source modules cannot silently break the
guard, and exercise the version-comparison rule end-to-end against the
repo's own pyproject.toml.

The script lives under ``tools/`` rather than ``forgelm/`` because it is a
build-time check; we import it via ``importlib`` from the repo root so the
test suite stays decoupled from any sys.path manipulation.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tools" / "check_site_claims.py"


def _load_module():
    """Import tools/check_site_claims.py as a module without modifying sys.path.

    The module gets registered in ``sys.modules`` so that
    ``@dataclasses.dataclass`` on classes defined inside it can resolve the
    owning module via ``cls.__module__`` (Python 3.11's dataclass plumbing
    raises ``AttributeError`` otherwise).
    """
    name = "_forgelm_check_site_claims_under_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def csc():
    return _load_module()


def test_pyproject_version_returns_a_pep440_string(csc) -> None:
    """The version reader must surface the ``[project] version`` literally."""
    version = csc.pyproject_version()
    assert isinstance(version, str)
    assert version  # non-empty
    # We don't pin the exact version (it changes each release) but the shape
    # should be PEP 440 minor.major.patch[suffix].
    parts = version.split(".")
    assert len(parts) >= 3, f"unexpected pyproject version shape: {version!r}"


def test_compliance_artifact_filenames_includes_annex(csc) -> None:
    """``export_compliance_artifacts`` must keep emitting annex_iv_metadata.json."""
    names = csc.compliance_artifact_filenames()
    assert "annex_iv_metadata.json" in names, (
        "annex_iv_metadata.json is the canonical Article 11 artefact; if it "
        "moved, update site/compliance.html and this guard together."
    )


def test_quickstart_template_set_matches_registry(csc) -> None:
    """The AST-derived template set must match :data:`forgelm.quickstart.TEMPLATES`."""
    from forgelm.quickstart import TEMPLATES

    assert csc.quickstart_template_names() == set(TEMPLATES.keys())


def test_gpu_pricing_count_is_positive(csc) -> None:
    """The trainer's _GPU_PRICING dict must be non-empty for the home stat."""
    assert csc.gpu_pricing_count() > 0


def test_version_tuple_orders_rc_below_release(csc) -> None:
    """Pre-release versions must sort below the matching public release."""
    rc = csc._version_tuple("0.5.1rc1")
    release = csc._version_tuple("0.5.1")
    assert rc is not None and release is not None
    assert rc < release


def test_version_tuple_rejects_garbage(csc) -> None:
    """Malformed version strings must yield None (caller treats as drift)."""
    assert csc._version_tuple("not-a-version") is None
    assert csc._version_tuple("0.5") is None


def test_check_version_accepts_released_below_dev_cycle(csc, monkeypatch) -> None:
    """A released ``0.5.0`` mention must pass when pyproject is on ``0.5.1rc1``."""
    monkeypatch.setattr(csc, "pyproject_version", lambda: "0.5.1rc1")
    monkeypatch.setattr(csc, "site_version_mentions", lambda: {"0.5.0"})
    result = csc.check_version()
    assert result.ok, result.render()


def test_check_version_rejects_future_release(csc, monkeypatch) -> None:
    """A ``0.6.0`` mention must fail when pyproject is on ``0.5.1rc1``."""
    monkeypatch.setattr(csc, "pyproject_version", lambda: "0.5.1rc1")
    monkeypatch.setattr(csc, "site_version_mentions", lambda: {"0.6.0"})
    result = csc.check_version()
    assert not result.ok
    assert "0.6.0" in result.render()


def test_run_checks_clean_repo_passes(csc) -> None:
    """End-to-end: every check on the unmodified repo must report OK.

    Reviewers should treat a failure here as "either the site drifted or the
    Python source drifted — fix one, not the test."
    """
    results = csc.run_checks()
    failures = [r for r in results if not r.ok]
    assert not failures, "site claims drift:\n" + "\n".join(r.render() for r in failures)

"""Phase 19 — Library API integration tests.

Verifies the public Python surface that
``docs/analysis/code_reviews/library-api-design-202605021414.md`` pins:

- Stable symbol set matches ``forgelm.__all__``.
- Lazy-import discipline holds — ``import forgelm`` does NOT pull
  ``torch`` / ``transformers`` / ``trl``.
- Attribute access through the ``__getattr__`` hook returns the
  expected source object and caches it for subsequent accesses.
- ``dir(forgelm)`` lists the full public surface (IDE autocomplete +
  ``help(forgelm)`` discovery).
- ``forgelm/py.typed`` PEP 561 marker is shipped with the package.
- ``__api_version__`` follows the contract in ``forgelm/_version.py``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Stable surface
# ---------------------------------------------------------------------------


_EXPECTED_STABLE_SYMBOLS = {
    # Versioning.
    "__version__",
    "__api_version__",
    # Configuration.
    "load_config",
    "ForgeConfig",
    "ConfigError",
    # Training entry point.
    "ForgeTrainer",
    "TrainResult",
    # Data preparation + audit.
    "prepare_dataset",
    "get_model_and_tokenizer",
    "audit_dataset",
    "AuditReport",
    # PII / secrets / dedup utility belt.
    "detect_pii",
    "mask_pii",
    "detect_secrets",
    "mask_secrets",
    "compute_simhash",
    # Compliance / audit log.
    "AuditLogger",
    "verify_audit_log",
    "VerifyResult",
    # Phase 36 verification toolbelt.
    "verify_annex_iv_artifact",
    "VerifyAnnexIVResult",
    "verify_gguf",
    "VerifyGgufResult",
    # Webhook notifier.
    "WebhookNotifier",
    # Auxiliary.
    "setup_authentication",
    "manage_checkpoints",
    "run_benchmark",
    "BenchmarkResult",
    "SyntheticDataGenerator",
}


class TestPublicSurface:
    def test_all_exposes_every_documented_symbol(self) -> None:
        import forgelm

        actual = set(forgelm.__all__)
        missing = _EXPECTED_STABLE_SYMBOLS - actual
        extra = actual - _EXPECTED_STABLE_SYMBOLS
        assert not missing, f"forgelm.__all__ is missing documented symbols: {sorted(missing)}"
        assert not extra, f"forgelm.__all__ has undocumented additions: {sorted(extra)}"

    def test_dir_lists_full_surface_before_any_attribute_access(self) -> None:
        """dir(forgelm) MUST list every public name even before any
        lazy attribute has been accessed (IDE autocomplete + help())."""
        # We intentionally do NOT delete forgelm from sys.modules here:
        # other tests in the suite rely on submodule attributes (e.g.
        # `forgelm.model`) being populated by their `import forgelm.X`
        # statements.  The contract this test pins — "every name in
        # __all__ is in dir(forgelm)" — holds regardless of which lazy
        # symbols have been resolved already, because __dir__ reads
        # from __all__ + globals().
        import forgelm

        listing = dir(forgelm)
        for name in _EXPECTED_STABLE_SYMBOLS:
            assert name in listing, f"dir(forgelm) is missing public symbol {name!r}"

    def test_py_typed_marker_present(self) -> None:
        """PEP 561: forgelm/py.typed must ship in the wheel + source."""
        import forgelm

        marker = Path(forgelm.__file__).parent / "py.typed"
        assert marker.is_file(), f"forgelm/py.typed marker is missing at {marker}"

    def test_api_version_is_semver_string(self) -> None:
        from forgelm import __api_version__

        parts = __api_version__.split(".")
        assert len(parts) == 3, f"__api_version__ should be MAJOR.MINOR.PATCH, got {__api_version__!r}"
        for p in parts:
            assert p.isdigit(), f"__api_version__ part {p!r} is not numeric (got {__api_version__!r})"

    def test_attribute_typo_raises_attribute_error_not_import_error(self) -> None:
        """A typo on a public attribute must surface as AttributeError
        (not ImportError) so consumers get a clean error message."""
        import forgelm

        with pytest.raises(AttributeError, match="forgelm"):
            _ = forgelm.ForeTrainer  # typo


# ---------------------------------------------------------------------------
# Lazy-import discipline
# ---------------------------------------------------------------------------


class TestLazyImportDiscipline:
    def test_import_forgelm_does_not_pull_torch(self) -> None:
        """`import forgelm` cold MUST NOT pull torch / transformers /
        trl into sys.modules.  Operators running `forgelm doctor` on a
        machine without torch installed would otherwise crash before
        the doctor probe runs.
        """
        # Use a subprocess so a previously-imported torch in this test
        # process doesn't pollute the assertion.
        script = (
            "import sys; "
            "import forgelm; "
            "loaded = sorted(m for m in sys.modules if m in {'torch', 'transformers', 'trl', 'datasets', 'peft'}); "
            "print(','.join(loaded))"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"subprocess crashed: {result.stderr}"
        loaded = result.stdout.strip()
        assert loaded == "", (
            "import forgelm pulled heavy deps it should not.  "
            f"sys.modules contains: {loaded!r}.  Lazy-import contract broken."
        )

    def test_attribute_reference_does_not_pull_torch(self) -> None:
        """Even *referencing* `forgelm.ForgeTrainer` (without
        instantiating it) must not pull torch — the reference resolves
        to the class object via __getattr__ + lazy import of
        forgelm.trainer, but trainer.py defers torch imports to method
        bodies (per the existing tests/test_lazy_imports.py contract).
        """
        script = "import sys; import forgelm; _ = forgelm.ForgeTrainer; loaded = 'torch' in sys.modules; print(loaded)"
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"subprocess crashed: {result.stderr}"
        # stdout is "True" or "False"; we want False.
        assert result.stdout.strip() == "False", (
            "Referencing forgelm.ForgeTrainer pulled torch.  Lazy-import contract broken."
        )


# ---------------------------------------------------------------------------
# Lazy resolution + caching semantics
# ---------------------------------------------------------------------------


class TestLazyResolutionSemantics:
    def test_first_access_resolves_via_getattr(self) -> None:
        """The first access to a lazy symbol routes through
        ``__getattr__`` and returns the underlying object (not a stub)."""
        import forgelm

        # Use a torch-free symbol so the test doesn't drag in heavy deps.
        # `audit_dataset` is in `forgelm.data_audit` and is a real callable.
        result = forgelm.audit_dataset
        assert callable(result)

    def test_second_access_hits_globals_cache(self) -> None:
        """After the first access, the value is cached in module
        ``globals()`` so the ``__getattr__`` hook does not fire again.
        We can't easily prove the hook didn't fire, but we can prove
        the value is in globals() post-access (the documented PEP 562
        cache mechanism)."""
        import forgelm

        _ = forgelm.AuditLogger
        # Now `AuditLogger` should be present in the module's globals.
        assert "AuditLogger" in vars(forgelm)
        # And subsequent access returns the same object.
        assert forgelm.AuditLogger is vars(forgelm)["AuditLogger"]


# ---------------------------------------------------------------------------
# End-to-end library entry points (torch-free where possible)
# ---------------------------------------------------------------------------


class TestLibraryEntryPoints:
    def test_load_config_round_trip(self, tmp_path: Path) -> None:
        from forgelm import ForgeConfig, load_config

        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            """
model:
  name_or_path: gpt2
  backend: transformers
lora:
  r: 8
training:
  trainer_type: sft
  output_dir: ./out
  num_train_epochs: 1
data:
  dataset_name_or_path: train.jsonl
"""
        )
        cfg = load_config(str(config_path))
        assert isinstance(cfg, ForgeConfig)
        assert cfg.model.name_or_path == "gpt2"

    def test_audit_logger_roundtrip(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("FORGELM_OPERATOR", "library-test@host")

        from forgelm import AuditLogger, verify_audit_log

        AuditLogger(str(tmp_path)).log_event("library.smoke_test", note="hello")
        result = verify_audit_log(str(tmp_path / "audit_log.jsonl"))
        assert result.valid is True

    def test_verify_annex_iv_library_function(self, tmp_path: Path) -> None:
        import json

        from forgelm import verify_annex_iv_artifact

        artifact = {
            "system_identification": {"name": "x"},
            "intended_purpose": "y",
            "system_components": ["a"],
            "computational_resources": {"gpu": "x"},
            "data_governance": {"sources": ["x"]},
            "technical_documentation": {"design": "x"},
            "monitoring_and_logging": {"audit_log": "x"},
            "performance_metrics": {"loss": 1.0},
            "risk_management": {"art9": "x"},
        }
        path = tmp_path / "annex_iv.json"
        path.write_text(json.dumps(artifact))
        result = verify_annex_iv_artifact(str(path))
        assert result.valid is True

    def test_verify_gguf_library_function(self, tmp_path: Path) -> None:
        from forgelm import verify_gguf

        path = tmp_path / "model.gguf"
        path.write_bytes(b"GGUF" + b"\x00" * 256)
        result = verify_gguf(str(path))
        assert result.valid is True

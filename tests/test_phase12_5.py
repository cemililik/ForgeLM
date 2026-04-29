"""Phase 12.5 — data curation polish backlog.

Covers the four follow-up items from
:mod:`docs/roadmap/phase-12-5-backlog.md`:

1. ``forgelm ingest --all-mask`` composite shorthand (this file).
2. Wizard "audit first" entry point (this file).
3. ``forgelm audit --croissant`` Croissant 1.0 metadata (this file).
4. Presidio ML-NER PII adapter via the ``[ingestion-pii-ml]`` extra
   (this file).

Each test class targets exactly one of those four items so a future
re-shuffle can split this file along section boundaries cleanly.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from forgelm.cli import main

# ---------------------------------------------------------------------------
# Item 3 — `forgelm ingest --all-mask` composite shorthand
# ---------------------------------------------------------------------------


class TestIngestAllMask:
    """Phase 12.5 #3: ``--all-mask`` is shorthand for ``--secrets-mask --pii-mask``."""

    def _write_text(self, path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")

    def test_all_mask_redacts_both_pii_and_secrets(self, tmp_path):
        # Inert fragments at runtime so repo-wide secret scanners stay silent
        # while the regex still has to match the canonical shape.
        aws_key = "AKIA" + "IOSFODNN7" + "EXAMPLE"
        email = "alice@example.com"
        src = tmp_path / "input.txt"
        self._write_text(src, f"contact: {email}\nkey={aws_key}\n")
        out = tmp_path / "out.jsonl"

        with patch(
            "sys.argv",
            ["forgelm", "ingest", str(src), "--output", str(out), "--all-mask"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        written = out.read_text(encoding="utf-8")
        # Both kinds of redaction tokens land in the JSONL — proves the flag
        # composes additively into both subsystems, not just one of them.
        assert email not in written
        assert aws_key not in written
        assert "[REDACTED-SECRET]" in written
        assert "[REDACTED]" in written

    def test_all_mask_combines_with_individual_flags_no_error(self, tmp_path):
        # Set-union semantics: passing ``--all-mask`` alongside ``--pii-mask``
        # must not raise; both stay True.
        src = tmp_path / "input.txt"
        self._write_text(src, "alice@example.com plain text")
        out = tmp_path / "out.jsonl"

        with patch(
            "sys.argv",
            [
                "forgelm",
                "ingest",
                str(src),
                "--output",
                str(out),
                "--all-mask",
                "--pii-mask",
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        assert "[REDACTED]" in out.read_text(encoding="utf-8")

    def test_all_mask_does_not_redact_when_off(self, tmp_path):
        # Sanity: without the flag, neither masking subsystem fires.
        email = "alice@example.com"
        src = tmp_path / "input.txt"
        self._write_text(src, f"contact: {email}")
        out = tmp_path / "out.jsonl"

        with patch(
            "sys.argv",
            ["forgelm", "ingest", str(src), "--output", str(out)],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        assert email in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Item 4 — Wizard "audit first" entry point
# ---------------------------------------------------------------------------


class TestWizardAuditFirstOffer:
    """Phase 12.5 #4: when a JSONL is provided to the wizard, offer to audit it.

    Mirrors the Phase 11.5 ``_offer_ingest_for_directory`` pattern: the
    wizard surfaces the verdicts before continuing so the user can decide
    whether to swap datasets at config-time, not at training-time.
    """

    def _write_jsonl(self, path: Path, rows) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def test_audit_offer_runs_audit_when_user_accepts(self, tmp_path, capsys):
        from forgelm.wizard import _offer_audit_for_jsonl

        ds = tmp_path / "data.jsonl"
        self._write_jsonl(ds, [{"text": "alpha"}, {"text": "beta"}])

        # Simulate "yes" to the offer.
        with patch("forgelm.wizard._prompt_yes_no", return_value=True):
            outcome = _offer_audit_for_jsonl(ds)

        assert outcome is True
        rendered = capsys.readouterr().out
        assert "Audit complete" in rendered or "Audit results" in rendered

    def test_audit_offer_skipped_when_user_declines(self, tmp_path, capsys):
        from forgelm.wizard import _offer_audit_for_jsonl

        ds = tmp_path / "data.jsonl"
        self._write_jsonl(ds, [{"text": "alpha"}])

        # Simulate "no" — must short-circuit before invoking audit_dataset.
        with patch("forgelm.wizard._prompt_yes_no", return_value=False):
            with patch("forgelm.data_audit.audit_dataset") as mock_audit:
                outcome = _offer_audit_for_jsonl(ds)
                mock_audit.assert_not_called()

        assert outcome is False

    def test_audit_offer_recovers_when_audit_raises(self, tmp_path, capsys):
        # The wizard runs in interactive context; an unexpected audit failure
        # must NOT crash the wizard. The function returns False so the caller
        # falls through to the "continue without audit" path.
        from forgelm.wizard import _offer_audit_for_jsonl

        ds = tmp_path / "data.jsonl"
        self._write_jsonl(ds, [{"text": "alpha"}])

        with patch("forgelm.wizard._prompt_yes_no", return_value=True):
            with patch(
                "forgelm.data_audit.audit_dataset",
                side_effect=RuntimeError("simulated audit failure"),
            ):
                outcome = _offer_audit_for_jsonl(ds)

        assert outcome is False
        assert "could not run" in capsys.readouterr().out.lower()


# ---------------------------------------------------------------------------
# Item 2 — Croissant 1.0 metadata
# ---------------------------------------------------------------------------


class TestCroissantMetadataExport:
    """Phase 12.5 #2: ``--croissant`` adds a Google Croissant subset to the report."""

    def _write_jsonl(self, path: Path, rows) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def test_croissant_section_empty_by_default(self, tmp_path):
        # Phase 12 precedent (``secrets_summary`` / ``quality_summary``):
        # additive keys appear as empty dicts on default audits so consumers
        # using ``report.get("...", {})`` keep working byte-equivalently.
        # The Croissant block follows the same convention.
        ds = tmp_path / "data.jsonl"
        self._write_jsonl(ds, [{"text": "alpha"}])
        out_dir = tmp_path / "audit"

        with patch(
            "sys.argv",
            ["forgelm", "audit", str(ds), "--output", str(out_dir)],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        report = json.loads((out_dir / "data_audit_report.json").read_text(encoding="utf-8"))
        # Key may or may not be present depending on serializer; the contract
        # is "no Croissant content unless --croissant is passed".
        assert report.get("croissant", {}) == {}

    def test_croissant_flag_emits_minimal_card(self, tmp_path):
        ds = tmp_path / "data.jsonl"
        self._write_jsonl(ds, [{"text": "alpha"}, {"text": "beta"}])
        out_dir = tmp_path / "audit"

        with patch(
            "sys.argv",
            [
                "forgelm",
                "audit",
                str(ds),
                "--output",
                str(out_dir),
                "--croissant",
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        report = json.loads((out_dir / "data_audit_report.json").read_text(encoding="utf-8"))
        assert "croissant" in report
        crois = report["croissant"]
        # Pin the canonical Croissant 1.0 envelope so consumers / CI checks can
        # rely on it. ``@type`` and ``@context`` are the minimum-viable subset
        # that lets a Croissant-aware consumer parse the file without
        # extending the audit JSON's other top-level keys.
        assert crois.get("@type") == "sc:Dataset"
        assert "@context" in crois
        assert crois["@context"].get("sc") == "https://schema.org/"
        # ForgeLM-specific fields the report already has should be carried
        # across into the card so it stays a single self-contained document.
        assert "name" in crois
        assert "distribution" in crois  # describes the underlying JSONL


# ---------------------------------------------------------------------------
# Item 1 — Presidio adapter (``[ingestion-pii-ml]`` extra)
# ---------------------------------------------------------------------------


class TestPresidioPIIAdapter:
    """Phase 12.5 #1: optional ML-NER PII signal layered onto the regex path."""

    def _write_jsonl(self, path: Path, rows) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def test_presidio_disabled_by_default(self, tmp_path):
        # No --pii-ml flag → no Presidio counts; the regex path is unchanged.
        from forgelm.data_audit import audit_dataset

        ds = tmp_path / "data.jsonl"
        self._write_jsonl(ds, [{"text": "Visit Acme Corp in Berlin next Monday."}])

        report = audit_dataset(str(ds), output_dir=str(tmp_path / "audit"))
        # No new ML-tier categories — the regex-only path didn't see any PII
        # in this prose either, but we're really asserting the schema doesn't
        # add the Presidio-only buckets when the feature is off.
        for ml_only in ("person", "organization", "location"):
            assert ml_only not in report.pii_summary

    def test_presidio_missing_extra_raises_with_install_hint(self):
        from forgelm.data_audit import _require_presidio

        # When the extra isn't installed, the require-helper raises a typed
        # ImportError pointing at the install command — same pattern as
        # ``_require_datasketch`` / ``_require_detect_secrets``.
        with patch("forgelm.data_audit._HAS_PRESIDIO", False):
            with pytest.raises(ImportError) as exc_info:
                _require_presidio()
        msg = str(exc_info.value)
        assert "ingestion-pii-ml" in msg
        assert "pip install" in msg

    def test_presidio_severity_table_exposes_ml_tiers(self):
        # The severity table grows three new rows so the existing pii_severity
        # block can grade ML-NER findings the same way it grades regex hits.
        from forgelm.data_audit import PII_ML_SEVERITY

        for kind in ("person", "organization", "location"):
            assert kind in PII_ML_SEVERITY, f"missing severity tier for ML kind {kind!r}"
        # All three categories are below the regex 'critical' tier — names /
        # orgs / locations leak less identity than a credit-card number.
        # Pin medium / low to keep audit verdicts stable across releases.
        assert PII_ML_SEVERITY["person"] == "medium"
        assert PII_ML_SEVERITY["organization"] == "low"
        assert PII_ML_SEVERITY["location"] == "low"

"""Phase 12 tests for forgelm.data_audit — MinHash, secrets, quality filter.

Kept in a dedicated file so the Phase 11 / 11.5 surface (``test_data_audit.py``)
stays focused on the simhash / regex / streaming contract — Phase 12 adds
optional methods that only run when explicitly opted into, plus an
always-on secrets scan.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from forgelm.data_audit import (
    DEDUP_METHODS,
    DEFAULT_MINHASH_JACCARD,
    SECRET_TYPES,
    _row_quality_flags,
    audit_dataset,
    detect_secrets,
    mask_secrets,
)


def _has(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False


def _write_jsonl(path: Path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Secrets detection — always-on; runs without any optional dependency
# ---------------------------------------------------------------------------


class TestSecretsDetection:
    def test_aws_access_key_detected(self):
        # ``AKIA…`` 20-char access key.
        text = "config: aws_access_key_id=AKIAIOSFODNN7EXAMPLE end"
        result = detect_secrets(text)
        assert result.get("aws_access_key") == 1

    def test_github_token_detected(self):
        text = "token: ghp_1234567890abcdefghijABCDEFGHIJabcdef"
        result = detect_secrets(text)
        assert result.get("github_token") == 1

    def test_openai_api_key_detected(self):
        text = "OPENAI_API_KEY=sk-proj-abcDEF1234567890_XYZ-tokens-here"
        result = detect_secrets(text)
        assert result.get("openai_api_key") == 1

    def test_jwt_detected(self):
        # Real-shape JWT: header.payload.signature, all base64url.
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.SflKxwRJSMeKKF2QT4fwpMeJ"
        result = detect_secrets(text)
        assert result.get("jwt") == 1

    def test_clean_text_returns_empty(self):
        assert detect_secrets("perfectly innocent prose with no credentials") == {}

    def test_non_string_returns_empty(self):
        assert detect_secrets(None) == {}
        assert detect_secrets(42) == {}

    def test_secret_types_listed(self):
        # Sanity: the public tuple should match what detect_secrets can emit.
        assert "aws_access_key" in SECRET_TYPES
        assert "github_token" in SECRET_TYPES
        assert "jwt" in SECRET_TYPES


class TestSecretsMasking:
    def test_aws_key_redacted(self):
        original = "config: aws_access_key_id=AKIAIOSFODNN7EXAMPLE end"
        masked = mask_secrets(original)
        assert "AKIAIOSFODNN7EXAMPLE" not in masked
        assert "[REDACTED-SECRET]" in masked

    def test_return_counts_truthful(self):
        original = "k1=AKIAIOSFODNN7EXAMPLE / k2=ghp_1234567890abcdefghijABCDEFGHIJabcdef"
        masked, counts = mask_secrets(original, return_counts=True)
        assert counts.get("aws_access_key") == 1
        assert counts.get("github_token") == 1
        assert "[REDACTED-SECRET]" in masked

    def test_clean_text_passes_through(self):
        original = "no secrets here"
        masked, counts = mask_secrets(original, return_counts=True)
        assert masked == original
        assert counts == {}

    def test_non_string_passes_through(self):
        assert mask_secrets(None) is None


class TestAuditPicksUpSecrets:
    def test_secrets_summary_lands_in_audit_json(self, tmp_path):
        path = tmp_path / "x.jsonl"
        _write_jsonl(
            path,
            [
                {"text": "key=AKIAIOSFODNN7EXAMPLE here"},
                {"text": "innocent line"},
                {"text": "token=ghp_abcdefghij1234567890ABCDEFGHIJ012345"},
            ],
        )
        report = audit_dataset(str(path))
        # detect_secrets is always-on — no flag needed.
        assert report.secrets_summary.get("aws_access_key") == 1
        assert report.secrets_summary.get("github_token") == 1


# ---------------------------------------------------------------------------
# Quality filter — opt-in; default audit doesn't run it
# ---------------------------------------------------------------------------


class TestQualityFilterPerRow:
    def test_low_alpha_ratio_flagged(self):
        # 90% non-letters → flagged.
        text = "1234567890 !@#$%^&*() {} [] :;<>"
        flags = _row_quality_flags(text)
        assert "low_alpha_ratio" in flags

    def test_short_paragraphs_flagged(self):
        # All paragraphs are < 5 words → flagged.
        text = "hi there.\n\nyo.\n\nok bye."
        flags = _row_quality_flags(text)
        assert "short_paragraphs" in flags

    def test_clean_prose_passes(self):
        text = (
            "The quick brown fox jumps over the lazy dog. The same fox "
            "later jumps back, this time more deliberately. End-of-line "
            "punctuation appears throughout the corpus. Lines are long "
            "enough to satisfy the heuristic checks."
        )
        flags = _row_quality_flags(text)
        assert flags == []

    def test_empty_text_returns_empty(self):
        assert _row_quality_flags("") == []
        assert _row_quality_flags(None) == []  # type: ignore[arg-type]


class TestQualityFilterEnabled:
    def test_quality_summary_only_present_when_enabled(self, tmp_path):
        path = tmp_path / "x.jsonl"
        _write_jsonl(path, [{"text": "1234567890 !@#$%^&*()"}, {"text": "fine prose here that survives heuristics."}])

        # Default: quality filter off → no quality_summary fields.
        default_report = audit_dataset(str(path))
        assert default_report.quality_summary == {}

        # Opt-in: quality filter on → quality_summary populated.
        opt_in_report = audit_dataset(str(path), enable_quality_filter=True)
        assert opt_in_report.quality_summary.get("samples_flagged", 0) >= 1
        assert "by_check" in opt_in_report.quality_summary


# ---------------------------------------------------------------------------
# MinHash LSH — needs the optional 'datasketch' extra
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _has("datasketch"), reason="datasketch (ingestion-scale extra) not installed")
class TestMinHashLshDedup:
    def test_dedup_method_choices_listed(self):
        assert "simhash" in DEDUP_METHODS
        assert "minhash" in DEDUP_METHODS

    def test_minhash_finds_near_duplicates(self):
        from forgelm.data_audit import compute_minhash, find_near_duplicates_minhash

        texts = [
            "the quick brown fox jumps over the lazy dog",
            "the quick brown fox jumps over the lazy dog",  # exact dup
            "the quick brown fox leaps over the lazy dog",  # near dup
            "completely unrelated payload with different tokens",
        ]
        minhashes = [compute_minhash(t) for t in texts]
        pairs = find_near_duplicates_minhash(minhashes, jaccard_threshold=0.5)
        pair_idx = {(i, j) for i, j, _ in pairs}
        # exact + near should both surface
        assert (0, 1) in pair_idx
        assert (0, 2) in pair_idx or (1, 2) in pair_idx

    def test_audit_minhash_writes_method_in_report(self, tmp_path):
        path = tmp_path / "x.jsonl"
        _write_jsonl(
            path,
            [
                {"text": "alpha beta gamma delta epsilon zeta"},
                {"text": "alpha beta gamma delta epsilon zeta"},
                {"text": "completely unrelated payload"},
            ],
        )
        report = audit_dataset(
            str(path),
            dedup_method="minhash",
            minhash_jaccard=DEFAULT_MINHASH_JACCARD,
        )
        assert report.near_duplicate_summary.get("method") == "minhash"
        # Within-split near-dup pair must be picked up.
        assert report.splits["train"]["near_duplicate_pairs"] >= 1

    def test_audit_default_uses_simhash(self, tmp_path):
        # Phase 11.5 default behaviour preserved when method is omitted.
        path = tmp_path / "x.jsonl"
        _write_jsonl(path, [{"text": "alpha"}])
        report = audit_dataset(str(path))
        assert report.near_duplicate_summary.get("method") == "simhash"


class TestMinHashMissingExtra:
    def test_helpful_error_when_datasketch_missing(self, monkeypatch):
        from forgelm import data_audit as audit_mod

        # Force the "missing extra" code path even if datasketch is installed.
        monkeypatch.setattr(audit_mod, "_HAS_DATASKETCH", False)
        with pytest.raises(ImportError, match=r"forgelm\[ingestion-scale\]"):
            audit_mod._require_datasketch()

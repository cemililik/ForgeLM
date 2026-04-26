"""Tests for forgelm.data_audit (Phase 11).

Pure-Python regex / simhash logic; no torch / TRL required.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forgelm.data_audit import (
    DEFAULT_NEAR_DUP_HAMMING,
    PII_TYPES,
    AuditReport,
    _is_credit_card,
    _is_tr_id,
    audit_dataset,
    compute_simhash,
    detect_pii,
    find_near_duplicates,
    hamming_distance,
    mask_pii,
    summarize_report,
)

# ---------------------------------------------------------------------------
# PII detection
# ---------------------------------------------------------------------------


class TestPiiDetection:
    def test_email_detected(self):
        assert detect_pii("write to alice@example.com today").get("email") == 1

    def test_phone_detected(self):
        assert detect_pii("call +90 532 123 45 67 now").get("phone", 0) >= 1

    def test_credit_card_validated_via_luhn(self):
        # 4111 1111 1111 1111 is a Visa test card with valid Luhn
        assert detect_pii("card 4111 1111 1111 1111").get("credit_card") == 1
        # Same shape but invalid Luhn → not flagged
        assert detect_pii("not a card 4111 1111 1111 1112").get("credit_card", 0) == 0

    def test_tr_id_validated_via_checksum(self):
        # Real-format checksum-valid TR Kimlik (synthetic, math-checked)
        valid = "10000000146"  # passes the canonical TR algorithm
        assert _is_tr_id(valid) is True
        assert detect_pii(f"id is {valid}").get("tr_id") == 1
        # Random 11 digits should fail the checksum
        assert detect_pii("id is 12345678901").get("tr_id", 0) == 0

    def test_us_ssn_excludes_invalid_prefixes(self):
        assert detect_pii("ssn 123-45-6789").get("us_ssn") == 1
        # 666 is reserved — not a valid SSN prefix
        assert detect_pii("ssn 666-45-6789").get("us_ssn", 0) == 0

    def test_returns_empty_for_clean_text(self):
        assert detect_pii("hello world how are you") == {}

    def test_returns_empty_for_non_string(self):
        assert detect_pii(None) == {}
        assert detect_pii(42) == {}

    def test_pii_types_listed(self):
        # Sanity: the public tuple matches what detect_pii can emit.
        assert "email" in PII_TYPES
        assert "credit_card" in PII_TYPES
        assert "tr_id" in PII_TYPES


class TestPiiMasking:
    def test_email_redacted(self):
        out = mask_pii("contact alice@example.com please")
        assert "alice@example.com" not in out
        assert "[REDACTED]" in out

    def test_valid_credit_card_is_redacted(self):
        out = mask_pii("card 4111 1111 1111 1111")
        assert "4111 1111 1111 1111" not in out
        assert "[REDACTED]" in out

    def test_luhn_helper_distinguishes_valid_from_invalid(self):
        # The masker may also redact long digit runs as candidate phone
        # numbers (false positives are intentional per the module docstring).
        # We assert at the helper level instead, which is unambiguous.
        from forgelm.data_audit import _is_credit_card

        assert _is_credit_card("4111111111111111") is True
        assert _is_credit_card("4111111111111112") is False

    def test_replacement_can_be_overridden(self):
        out = mask_pii("email alice@example.com", replacement="<X>")
        assert "<X>" in out

    def test_passes_non_string_through(self):
        assert mask_pii(None) is None  # type: ignore[arg-type]


class TestLuhnHelper:
    @pytest.mark.parametrize("number", ["4111111111111111", "4012888888881881", "5555555555554444"])
    def test_known_test_cards_pass(self, number):
        assert _is_credit_card(number) is True

    def test_short_number_rejected(self):
        assert _is_credit_card("1234") is False

    def test_invalid_luhn_rejected(self):
        assert _is_credit_card("1234567812345678") is False


# ---------------------------------------------------------------------------
# Simhash + near-duplicate detection
# ---------------------------------------------------------------------------


class TestSimhash:
    def test_identical_text_same_fingerprint(self):
        a = "The quick brown fox jumps over the lazy dog."
        b = "The quick brown fox jumps over the lazy dog."
        assert compute_simhash(a) == compute_simhash(b)

    def test_empty_text_zero(self):
        assert compute_simhash("") == 0
        assert compute_simhash("   ") == 0

    def test_near_duplicate_close_in_hamming(self):
        a = "The quick brown fox jumps over the lazy dog."
        b = "The quick brown fox leaps over the lazy dog."  # one word changed
        assert hamming_distance(compute_simhash(a), compute_simhash(b)) <= 16

    def test_unrelated_text_far_in_hamming(self):
        a = "The quick brown fox jumps over the lazy dog."
        b = "Quantum chromodynamics describes the strong nuclear force."
        # Should be large; exact value depends on hash mixing
        assert hamming_distance(compute_simhash(a), compute_simhash(b)) > 10


class TestFindNearDuplicates:
    def test_finds_identical_pairs(self):
        fps = [compute_simhash("alpha"), compute_simhash("alpha"), compute_simhash("beta")]
        pairs = find_near_duplicates(fps, threshold=0)
        assert (0, 1, 0) in pairs
        # No (alpha, beta) pair below threshold 0
        assert all(not (i == 0 and j == 2) for i, j, _ in pairs)

    def test_skips_zero_fingerprints(self):
        fps = [0, 0, compute_simhash("alpha")]
        assert find_near_duplicates(fps, threshold=DEFAULT_NEAR_DUP_HAMMING) == []


# ---------------------------------------------------------------------------
# audit_dataset end-to-end
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class TestAuditSingleFile:
    def test_basic_metrics(self, tmp_path):
        path = tmp_path / "train.jsonl"
        _write_jsonl(
            path,
            [
                {"text": "Alpha bravo charlie."},
                {"text": "Delta echo foxtrot."},
                {"text": ""},  # null/empty case
            ],
        )
        report = audit_dataset(str(path))
        assert isinstance(report, AuditReport)
        assert report.total_samples == 3
        assert "train" in report.splits
        info = report.splits["train"]
        assert info["sample_count"] == 3
        assert info["null_or_empty_count"] == 1
        assert info["text_length"]["min"] >= 1

    def test_pii_aggregated_into_summary(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        _write_jsonl(
            path,
            [
                {"text": "Email alice@example.com"},
                {"text": "Another to bob@example.com"},
            ],
        )
        report = audit_dataset(str(path))
        assert report.pii_summary.get("email") == 2

    def test_writes_report_when_output_dir_given(self, tmp_path):
        path = tmp_path / "x.jsonl"
        _write_jsonl(path, [{"text": "hello world"}])
        out_dir = tmp_path / "audit"
        audit_dataset(str(path), output_dir=str(out_dir))
        report_path = out_dir / "data_audit_report.json"
        assert report_path.is_file()
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        assert payload["total_samples"] == 1

    def test_missing_input_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            audit_dataset(str(tmp_path / "nope.jsonl"))


class TestAuditDirectoryLayout:
    def test_split_keyed_directory(self, tmp_path):
        _write_jsonl(tmp_path / "train.jsonl", [{"text": "A"}, {"text": "B"}])
        _write_jsonl(tmp_path / "validation.jsonl", [{"text": "C"}])
        report = audit_dataset(str(tmp_path))
        assert set(report.splits) == {"train", "validation"}
        assert report.total_samples == 3

    def test_cross_split_overlap_caught(self, tmp_path):
        # Identical row in train + test → leakage
        _write_jsonl(tmp_path / "train.jsonl", [{"text": "alpha bravo charlie delta echo"}])
        _write_jsonl(tmp_path / "test.jsonl", [{"text": "alpha bravo charlie delta echo"}])
        report = audit_dataset(str(tmp_path))
        pairs = report.cross_split_overlap.get("pairs", {})
        assert any("train" in k and "test" in k for k in pairs)
        # The reporter records the leak under one direction; rate >= 1.0 / count
        leak_payload = next(iter(pairs.values()))
        assert leak_payload["leak_rate"] > 0.0


class TestMessagesFormat:
    def test_concatenates_message_content_for_dedup(self, tmp_path):
        path = tmp_path / "chat.jsonl"
        _write_jsonl(
            path,
            [
                {"messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]},
                {"messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]},
            ],
        )
        report = audit_dataset(str(path))
        # Two identical chats → near_duplicate_pairs should be 1
        assert report.splits["train"]["near_duplicate_pairs"] >= 1


class TestSummarize:
    def test_renders_split_metrics(self, tmp_path):
        path = tmp_path / "x.jsonl"
        _write_jsonl(path, [{"text": "alpha"}, {"text": "alpha"}])
        report = audit_dataset(str(path))
        rendered = summarize_report(report)
        assert "Total samples" in rendered
        assert "train" in rendered

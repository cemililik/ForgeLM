"""Phase 15 Task 3 unit tests — pypdf glyph-normalisation profile."""

from __future__ import annotations

import pytest

from forgelm._pypdf_normalise import (
    DEFAULT_PROFILE,
    PROFILES,
    apply_profile,
    emitted_codepoints,
    profile_summary,
)


class TestProfileVocabulary:
    def test_default_profile_is_turkish(self):
        assert DEFAULT_PROFILE == "turkish"

    def test_profiles_includes_none_for_explicit_opt_out(self):
        assert "none" in PROFILES
        assert "turkish" in PROFILES


class TestApplyProfile:
    def test_turkish_profile_round_trip_canonical_glyphs(self):
        # Audit-measured artefacts: ø Õ ú ÷ ࡟ → İ ı ş ğ •
        assert apply_profile("ø Õ ú ÷ ࡟", "turkish") == "İ ı ş ğ •"

    def test_multichar_substitution_fires_before_single_char(self):
        # ``ö `` (with trailing space) maps to ``Ğ`` — the multi-char
        # pass must run before the single-char str.translate() lookup.
        assert apply_profile("ö abc", "turkish") == "Ğabc"

    def test_none_profile_returns_input_unchanged(self):
        assert apply_profile("ø Õ ú", "none") == "ø Õ ú"

    def test_unknown_profile_silently_no_ops(self):
        # Forward compat: don't crash an ingest run on an unknown profile.
        assert apply_profile("ø Õ ú", "klingon") == "ø Õ ú"

    def test_empty_text_returns_empty(self):
        assert apply_profile("", "turkish") == ""

    def test_preserves_clean_turkish_text(self):
        # The normaliser must never rewrite correct Turkish characters.
        clean = "Türkçe metin doğru karakterler içerir."
        assert apply_profile(clean, "turkish") == clean


class TestProfileSummary:
    def test_turkish_summary_returns_table_sizes(self):
        summary = profile_summary("turkish")
        assert summary["single"] >= 5
        assert summary["multi"] >= 1

    def test_none_profile_summary_is_zero(self):
        assert profile_summary("none") == {"multi": 0, "single": 0}

    def test_unknown_profile_summary_is_zero(self):
        assert profile_summary("klingon") == {"multi": 0, "single": 0}


class TestEmittedCodepoints:
    def test_turkish_emit_set_contains_targets(self):
        emit = emitted_codepoints("turkish")
        for target in ("İ", "ı", "ş", "ğ", "•", "Ğ"):
            assert target in emit

    def test_none_profile_emits_nothing(self):
        assert emitted_codepoints("none") == frozenset()


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))

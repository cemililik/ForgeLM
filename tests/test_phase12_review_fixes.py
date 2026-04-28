"""Regression tests for Phase 12 review-cycle fixes.

These tests pin behaviour that the Phase 12 code review (2026-04-28)
flagged as wrong / regressed. Kept in a dedicated file so the original
Phase 12 acceptance suite (``test_data_audit_phase12.py`` /
``test_ingestion_phase12.py``) stays a clean record of the feature's
shape, while this file documents *what the review caught and how we
prevent it from coming back*.
"""

from __future__ import annotations

import json
from pathlib import Path

from forgelm.data_audit import (
    _SECRET_PATTERNS,
    _row_quality_flags,
    audit_dataset,
    detect_secrets,
)
from forgelm.ingestion import (
    _chunk_markdown_tokens,
    _docx_table_to_markdown,
    _markdown_sections,
)


def _write_jsonl(path: Path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# C1 — stdout JSON envelope: ``near_duplicate_pairs_per_split`` must remain
# present so v0.5.1 consumers (e.g. ``jq '.near_duplicate_pairs_per_split'``)
# don't break under v0.5.2.
# ---------------------------------------------------------------------------


class TestC1JsonEnvelopeBackcompat:
    def test_envelope_keeps_legacy_pairs_per_split_key(self, tmp_path, capsys):
        # Drives the CLI envelope path. ``audit_dataset`` returns the report;
        # the CLI shim is the boundary that exposes ``near_duplicate_pairs_per_split``.
        from forgelm.cli import _run_data_audit

        path = tmp_path / "x.jsonl"
        _write_jsonl(path, [{"text": "alpha"}, {"text": "alpha"}, {"text": "beta gamma"}])
        out_dir = tmp_path / "audit"
        _run_data_audit(str(path), str(out_dir), "json")
        captured = capsys.readouterr().out
        envelope = json.loads(captured)
        # Legacy key — pre-Phase-12 consumers depend on this exact name.
        assert "near_duplicate_pairs_per_split" in envelope
        # New richer key kept alongside (additive).
        assert "near_duplicate_summary" in envelope
        # Both must reference the same per-split data.
        assert envelope["near_duplicate_pairs_per_split"] == envelope["near_duplicate_summary"].get(
            "pairs_per_split", {}
        )


# ---------------------------------------------------------------------------
# C2 — quality filter: ``repeated_lines`` (the 5th plan-promised check) is
# implemented and surfaces in the audit JSON.
# ---------------------------------------------------------------------------


class TestC2RepeatedLinesQualityCheck:
    def test_top3_lines_over_30pct_flag(self):
        # Build a corpus where 4 of 6 lines are the same boilerplate line
        # (66 % > 30 % threshold).
        text = (
            "boilerplate header.\n"
            "boilerplate header.\n"
            "actual content here.\n"
            "boilerplate header.\n"
            "different content again.\n"
            "boilerplate header.\n"
        )
        flags = _row_quality_flags(text)
        assert "repeated_lines" in flags

    def test_diverse_lines_not_flagged(self):
        text = (
            "first unique line of prose.\n"
            "second unique line of prose.\n"
            "third unique line of prose.\n"
            "fourth unique line of prose.\n"
            "fifth unique line of prose.\n"
        )
        flags = _row_quality_flags(text)
        assert "repeated_lines" not in flags

    def test_quality_summary_surfaces_repeated_lines(self, tmp_path):
        path = tmp_path / "x.jsonl"
        _write_jsonl(
            path,
            [
                {"text": "Disclaimer X.\nDisclaimer X.\nbody.\nDisclaimer X.\nmore body.\nDisclaimer X.\n"},
                {"text": "innocent prose with no repetition pattern at all."},
            ],
        )
        report = audit_dataset(str(path), enable_quality_filter=True)
        by_check = report.quality_summary.get("by_check", {})
        assert by_check.get("repeated_lines", 0) >= 1


# ---------------------------------------------------------------------------
# C3 — DOCX table cell ``|`` characters must be escaped so the rendered
# markdown table parses with the correct column count.
# ---------------------------------------------------------------------------


class _FakeCell:
    def __init__(self, text):
        self.text = text


class _FakeRow:
    def __init__(self, cells):
        self.cells = [_FakeCell(c) for c in cells]


class _FakeTable:
    def __init__(self, rows):
        self.rows = [_FakeRow(r) for r in rows]


class TestC3DocxPipeEscape:
    def test_pipe_in_cell_escaped(self):
        table = _FakeTable(
            [
                ["Name", "Value"],
                ["a|b", "x"],
                ["c", "d|e"],
            ]
        )
        rendered = _docx_table_to_markdown(table)
        # The body rows must escape the inline pipes — otherwise downstream
        # markdown parsers see 4 columns instead of 2.
        assert "a\\|b" in rendered
        assert "d\\|e" in rendered
        # Each body line still has exactly 3 separators (= 2 columns).
        body_lines = [line for line in rendered.splitlines() if line.startswith("| ")][1:]
        # 3 separators because of leading/trailing/middle ``|``; escaped
        # ``\|`` doesn't act as a separator.
        for line in body_lines:
            # Real separators only — strip escaped ``\|`` first.
            stripped = line.replace("\\|", "")
            assert stripped.count("|") == 3, f"bad row: {line!r}"

    def test_backslash_in_cell_escaped(self):
        table = _FakeTable([["A"], ["c:\\path"]])
        rendered = _docx_table_to_markdown(table)
        # Backslash must be escaped (``\\`` → ``\\\\``) so it survives one
        # round-trip through a markdown-aware tokeniser.
        assert "c:\\\\path" in rendered

    def test_newline_in_cell_collapsed(self):
        table = _FakeTable([["Header"], ["multi\nline\ncell"]])
        rendered = _docx_table_to_markdown(table)
        # Newlines collapse to spaces — markdown tables can't carry them.
        assert "multi line line cell" not in rendered  # not duplicated
        assert "multi line cell" in rendered


# ---------------------------------------------------------------------------
# C4 — JWT regex must reject prose-shaped ``eyJ.eyJ.X`` strings while
# continuing to flag real JWTs (``alg`` / ``typ`` / etc. headers).
# ---------------------------------------------------------------------------


class TestC4JwtRegexNarrowing:
    def test_real_jwt_still_detected(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.SflKxwRJSMeKKF2QT4fwpMeJ"
        result = detect_secrets(text)
        assert result.get("jwt") == 1

    def test_realistic_hs256_token_detected(self):
        text = (
            "token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIxMjM0NSIsIm5hbWUiOiJKb2huIERvZSJ9."
            "abcdefghijklmnopqrstuvwxyz123"
        )
        result = detect_secrets(text)
        assert result.get("jwt") == 1

    def test_prose_eyj_shape_not_flagged(self):
        # Reviewer's false-positive shape: ``eyJ.eyJ.X`` in casual prose,
        # not a real JWT (header is just ``eyJ`` followed by random bytes,
        # missing ``alg`` / ``typ`` / ``kid`` etc.).
        text = "Look at this base64: eyJhYmNkZWY.eyJ4eXp.aGVsbG8 — could be a JWT shape but is not."
        result = detect_secrets(text)
        assert "jwt" not in result

    def test_jwt_pattern_anchored_on_known_headers(self):
        # The compiled pattern itself must require one of the canonical
        # JWT header prefixes — pinning so a future regex broadening can't
        # silently re-introduce the false-positive class.
        pattern = _SECRET_PATTERNS["jwt"].pattern
        for anchor in ("hbGc", "0eXA", "raWQ", "jdHk", "lbmM", "hcGk"):
            assert anchor in pattern


# ---------------------------------------------------------------------------
# Review-1#4 — quality filter must not flag rows that are predominantly
# fenced markdown code blocks (legitimate SFT content for code-instruct).
# ---------------------------------------------------------------------------


class TestQualityFilterIgnoresCodeFences:
    def test_pure_code_block_returns_no_flags(self):
        text = "```python\ndef f(x):\n    return x + 1\n```\n"
        # Pure code → strip leaves ``""`` → no flags (not "low_alpha_ratio").
        assert _row_quality_flags(text) == []

    def test_prose_with_code_block_judged_on_prose_only(self):
        text = (
            "Here is a function that adds one to its input. "
            "It is a simple unary mapping. "
            "Use it for arithmetic chaining.\n\n"
            "```python\n"
            "def f(x):\n"
            "    return x + 1\n"
            "```\n\n"
            "The function is pure and side-effect free."
        )
        flags = _row_quality_flags(text)
        # Prose around the code passes all heuristics — the code block must
        # not have dragged the alpha-ratio below 70 %.
        assert flags == []


# ---------------------------------------------------------------------------
# H4 — ``_chunk_markdown_tokens`` (token-aware twin) must respect the token
# cap and inline the heading breadcrumb. The original Phase 12 suite only
# tested the character-mode twin.
# ---------------------------------------------------------------------------


class _StubTokenizer:
    """Word-count tokenizer for deterministic token-cap tests."""

    def encode(self, text, add_special_tokens=False):  # noqa: ARG002
        return list(range(len(text.split())))


class TestChunkMarkdownTokens:
    def test_short_doc_packs_into_one_chunk(self):
        text = "# H1\n\nshort body."
        chunks = list(_chunk_markdown_tokens(text, max_tokens=100, tokenizer=_StubTokenizer()))
        assert len(chunks) == 1
        assert "# H1" in chunks[0]

    def test_separator_token_included_in_budget(self):
        # Two sections, each ~5 tokens. Token cap forces them into separate
        # chunks; the second chunk must inline the parent breadcrumb.
        text = (
            "# Project\n\n"
            "alpha beta gamma delta epsilon\n\n"
            "## Background\n\n"
            "uno dos tres cuatro cinco seis siete ocho nueve diez"
        )
        chunks = list(_chunk_markdown_tokens(text, max_tokens=8, tokenizer=_StubTokenizer()))
        assert len(chunks) >= 2
        background = next(c for c in chunks if "Background" in c)
        # Breadcrumb invariant: the parent heading rides into the
        # downstream chunk so SFT loss sees the document context.
        assert "# Project" in background

    def test_invalid_max_tokens_raises(self):
        import pytest

        with pytest.raises(ValueError):
            list(_chunk_markdown_tokens("# H1\n\nbody.", max_tokens=0, tokenizer=_StubTokenizer()))


# ---------------------------------------------------------------------------
# N1 — CommonMark allows up to 3 leading spaces before an ATX heading.
# ---------------------------------------------------------------------------


class TestCommonMarkIndentedHeadings:
    def test_two_leading_spaces_treated_as_heading(self):
        # 0-3 leading spaces is still a heading per CommonMark §4.2.
        text = "  # Indented heading\n\nbody under it.\n"
        sections = _markdown_sections(text)
        assert len(sections) == 1
        path, body = sections[0]
        # Heading text is recovered (with the ``#`` prefix preserved).
        assert path[0].lstrip().startswith("#")
        assert "body under it" in body

    def test_four_leading_spaces_is_not_heading(self):
        # 4+ spaces makes it an indented code block — must NOT split.
        text = "# Real H1\n\nintro.\n\n    # Not a heading\n\nstill body.\n"
        sections = _markdown_sections(text)
        # Single section because the 4-space line is body, not a heading.
        assert len(sections) == 1

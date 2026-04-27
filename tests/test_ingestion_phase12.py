"""Phase 12 tests for forgelm.ingestion — markdown splitter, DOCX table preservation, secrets-mask wiring."""

from __future__ import annotations

import importlib
import json

from forgelm.ingestion import (
    _chunk_markdown,
    _docx_table_to_markdown,
    _markdown_sections,
    ingest_path,
)


def _has(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Markdown splitter
# ---------------------------------------------------------------------------


class TestMarkdownSections:
    def test_simple_two_section_document(self):
        text = "# H1\n\nintro paragraph.\n\n## H2\n\nbody under H2."
        sections = _markdown_sections(text)
        # Two sections: ``# H1`` and ``## H2``
        assert len(sections) == 2
        path1, body1 = sections[0]
        path2, body2 = sections[1]
        assert path1 == ["# H1"]
        assert "intro paragraph" in body1
        # Second section's heading path includes the parent.
        assert path2 == ["# H1", "## H2"]
        assert "body under H2" in body2

    def test_heading_inside_code_block_is_not_a_heading(self):
        text = (
            "# Real Heading\n\n"
            "Some intro.\n\n"
            "```bash\n"
            "# this looks like a heading but it's a shell prompt\n"
            "echo hi\n"
            "```\n\n"
            "more body after the code block."
        )
        sections = _markdown_sections(text)
        # Exactly one heading; the ``# this looks like…`` inside the
        # fenced block must NOT split into its own section.
        assert len(sections) == 1
        body = sections[0][1]
        assert "shell prompt" in body
        assert "echo hi" in body
        assert "more body" in body


class TestChunkMarkdown:
    def test_short_doc_packs_into_one_chunk(self):
        text = "# H1\n\nshort body."
        chunks = list(_chunk_markdown(text, max_chunk_size=10_000))
        assert len(chunks) == 1
        assert "# H1" in chunks[0]

    def test_breadcrumb_inlined_for_nested_sections(self):
        text = (
            "# Project\n\n"
            "Project intro.\n\n"
            "## Background\n\n"
            "Background body that's much longer than the cap can fit "
            "alongside the project intro section above."
        )
        # Cap small enough to force a split between sections.
        chunks = list(_chunk_markdown(text, max_chunk_size=80))
        # The Background chunk's body must include the parent heading
        # (``# Project``) as a breadcrumb so SFT loss sees the context.
        background_chunk = next(c for c in chunks if "Background" in c)
        assert "# Project" in background_chunk

    def test_long_section_emitted_whole(self):
        long_body = " ".join(["word"] * 500)
        text = f"# H1\n\n{long_body}"
        chunks = list(_chunk_markdown(text, max_chunk_size=200))
        # Single section — even though it's longer than the cap, it stays whole.
        assert len(chunks) == 1
        assert chunks[0].endswith("word")


class TestMarkdownStrategyExposed:
    def test_strategy_dispatch_includes_markdown(self, tmp_path):
        # End-to-end: ingest a markdown file with --strategy markdown.
        src = tmp_path / "doc.md"
        src.write_text(
            "# Doc\n\nintro\n\n## Section A\n\nbody A\n\n## Section B\n\nbody B",
            encoding="utf-8",
        )
        out = tmp_path / "out.jsonl"
        result = ingest_path(
            str(src),
            output_path=str(out),
            strategy="markdown",
            chunk_size=100,
        )
        assert result.chunk_count >= 1
        # Each emitted chunk must reference at least one heading line.
        with open(out, encoding="utf-8") as fh:
            payloads = [json.loads(line)["text"] for line in fh if line.strip()]
        assert all("#" in p for p in payloads)


# ---------------------------------------------------------------------------
# DOCX markdown table preservation
# ---------------------------------------------------------------------------


class _FakeCell:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeRow:
    def __init__(self, cells):
        self.cells = [_FakeCell(c) for c in cells]


class _FakeTable:
    def __init__(self, rows):
        self.rows = [_FakeRow(r) for r in rows]


class TestDocxTableToMarkdown:
    def test_simple_3x3_table_renders_markdown(self):
        table = _FakeTable(
            [
                ["Name", "Age", "City"],
                ["Alice", "30", "Berlin"],
                ["Bob", "25", "Paris"],
            ]
        )
        rendered = _docx_table_to_markdown(table)
        # Header line + separator + 2 body lines.
        assert "| Name | Age | City |" in rendered
        assert "|---|---|---|" in rendered
        assert "| Alice | 30 | Berlin |" in rendered

    def test_uneven_rows_padded_with_blanks(self):
        table = _FakeTable(
            [
                ["A", "B", "C"],
                ["row1"],  # short row → padded
            ]
        )
        rendered = _docx_table_to_markdown(table)
        assert "| row1 |  |  |" in rendered

    def test_empty_rows_skipped(self):
        table = _FakeTable(
            [
                ["", "", ""],
                ["A", "B", "C"],
                ["", "", ""],
            ]
        )
        rendered = _docx_table_to_markdown(table)
        # The all-blank rows should be dropped.
        assert "| A | B | C |" in rendered
        # Empty rows trimmed → only the kept row drives the layout.
        # 3 columns → header line + separator line, no body lines.
        assert rendered == "| A | B | C |\n|---|---|---|"

    def test_empty_table_returns_empty_string(self):
        table = _FakeTable([])
        assert _docx_table_to_markdown(table) == ""


# ---------------------------------------------------------------------------
# Secrets-mask CLI wiring
# ---------------------------------------------------------------------------


class TestSecretsMaskIngest:
    def test_secrets_mask_redacts_and_counts(self, tmp_path):
        src = tmp_path / "secret.txt"
        src.write_text(
            "config\n\nkey=AKIAIOSFODNN7EXAMPLE\n\ntoken=ghp_abcdefghij1234567890ABCDEFGHIJ012345",
            encoding="utf-8",
        )
        out = tmp_path / "out.jsonl"
        result = ingest_path(
            str(src),
            output_path=str(out),
            secrets_mask=True,
        )
        assert result.secrets_redaction_counts.get("aws_access_key", 0) >= 1
        assert result.secrets_redaction_counts.get("github_token", 0) >= 1
        with open(out, encoding="utf-8") as fh:
            written = fh.read()
        assert "AKIAIOSFODNN7EXAMPLE" not in written
        assert "ghp_" not in written
        assert "[REDACTED-SECRET]" in written

    def test_secrets_mask_off_by_default(self, tmp_path):
        # Without --secrets-mask, secrets land in the JSONL unchanged.
        src = tmp_path / "secret.txt"
        src.write_text("key=AKIAIOSFODNN7EXAMPLE", encoding="utf-8")
        out = tmp_path / "out.jsonl"
        result = ingest_path(str(src), output_path=str(out))
        assert result.secrets_redaction_counts == {}
        with open(out, encoding="utf-8") as fh:
            written = fh.read()
        assert "AKIAIOSFODNN7EXAMPLE" in written

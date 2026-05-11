# Phase 15 regression fixtures

> **Audience:** ForgeLM contributors maintaining the Phase 15
> ingestion-reliability regression suite.

This directory carries the **deterministic** Phase 15 fixtures that
do not depend on a specific `pypdf` / `python-docx` / `ebooklib`
version — small, plain-text-or-XML inputs whose extraction behaviour
is contractually stable across library upgrades. Binary fixtures that
*do* depend on extractor version (PDF / DOCX / EPUB) are **synthesised
at test time** by `tests/test_ingestion_reliability.py` so a future
`pypdf` upgrade does not silently break the regression suite.

All fixtures are synthesised inside the repository under the
project's permissive licence. No third-party copyright is incurred.

## On-disk fixtures (here)

| File | Purpose |
|---|---|
| `txt_with_bom_crlf.txt` | UTF-8 BOM strip + CRLF passthrough (Task 8) |
| `md_with_frontmatter_and_html.md` | YAML frontmatter strip + embedded HTML (Task 8) |
| `mixed_directory/sample.txt` | Recursive ingest cross-format sample (Task 10) |
| `mixed_directory/sample.md` | Recursive ingest cross-format sample (Task 10) |

## In-test synthesised fixtures

The PDF / DOCX / EPUB fixtures are generated on-the-fly inside
`tests/test_ingestion_reliability.py` via helper factories. Synthesis
uses `pypdf.PdfWriter` / `python-docx` / `ebooklib` directly — the
same libraries the extractor calls — so the binary path exercises
the same code that real-world corpora hit. Goldens are computed in
the same run and asserted against expected behaviours (header line
not in any chunk, alpha-ratio > 0.65, etc.) rather than byte-compared,
which keeps the suite resilient against pypdf minor-version drift.

This trades the audit's "commit the binary + commit the golden"
pattern for "commit the synthesis helper + assert on properties" —
both are valid regression-locking strategies, and the second is more
sustainable for a test-driven repo on a moving dependency surface.

## Why "synthesised, not real-world"

Real-world corpora carry institutional copyright + privacy concerns
that block inclusion under the project's permissive licence. The
synthetic fixtures exhibit the same **technical phenomena** the audit
documented (corrupt glyphs, multi-line headers, ToC underscore
leaders, URL noise, BOM + CRLF, YAML frontmatter, embedded HTML)
without redistributing any third-party content.

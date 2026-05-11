---
title: Phase 15 fixture
author: ForgeLM tests
date: 2026-05-11
tags:
  - phase-15
  - regression
---

<!-- markdownlint-disable MD025 MD033 — Phase 15 fixture intentionally
     ships a top-level `#` heading PLUS raw HTML passthrough so the
     `_extract_markdown` helper can be exercised against both failure
     modes in a single file. The Codacy notices are expected, not bugs. -->

# Body heading

This is the body content that should survive YAML-frontmatter stripping.
It uses a fully-formed sentence so the alpha-ratio quality check stays
comfortably above the 70 % threshold.

<div class="callout">
HTML blocks pass through verbatim today; Wave 3 may revisit them.
</div>

Another paragraph closes the sample so the chunker has at least two
paragraph boundaries to work with under the paragraph strategy.

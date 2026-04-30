"""Phase 12: heuristic quality filter (audit-side, opt-in).

Gopher / C4 / RefinedWeb-style row-level checks that surface in the
audit's ``quality_summary`` block when ``enable_quality_filter=True``.
Heuristics are intentionally conservative (none of them block training;
they flag rows for the operator to inspect). Markdown fenced code blocks
are stripped before applying prose heuristics so legitimate
code-instruction SFT data isn't penalised for not reading like prose.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Phase 12: heuristic quality filter (audit-side, opt-in)
# ---------------------------------------------------------------------------


_QUALITY_CHECKS: Tuple[str, ...] = (
    "low_alpha_ratio",
    "low_punct_endings",
    "abnormal_mean_word_length",
    "short_paragraphs",
    "repeated_lines",
)
"""Per-row quality-heuristic identifiers. Same names land in the audit
JSON's ``quality_summary.by_check`` map; tests pin them so a future
addition / rename doesn't silently break consumers."""


_WORD_PATTERN = re.compile(r"\b[\w']+\b", re.UNICODE)
# ``[ \t]*$`` not ``\s*$``: callers pass single lines (no embedded
# newlines), so the ``\s`` form's newline-overlap potential is dead
# weight per docs/standards/regex.md rule 5.
_PUNCT_END_PATTERN = re.compile(r"[.!?…\"'\)\]][ \t]*$")


def _is_code_fence_open(line: str) -> Optional[Tuple[str, int]]:
    """Return ``(fence_char, run_length)`` if ``line`` opens a CommonMark fence, else ``None``.

    CommonMark §4.5: an opening fence is 3+ identical backticks (or
    tildes), optionally indented by up to 3 spaces, possibly followed by
    an info string. We capture the **run length** because a valid
    closing fence must use at least as many fence characters as the
    opener — a 4-backtick block is *not* closed by a 3-backtick line.
    """
    stripped = line.lstrip(" ")
    if len(line) - len(stripped) > 3:
        return None  # 4+ spaces: indented code block, not a fence
    if stripped.startswith("```"):
        run = len(stripped) - len(stripped.lstrip("`"))
        # CommonMark §4.5: the info string after a backtick fence may not
        # contain backticks. Lines like ``` ```lang `oops`` are *not*
        # opening fences — treating them as one would mis-parse inline
        # code in prose as a code block.
        rest = stripped[run:]
        if "`" in rest:
            return None
        return ("`", run)
    if stripped.startswith("~~~"):
        run = len(stripped) - len(stripped.lstrip("~"))
        return ("~", run)
    return None


def _is_code_fence_close(line: str, fence_char: str, min_run: int) -> bool:
    """Return ``True`` when ``line`` is a valid CommonMark close for ``(fence_char, min_run)``.

    Stricter than ``_is_code_fence_open``:

    1. The closing fence may **not** carry an info string — only the
       fence run + optional trailing whitespace. ``~~~bash`` opens a
       tilde block but does **not** close one.
    2. Per CommonMark §4.5, the close must use **at least as many**
       fence characters as the opener, so a ``\\`\\`\\``\\``` block
       (4 backticks) is not closed by a ``\\`\\`\\``` line (3 backticks).
    """
    stripped = line.lstrip(" ")
    if len(line) - len(stripped) > 3:
        return False
    body = stripped.rstrip(" \t\r\n")
    if len(body) < min_run:
        return False
    return all(ch == fence_char for ch in body)


def _strip_code_fences(text: str) -> str:
    """Remove CommonMark fenced code blocks (``\\`\\`\\``` or ``~~~``); leave inline code intact.

    Implemented as a per-line state machine rather than a single regex
    so the cost is provably O(n). The previous regex
    ``^ {0,3}(?P<fence>\\`{3,}|~{3,})[^\\n]*\\n.*?^ {0,3}(?P=fence)[ \\t]*$``
    used ``.*?`` with a back-reference under DOTALL, which static
    analysers (SonarCloud python:S5852) flag as a polynomial-runtime
    risk — and the same line-walker pattern is already used in
    :func:`forgelm.ingestion._markdown_sections`, so we use it here too.

    Tracks the **opening fence char + run length** per CommonMark §4.5
    so a 4-backtick opener isn't prematurely closed by a 3-backtick line.
    Behaviour matches the old regex bit-for-bit on the standard test
    fixtures: a fully-closed fence is replaced by the surrounding line
    breaks (``intro\\n...block...\\nouter`` -> ``intro\\n\\nouter``); an
    *unclosed* fence is left untouched.
    """
    out: List[str] = []
    open_fence: Optional[Tuple[str, int]] = None  # (char, min_close_length) while in block
    block_buffer: List[str] = []  # accumulates an in-progress block

    for line in text.splitlines(keepends=True):
        if open_fence is None:
            fence_info = _is_code_fence_open(line)
            if fence_info is not None:
                open_fence = fence_info
                block_buffer = [line]  # buffer in case the block is unclosed
            else:
                out.append(line)
            continue
        # Inside an active block: buffer the line, then check for close.
        block_buffer.append(line)
        fence_char, min_run = open_fence
        if _is_code_fence_close(line, fence_char, min_run):
            # The regex consumed BEGIN through CLOSE inclusive but stopped
            # before the trailing ``\n`` — preserve that newline so the
            # surrounding lines aren't glued together.
            if block_buffer[-1].endswith("\n"):
                out.append("\n")
            block_buffer = []
            open_fence = None

    # Unclosed block: flush the buffered lines back to output verbatim
    # (the old regex would have failed to match a partial block, so the
    # surrounding text stayed as-is).
    if block_buffer:
        out.extend(block_buffer)

    return "".join(out)


def _check_low_alpha_ratio(prose: str) -> Optional[str]:
    """Flag prose whose letter-to-non-whitespace ratio falls below 70 %."""
    non_ws = [c for c in prose if not c.isspace()]
    if not non_ws:
        return None
    alpha_ratio = sum(1 for c in non_ws if c.isalpha()) / len(non_ws)
    return "low_alpha_ratio" if alpha_ratio < 0.70 else None


def _check_low_punct_endings(lines: List[str]) -> Optional[str]:
    """Flag when fewer than 50 % of non-empty lines end with punctuation."""
    if not lines:
        return None
    punct_ratio = sum(1 for ln in lines if _PUNCT_END_PATTERN.search(ln)) / len(lines)
    return "low_punct_endings" if punct_ratio < 0.50 else None


def _check_abnormal_mean_word_length(words: List[str]) -> Optional[str]:
    """Flag mean word length outside the 3-12 char window."""
    mean_wl = sum(len(w) for w in words) / len(words)
    return "abnormal_mean_word_length" if mean_wl < 3.0 or mean_wl > 12.0 else None


def _check_short_paragraphs(prose: str) -> Optional[str]:
    """Flag when > 50 % of ``\\n\\n``-blocks contain < 5 words."""
    paragraphs = [p for p in prose.split("\n\n") if p.strip()]
    if not paragraphs:
        return None
    short = sum(1 for p in paragraphs if len(_WORD_PATTERN.findall(p)) < 5)
    return "short_paragraphs" if short / len(paragraphs) > 0.50 else None


def _check_repeated_lines(lines: List[str]) -> Optional[str]:
    """Flag when the top-3 *actually-repeating* lines (count >= 2) cover > 30 %.

    A naive "top-3 distinct lines" rule fires on any short all-unique
    document; pinning on count >= 2 isolates real boilerplate (repeated
    headers / footers / disclaimers).
    """
    if len(lines) < 3:
        return None
    line_counts = Counter(lines)
    repeating = [(ln, n) for ln, n in line_counts.items() if n >= 2]
    if not repeating:
        return None
    repeating.sort(key=lambda kv: kv[1], reverse=True)
    top3_total = sum(n for _, n in repeating[:3])
    return "repeated_lines" if top3_total / len(lines) > 0.30 else None


def _row_quality_flags(text: Optional[str]) -> List[str]:
    """Return the subset of :data:`_QUALITY_CHECKS` that flag ``text``.

    Heuristics are intentionally conservative (Gopher / C4 / RefinedWeb
    style — none of them block training; they surface in the audit so the
    operator decides whether to filter). Empty / non-string input
    short-circuits with an empty list so :class:`_StreamingAggregator`
    can call this on every row without per-call type checks.

    Fenced markdown code blocks (``` ... ``` or ``~~~ ... ~~~``) are stripped
    before applying prose heuristics — code is legitimate SFT content but
    trips ``low_alpha_ratio`` / ``low_punct_endings`` / ``short_paragraphs``
    on its own. If the row is **purely** code (nothing left after
    stripping), the function returns ``[]`` rather than flagging the
    whole row.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    prose = _strip_code_fences(text).strip()
    if not prose:
        # Pure code-fence rows: don't flag — this is legitimate SFT data
        # for code-instruction models, not noise.
        return []
    words = _WORD_PATTERN.findall(prose)
    if not words:
        return ["low_alpha_ratio"]
    lines = [ln for ln in prose.splitlines() if ln.strip()]

    # Each helper returns either a flag name or ``None``; collect the hits.
    candidates = [
        _check_low_alpha_ratio(prose),
        _check_low_punct_endings(lines),
        _check_abnormal_mean_word_length(words),
        _check_short_paragraphs(prose),
        _check_repeated_lines(lines),
    ]
    return [flag for flag in candidates if flag is not None]


__all__ = [
    "_QUALITY_CHECKS",
    "_WORD_PATTERN",
    "_PUNCT_END_PATTERN",
    "_is_code_fence_open",
    "_is_code_fence_close",
    "_strip_code_fences",
    "_check_low_alpha_ratio",
    "_check_low_punct_endings",
    "_check_abnormal_mean_word_length",
    "_check_short_paragraphs",
    "_check_repeated_lines",
    "_row_quality_flags",
]

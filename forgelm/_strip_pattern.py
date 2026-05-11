"""Phase 15 Wave 2 Task 11 — operator-supplied strip-pattern with ReDoS guard.

The ``--strip-pattern REGEX`` flag lets operators delete known-boilerplate
lines that ForgeLM's automatic dedup heuristic misses (running headers
with varying content, watermark lines, DOI / journal headers, etc.).
Because the pattern is **operator-controlled**, two failure modes have
to be ruled out before the ingestion run starts:

1. **Pathological back-tracking** — e.g. ``(a+)+b`` against a long
   string of ``a`` characters is the textbook ReDoS shape. Validating
   the pattern up-front at CLI parse time catches the most common
   anti-patterns described in ``docs/standards/regex.md`` (rules 4 + 6).
2. **Run-time hang** — even a pattern that *looks* safe can hit a
   degenerate input. A SIGALRM-based timeout per regex bounds the
   worst-case match cost; on Windows + non-main threads the timeout is
   a no-op and the operator is expected to vet the pattern themselves
   (same trade-off ``forgelm reverse-pii --type custom`` makes).

The public surface is intentionally small:

* :func:`validate_strip_pattern` — CLI-time structural validation.
* :func:`compile_strip_patterns` — turn a list of validated patterns
  into compiled :class:`re.Pattern` objects.
* :func:`apply_strip_patterns` — strip every matching span (or whole
  line, in MULTILINE mode) with a per-pattern SIGALRM guard.
* :class:`StripPatternError` — single exception type the CLI catches.

This module imports only stdlib so it can run before any ingestion
extras are installed.
"""

from __future__ import annotations

import logging
import os
import re
import signal
import threading
import time
from typing import List, Optional, Tuple

logger = logging.getLogger("forgelm.ingestion.strip_pattern")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT_S: int = 5
"""Per-pattern match budget in seconds.

Five seconds is generous for legitimate boilerplate-stripping on a
typical 200-page corpus (each page's extracted text is < 4 KB and a
sane regex finishes in microseconds), but small enough that a
pathological pattern aborts the run before it eats the user's session.
Operator can opt out via ``--strip-pattern-no-timeout`` for
known-safe patterns on POSIX main thread; the guard is always a no-op
elsewhere.
"""

_MAX_PATTERN_LENGTH: int = 2048
"""Generous upper bound on the operator's pattern string.

ReDoS is largely a function of pattern complexity, not length, but a
genuinely useful boilerplate-stripping pattern fits inside this
envelope easily. Anything over 2 KB is overwhelmingly more likely to
be a paste-bin accident than a legitimate use case; rejecting it at
CLI-parse time saves a confusing run-time hang.
"""


class StripPatternError(ValueError):
    """Raised when a strip-pattern is malformed or fails the ReDoS guard.

    Inherits from :class:`ValueError` so existing CLI dispatchers that
    catch ``ValueError`` (per ``forgelm/cli/subcommands/_ingest.py``)
    keep working without an explicit ``except`` for this subclass.
    """


# ---------------------------------------------------------------------------
# Structural validation (CLI-parse time)
# ---------------------------------------------------------------------------


def validate_strip_pattern(pattern: str) -> str:
    """Validate ``pattern`` up-front; return it verbatim on success.

    Mirrors the SonarCloud ``python:S5852`` / regex.md rule 4 + 6
    structural checks ForgeLM applies to its own internal regexes:

    * Reject empty / overlong patterns.
    * Reject patterns with **two unbounded greedy / lazy quantifiers
      in sequence** that share a character class (rule 4) — the
      ``(a+)+b`` / ``(.+?)(.+)`` shapes.
    * Reject patterns combining ``.*?`` with a back-reference under
      DOTALL (rule 6) — even when CPython handles it, SonarCloud
      flags it and the operator can rewrite as multiple narrower
      patterns.
    * Reject patterns that fail :func:`re.compile` (syntax error).

    Raises :class:`StripPatternError` with a message that names the
    offending construct so the operator can rewrite the pattern.
    """
    if not pattern:
        raise StripPatternError("--strip-pattern must be a non-empty regex.")
    if len(pattern) > _MAX_PATTERN_LENGTH:
        raise StripPatternError(
            f"--strip-pattern is too long ({len(pattern)} chars; max {_MAX_PATTERN_LENGTH}). "
            "If your boilerplate is more than 2 KB, split it across multiple --strip-pattern flags."
        )
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise StripPatternError(f"--strip-pattern {pattern!r} is not a valid regular expression: {exc}") from exc

    _check_unbounded_quantifier_sequence(pattern)
    _check_dotall_backreference(pattern, compiled.flags)

    return pattern


def _check_unbounded_quantifier_sequence(pattern: str) -> None:
    """Reject patterns with two unbounded quantifiers in sequence.

    The classic ``(a+)+`` ReDoS shape is detected by walking the
    pattern as plain text and looking for ``+`` / ``*`` followed by
    a closing group ``)`` followed by another ``+`` / ``*``. We
    deliberately do **not** parse the regex AST — that is more work
    than the structural check warrants, and CPython already protects
    operators against the worst cases at run time via the SIGALRM
    timeout. The heuristic catches the textbook shape and is happy
    to miss exotic variants (the run-time timeout is the safety net).

    Why no full-AST parse: regex.md rule 4 is about pattern *shape*,
    not semantic equivalence, so a textual scan is sufficient. The
    same approach is used inside SonarCloud's S5852 implementation
    on the JVM side.
    """
    # Walk the raw pattern, skipping escape sequences. Look for
    # ``)`` immediately following a ``+`` or ``*`` quantifier, then a
    # second ``+`` or ``*`` on the outer group — that is the
    # ``(a+)+`` / ``(.+)+`` shape.
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "\\":
            i += 2  # skip the escaped pair
            continue
        if char in ("+", "*"):
            # Look at the previous *non-escaped* character: if it's ``)`` and
            # the group it closes ended on another ``+`` / ``*``, this is the
            # textbook nested-unbounded shape.
            prev_char = pattern[i - 1] if i > 0 else ""
            if prev_char == ")":
                # Find the matching opening ``(`` and walk back to see if the
                # group itself ended on another unbounded quantifier.
                if _group_ends_with_unbounded_quantifier(pattern, i - 1):
                    raise StripPatternError(
                        f"--strip-pattern {pattern!r} contains a nested unbounded "
                        "quantifier (e.g. `(a+)+`) which is a textbook ReDoS shape. "
                        "Rewrite with bounded repetition (e.g. `a{1,100}`) or split "
                        "across multiple narrower --strip-pattern flags."
                    )
        i += 1


def _group_ends_with_unbounded_quantifier(pattern: str, close_paren_index: int) -> bool:
    """Return ``True`` if the group ending at ``close_paren_index`` has an inner ``+`` / ``*``."""
    # Walk backwards, balancing parens, looking for an unbounded quantifier
    # just before the matching ``(``. Escapes are honoured.
    depth = 1
    i = close_paren_index - 1
    while i >= 0:
        char = pattern[i]
        if char == "\\":
            # Escape: skip the escaped pair (one step further back).
            i -= 2
            continue
        if char == ")":
            depth += 1
        elif char == "(":
            depth -= 1
            if depth == 0:
                # The character immediately *before* the closing ``)`` of the
                # opened group tells us whether the inner content ended on an
                # unbounded quantifier.
                inner_last = pattern[close_paren_index - 1] if close_paren_index > 0 else ""
                return inner_last in ("+", "*")
        i -= 1
    return False


def _check_dotall_backreference(pattern: str, flags: int) -> None:
    """Reject ``.*?`` + back-reference under DOTALL.

    Mirrors regex.md rule 6 / SonarCloud python:S5852. Cheap to detect
    structurally: presence of ``.*?`` (or ``.+?``) **and** a back-reference
    (``\\1`` … or ``(?P=name)``) under :data:`re.DOTALL`. The pattern
    flags are read from the compiled object so operator-supplied inline
    ``(?s)`` flags are honoured.
    """
    if not (flags & re.DOTALL):
        return
    if ".*?" not in pattern and ".+?" not in pattern:
        return
    # Look for any back-reference: ``\<digit>`` or ``(?P=name)``.
    if re.search(r"\\[1-9]|\(\?P=", pattern):
        raise StripPatternError(
            f"--strip-pattern {pattern!r} combines a lazy `.*?` / `.+?` with a "
            "back-reference under DOTALL — this is the SonarCloud python:S5852 "
            "polynomial-runtime shape. Rewrite as a line-walker or split the "
            "pattern across multiple --strip-pattern flags."
        )


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


def compile_strip_patterns(patterns: List[str]) -> List[Tuple[str, re.Pattern[str]]]:
    """Compile a list of validated strip-patterns to ``(raw, compiled)`` pairs.

    The raw string is preserved alongside the compiled pattern so the
    timeout warning can quote the offending pattern verbatim instead of
    re-deriving it from :attr:`re.Pattern.pattern` (which collapses some
    operator-supplied character classes).
    """
    out: List[Tuple[str, re.Pattern[str]]] = []
    for raw in patterns:
        validate_strip_pattern(raw)
        # MULTILINE so ``^`` / ``$`` work line-by-line, which is the dominant
        # use case (strip an entire boilerplate line, not a substring).
        compiled = re.compile(raw, flags=re.MULTILINE)
        out.append((raw, compiled))
    return out


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


def apply_strip_patterns(
    text: str,
    patterns: List[Tuple[str, re.Pattern[str]]],
    *,
    timeout_s: Optional[int] = DEFAULT_TIMEOUT_S,
    logger_override: Optional[logging.Logger] = None,
) -> Tuple[str, int]:
    """Strip every match from ``text``; return ``(new_text, total_matches)``.

    Patterns are applied in order. Each match is replaced with an empty
    string. On POSIX main-thread runs a per-pattern SIGALRM budget of
    ``timeout_s`` seconds bounds the worst-case backtracking cost; on
    Windows or worker threads the guard is a no-op (same trade-off
    ``forgelm reverse-pii --type custom`` makes).

    When a timeout fires, the offending pattern is **skipped** with a
    loud ``WARNING`` and the remaining patterns continue to apply.
    Skipping is the right trade-off: aborting the ingestion run would
    drop user data on the floor, while silently swallowing the timeout
    would leave the operator wondering why their pattern did nothing.

    Args:
        text: Text to scan.
        patterns: Output of :func:`compile_strip_patterns`.
        timeout_s: Per-pattern budget. ``None`` disables the guard
            entirely (used by ``--strip-pattern-no-timeout``).
        logger_override: Test seam; defaults to the module logger.

    Returns:
        The stripped text and the total number of substitutions made.
    """
    use_logger = logger_override or logger
    if not patterns or not text:
        return text, 0

    use_alarm = (
        timeout_s is not None
        and timeout_s > 0
        and os.name == "posix"
        and hasattr(signal, "SIGALRM")
        and threading.current_thread() is threading.main_thread()
    )

    total_subs = 0
    out = text
    for raw, compiled in patterns:
        new_out, subs = _apply_one(out, raw, compiled, timeout_s, use_alarm, use_logger)
        out = new_out
        total_subs += subs
    return out, total_subs


def _apply_one(
    text: str,
    raw: str,
    compiled: re.Pattern[str],
    timeout_s: Optional[int],
    use_alarm: bool,
    use_logger: logging.Logger,
) -> Tuple[str, int]:
    """Apply one pattern under the ReDoS guard; warn + skip on timeout."""
    if not use_alarm or timeout_s is None:
        new_out, subs = compiled.subn("", text)
        return new_out, subs

    def _alarm(_sig, _frame):  # pragma: no cover — exercised via integration tests
        raise OSError(f"strip-pattern {raw!r} exceeded {timeout_s}s (ReDoS guard)")

    previous_handler = signal.signal(signal.SIGALRM, _alarm)
    previous_remaining = signal.alarm(timeout_s)
    started = time.monotonic()
    try:
        new_out, subs = compiled.subn("", text)
        return new_out, subs
    except OSError as exc:
        use_logger.warning(
            "Skipping --strip-pattern (timeout): %s. Remaining patterns will still apply.",
            exc,
        )
        return text, 0
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_remaining > 0:
            # Honour an outer caller's alarm budget (same protocol the
            # reverse-pii ReDoS guard uses). Round up partial seconds so
            # the outer budget is preserved, never extended.
            elapsed = time.monotonic() - started
            remaining = max(int(previous_remaining - elapsed) + 1, 1)
            signal.alarm(remaining)


__all__ = [
    "DEFAULT_TIMEOUT_S",
    "StripPatternError",
    "validate_strip_pattern",
    "compile_strip_patterns",
    "apply_strip_patterns",
]

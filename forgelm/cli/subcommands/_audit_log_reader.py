"""Single-source audit-log JSONL reader for the approval / approvals / purge family.

Background — Wave 2a Round-1 review (XPR-01) flagged that ForgeLM had three
near-identical JSONL parsers across :mod:`._approve` and :mod:`._approvals`,
with a fourth coming in Phase 21 (``forgelm purge``).  Each copy duplicated
the malformed-line accounting, the OSError handling, and the
``isinstance(event, dict)`` guard — so a future fix to any one of those
policies (e.g. switching to streaming reads, adding a maximum line length,
emitting structured error events) would have to be applied in ``N``
places at once.

This module is the single place that policy lives.  Two helpers cover the
two read patterns the family uses:

- :func:`iter_audit_events` — generator yielding ``(line_number, event)``
  pairs.  Skips blank lines + malformed JSON + non-dict roots silently;
  emits one summary warning at the end.  Used by anything that needs to
  walk the whole log (e.g. ``forgelm approvals --pending``).
- :func:`find_latest_event_for_run` — convenience wrapper that returns the
  most-recent event matching a predicate, or ``None``.  Used by the
  approve / reject decision-guard checks.

Both helpers route OSError on file-open through the module logger and
return an empty result so the caller sees a missing log as "no matching
event" rather than as a crash.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, Dict, Iterator, Optional, Tuple

logger = logging.getLogger("forgelm.cli.audit_log_reader")


def iter_audit_events(audit_log_path: str) -> Iterator[Tuple[int, Dict[str, Any]]]:
    """Yield ``(line_number, event_dict)`` from an append-only JSONL audit log.

    Skips blank lines and malformed entries (non-JSON lines, JSON whose
    root is not a ``dict``) silently — emitting a per-skip warning here
    would be very noisy on a long-lived audit log.  The number of skipped
    lines is summarised in a single ``logger.warning`` call when iteration
    finishes (so callers learn about corruption without paying per-line
    log cost).

    Returns nothing (no events yielded, no warning) when:
    - the file does not exist (a freshly-bootstrapped output dir
      legitimately has no audit log yet); or
    - the file cannot be opened (OSError logged at ERROR level so
      operators see why nothing came through).

    The caller is responsible for closing nothing — this generator owns
    the file handle via ``with`` and releases it on iterator exhaustion.
    """
    if not os.path.isfile(audit_log_path):
        return
    try:
        fh = open(audit_log_path, "r", encoding="utf-8")
    except OSError as exc:
        logger.error("Cannot open audit log %s: %s", audit_log_path, exc)
        return
    skipped_lines = 0
    with fh:
        for line_number, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                skipped_lines += 1
                continue
            if not isinstance(event, dict):
                skipped_lines += 1
                continue
            yield line_number, event
    if skipped_lines:
        logger.warning(
            "Skipped %d malformed line(s) while parsing %s.",
            skipped_lines,
            audit_log_path,
        )


def find_latest_event_for_run(
    audit_log_path: str,
    *,
    run_id: str,
    matches: Callable[[Dict[str, Any]], bool],
) -> Optional[Dict[str, Any]]:
    """Return the most-recent event matching ``matches`` for ``run_id``.

    Walks the entire log (audit logs are append-only so "most recent"
    means the last matching entry encountered).  Returns ``None`` when
    no event matches.

    ``matches`` is the predicate the caller cares about — typically
    ``lambda e: e.get("event") == "human_approval.required"`` or a
    membership check against a frozenset of decision-event names.
    Keeping the predicate as a callable lets every caller in the
    approve / approvals / purge family share the parser without
    couping it to a specific event vocabulary.
    """
    latest: Optional[Dict[str, Any]] = None
    for _line_no, event in iter_audit_events(audit_log_path):
        if event.get("run_id") != run_id:
            continue
        if matches(event):
            latest = event
    return latest


__all__ = [
    "iter_audit_events",
    "find_latest_event_for_run",
]

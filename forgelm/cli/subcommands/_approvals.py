"""``forgelm approvals`` listing subcommand (Article 14 follow-up).

The Phase 9 closure shipped ``forgelm approve`` and ``forgelm reject`` so an
operator can act on a single staged run, but it left the *discovery* step
out: an operator who walks up to a workstation cold has no way to ask
"which runs are awaiting my review?".  This module fills the gap.

Two query modes:

- ``forgelm approvals --pending [--output-dir DIR]`` lists every run whose
  audit log carries a ``human_approval.required`` event without a matching
  terminal decision (``human_approval.granted`` / ``human_approval.rejected``).
- ``forgelm approvals --show RUN_ID --output-dir DIR`` prints the full
  approval-related audit chain for a single run plus the on-disk staging
  directory layout.

The audit-log JSONL parser (skip malformed, emit one summary warning at
end) lives in :mod:`._audit_log_reader` and is shared with
:mod:`._approve` (and the upcoming :mod:`._purge`).  The
``output_dir/audit_log.jsonl`` convention + Article 14 event vocabulary
live here so the dispatcher stays cohesive; only the *parser* is shared.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .._exit_codes import EXIT_CONFIG_ERROR, EXIT_SUCCESS, EXIT_TRAINING_ERROR
from .._logging import logger

# Audit event names. Mirror :mod:`._approve` so a future rename of one set
# can't drift across the listing dispatcher and the decision dispatcher.
_EVT_HUMAN_APPROVAL_REQUIRED = "human_approval.required"
_EVT_HUMAN_APPROVAL_GRANTED = "human_approval.granted"
_EVT_HUMAN_APPROVAL_REJECTED = "human_approval.rejected"
_TERMINAL_DECISION_EVENTS = frozenset({_EVT_HUMAN_APPROVAL_GRANTED, _EVT_HUMAN_APPROVAL_REJECTED})

# Default audit-log filename.  Centralised so a future rename does not have to
# touch every dispatcher.
_AUDIT_LOG_FILENAME = "audit_log.jsonl"


def _output_error_and_exit(output_format: str, msg: str, exit_code: int) -> None:
    """Emit ``msg`` as a structured JSON error or a log record, then exit.

    Mirrors :func:`forgelm.cli.subcommands._approve._output_error_and_exit`
    so the JSON envelope contract is identical across the approval family
    of subcommands.
    """
    if output_format == "json":
        print(json.dumps({"success": False, "error": msg}))
    else:
        logger.error(msg)
    sys.exit(exit_code)


# Wave 2a Round-1 review (XPR-01): the JSONL parser was extracted into
# the shared :mod:`._audit_log_reader` module so a future malformed-line
# policy fix lands in one place across the approve / approvals / purge
# family.  The local re-export below preserves the import name tests
# already use (``from forgelm.cli import _iter_audit_events``).
from ._audit_log_reader import iter_audit_events as _iter_audit_events  # noqa: F401,E402


def _collect_pending_runs(audit_log_path: str) -> List[Dict[str, Any]]:
    """Return the list of pending approval requests, newest-first.

    A "pending" run is one whose audit log carries a
    ``human_approval.required`` event whose ``run_id`` does **not** appear
    in any *later* ``human_approval.granted`` / ``human_approval.rejected``
    event after that requirement was issued.

    **Latest-wins semantics** (Wave 2a Round-1 review F-25-03 fix): when a
    run is restarted with the same ``run_id`` after a prior decision —
    e.g. a rejected run is re-staged for a second review — the latest
    ``human_approval.required`` event reflects the current pending state
    and earlier terminal decisions for that ``run_id`` are no longer the
    operative status.  Mirrors :func:`._approve._find_human_approval_decision_event`'s
    "most-recent matching event wins" semantic so the family stays
    consistent.

    Implementation: walk the log in append order, recording the latest
    ``required`` and the latest terminal decision per ``run_id``.  A run
    is pending iff its last ``required`` event came strictly after its
    last terminal decision (or no terminal decision exists).  Line-number
    fallback is used when timestamp is missing so re-imported logs without
    timestamps still have a deterministic ordering.
    """
    latest_required: Dict[str, tuple[int, Dict[str, Any]]] = {}
    latest_decision_line: Dict[str, int] = {}

    for line_no, event in _iter_audit_events(audit_log_path):
        run_id = event.get("run_id")
        if not isinstance(run_id, str):
            # Required field on every approval-gate event; if missing the
            # event is malformed and we cannot reason about it.  Skip.
            continue
        event_name = event.get("event")
        if event_name == _EVT_HUMAN_APPROVAL_REQUIRED:
            latest_required[run_id] = (line_no, event)
        elif event_name in _TERMINAL_DECISION_EVENTS:
            latest_decision_line[run_id] = line_no

    pending = [
        event for run_id, (req_line, event) in latest_required.items() if req_line > latest_decision_line.get(run_id, 0)
    ]
    # Newest-pending first so an operator opening the list sees the most
    # recent request at the top.  ``timestamp`` may be missing on
    # synthetic / hand-edited entries — sort missing values to the bottom.
    pending.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
    return pending


def _collect_run_audit_chain(audit_log_path: str, run_id: str) -> List[Dict[str, Any]]:
    """Return every approval-gate event for ``run_id`` in append order.

    Used by ``--show`` to render the full request → decision chain.  We
    return the events in their on-disk order (which is also wall-clock
    order since the audit log is append-only) so an operator scanning the
    output can read top-to-bottom as the timeline.
    """
    chain: List[Dict[str, Any]] = []
    approval_events = {_EVT_HUMAN_APPROVAL_REQUIRED, *_TERMINAL_DECISION_EVENTS}
    for _line_no, event in _iter_audit_events(audit_log_path):
        if event.get("event") in approval_events and event.get("run_id") == run_id:
            chain.append(event)
    return chain


def _staging_dir_for_event(output_dir: str, event: Dict[str, Any]) -> Optional[str]:
    """Best-effort: return the on-disk staging path the event refers to.

    The trainer records ``staging_path`` on every ``human_approval.required``
    event (Wave 1 round-2 audit-event vocabulary).  Older audit logs may
    pre-date that addition; for those we synthesise the canonical path
    ``<output_dir>/final_model.staging`` and let the caller decide whether
    to fall back when ``os.path.isdir`` is False.

    **Defence in depth (Wave 2a Round-1 review fix):** when an audit log
    lives on shared / unsigned storage, an attacker who can append events
    could plant a ``staging_path`` value pointing outside ``output_dir``
    (e.g. ``/etc``).  ``_staging_contents`` would then leak directory
    listings as a tampered-audit-log oracle.  We reuse the
    ``_staging_path_inside_output_dir`` guard Phase 9's :mod:`._approve`
    module already ships and refuse declared paths that escape the
    operator-supplied ``output_dir`` boundary.
    """
    # Late import via the package facade so the helper resolves through
    # the same monkeypatch surface tests already use for _approve.py.
    from forgelm import cli as _cli_facade

    declared = event.get("staging_path")
    if isinstance(declared, str) and declared:
        if not _cli_facade._staging_path_inside_output_dir(declared, output_dir):
            logger.warning(
                "Refusing staging_path %r from audit event for output_dir %r: "
                "resolved path escapes the output_dir boundary (audit-log tampering "
                "guard).  Falling back to canonical final_model.staging if present.",
                declared,
                output_dir,
            )
            declared = None
    if isinstance(declared, str) and declared:
        return declared
    fallback = os.path.join(output_dir, "final_model.staging")
    return fallback if os.path.isdir(fallback) else None


def _age_seconds(event_timestamp: Optional[str]) -> Optional[float]:
    """Compute ``now - timestamp`` in seconds; ``None`` when unparseable.

    The audit log emits ISO-8601 with a UTC suffix (``+00:00``).  We accept
    a missing or malformed timestamp gracefully because hand-edited test
    fixtures sometimes drop it, and a missing age is far less actionable
    than a stack trace.
    """
    if not isinstance(event_timestamp, str) or not event_timestamp:
        return None
    try:
        # Python 3.10 ``datetime.fromisoformat`` does not accept the ``Z``
        # suffix.  Normalise to ``+00:00`` for older interpreters.
        normalised = event_timestamp.replace("Z", "+00:00")
        when = datetime.fromisoformat(normalised)
    except ValueError:
        return None
    if when.tzinfo is None:
        # Treat naive timestamps as UTC; mirrors how AuditLogger emits them
        # but is defensive against external producers.
        when = when.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - when
    return delta.total_seconds()


def _staging_contents(staging_path: Optional[str]) -> List[str]:
    """List files in ``staging_path`` (sorted) or ``[]`` when missing/unreadable."""
    if not staging_path or not os.path.isdir(staging_path):
        return []
    try:
        return sorted(os.listdir(staging_path))
    except OSError as exc:
        logger.warning("Cannot list staging directory %s: %s", staging_path, exc)
        return []


def _summarise_pending(event: Dict[str, Any], output_dir: str) -> Dict[str, Any]:
    """Build the per-run dict used in ``--pending`` output (text + JSON)."""
    staging_path = _staging_dir_for_event(output_dir, event)
    timestamp = event.get("timestamp")
    return {
        "run_id": event.get("run_id"),
        "staging_path": staging_path,
        "staging_exists": bool(staging_path and os.path.isdir(staging_path)),
        "requested_at": timestamp,
        "age_seconds": _age_seconds(timestamp),
        "metrics": event.get("metrics") or {},
        "config_hash": event.get("config_hash") or event.get("config_fingerprint"),
        "reason": event.get("reason"),
    }


def _format_age(age_seconds: Optional[float]) -> str:
    """Render ``age_seconds`` as a human-friendly ``Nh Mm`` / ``Nd`` string."""
    if age_seconds is None:
        return "unknown"
    if age_seconds < 60:
        return f"{int(age_seconds)}s"
    if age_seconds < 3600:
        return f"{int(age_seconds // 60)}m"
    if age_seconds < 86400:
        hours = int(age_seconds // 3600)
        minutes = int((age_seconds % 3600) // 60)
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    days = int(age_seconds // 86400)
    return f"{days}d"


def _emit_pending_text(pending_summaries: List[Dict[str, Any]]) -> None:
    """Print a tabular pending list (or a friendly empty notice)."""
    if not pending_summaries:
        print("No pending approvals.")
        return
    print(f"Pending approvals ({len(pending_summaries)}):")
    print()
    # Tabular layout.  Plain text (no rich) so the output stays usable in
    # CI logs, redirected files, and SSH sessions without colour support.
    headers = ("RUN_ID", "AGE", "REQUESTED_AT", "STAGING")
    rows = [
        (
            summary["run_id"] or "(missing run_id)",
            _format_age(summary["age_seconds"]),
            summary["requested_at"] or "(unknown)",
            "present" if summary["staging_exists"] else "MISSING",
        )
        for summary in pending_summaries
    ]
    widths = [max(len(h), max(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*("-" * w for w in widths)))
    for row in rows:
        print(fmt.format(*row))


def _emit_pending_json(pending_summaries: List[Dict[str, Any]]) -> None:
    """Print the pending list as a JSON array of summaries."""
    print(
        json.dumps(
            {"success": True, "pending": pending_summaries, "count": len(pending_summaries)},
            indent=2,
        )
    )


def _run_approvals_list_pending(args, output_format: str) -> None:
    """Handle ``forgelm approvals --pending`` end-to-end."""
    output_dir = args.output_dir
    audit_log_path = os.path.join(output_dir, _AUDIT_LOG_FILENAME)
    if not os.path.isfile(audit_log_path):
        # Treat missing audit log the same as "no pending approvals" rather
        # than as an error — a freshly-bootstrapped output dir legitimately
        # has neither yet.  Operators get an informative empty summary.
        if output_format == "json":
            _emit_pending_json([])
        else:
            print(f"No audit log at {audit_log_path}; nothing to list.")
        sys.exit(EXIT_SUCCESS)

    try:
        pending_events = _collect_pending_runs(audit_log_path)
    except OSError as exc:
        _output_error_and_exit(
            output_format,
            f"Failed to scan audit log {audit_log_path!r}: {exc}",
            EXIT_TRAINING_ERROR,
        )

    summaries = [_summarise_pending(event, output_dir) for event in pending_events]
    if output_format == "json":
        _emit_pending_json(summaries)
    else:
        _emit_pending_text(summaries)
    sys.exit(EXIT_SUCCESS)


def _classify_chain(chain: List[Dict[str, Any]]) -> str:
    """Return ``pending`` / ``granted`` / ``rejected`` / ``unknown``."""
    decisions = [e.get("event") for e in chain if e.get("event") in _TERMINAL_DECISION_EVENTS]
    if not decisions:
        # If we have a `required` but no decision, it is pending.  If we
        # have neither, the run is unknown to the audit log.
        if any(e.get("event") == _EVT_HUMAN_APPROVAL_REQUIRED for e in chain):
            return "pending"
        return "unknown"
    # Most-recent decision wins (the chain is already in append order).
    last = decisions[-1]
    if last == _EVT_HUMAN_APPROVAL_GRANTED:
        return "granted"
    return "rejected"


def _emit_show_text(run_id: str, chain: List[Dict[str, Any]], status: str, staging_listing: List[str]) -> None:
    """Render ``--show RUN_ID`` output as a human-readable timeline."""
    print(f"Run: {run_id}")
    print(f"Status: {status}")
    print()
    print("Audit chain (oldest first):")
    if not chain:
        print("  (no approval-gate events found)")
    for event in chain:
        ts = event.get("timestamp", "(no timestamp)")
        name = event.get("event", "(no event name)")
        # Render the most operator-relevant fields; full payload is in JSON
        # output below.
        approver = event.get("approver")
        comment = event.get("comment")
        reason = event.get("reason")
        line = f"  [{ts}] {name}"
        if approver:
            line += f" by {approver}"
        if reason:
            line += f" — {reason}"
        if comment:
            line += f" ({comment})"
        print(line)
    print()
    if staging_listing:
        print(f"Staging contents ({len(staging_listing)} entries):")
        for entry in staging_listing:
            print(f"  - {entry}")
    else:
        print("Staging directory: missing or empty.")


def _emit_show_json(run_id: str, chain: List[Dict[str, Any]], status: str, staging_listing: List[str]) -> None:
    """Render ``--show RUN_ID`` output as a structured JSON object."""
    print(
        json.dumps(
            {
                "success": True,
                "run_id": run_id,
                "status": status,
                "chain": chain,
                "staging_contents": staging_listing,
            },
            indent=2,
        )
    )


def _run_approvals_show(args, output_format: str) -> None:
    """Handle ``forgelm approvals --show <run_id>`` end-to-end."""
    run_id: str = args.show
    output_dir = args.output_dir
    audit_log_path = os.path.join(output_dir, _AUDIT_LOG_FILENAME)
    if not os.path.isfile(audit_log_path):
        _output_error_and_exit(
            output_format,
            f"No audit log at {audit_log_path!r}; cannot show run {run_id!r}.",
            EXIT_CONFIG_ERROR,
        )

    chain = _collect_run_audit_chain(audit_log_path, run_id)
    if not chain:
        _output_error_and_exit(
            output_format,
            f"No approval-gate events found for run_id={run_id!r} in {audit_log_path!r}.",
            EXIT_CONFIG_ERROR,
        )

    status = _classify_chain(chain)
    # Staging path is read from the *first* required event so a
    # post-rename layout (final/ exists, staging/ deleted) still surfaces
    # the originally-staged directory name.
    required_event = next((e for e in chain if e.get("event") == _EVT_HUMAN_APPROVAL_REQUIRED), {})
    staging_path = _staging_dir_for_event(output_dir, required_event) if required_event else None
    staging_listing = _staging_contents(staging_path)

    if output_format == "json":
        _emit_show_json(run_id, chain, status, staging_listing)
    else:
        _emit_show_text(run_id, chain, status, staging_listing)
    sys.exit(EXIT_SUCCESS)


def _run_approvals_cmd(args, output_format: str) -> None:
    """Top-level dispatcher for ``forgelm approvals``.

    Exactly one of ``--pending`` / ``--show RUN_ID`` must be set; argparse
    enforces the mutual exclusion via the parser registrar so this
    function only sees a valid args namespace.
    """
    show_run_id = getattr(args, "show", None)
    if show_run_id:
        _run_approvals_show(args, output_format)
    elif getattr(args, "pending", False):
        _run_approvals_list_pending(args, output_format)
    else:
        # argparse should have prevented this; defensive double-check.
        _output_error_and_exit(
            output_format,
            "forgelm approvals: one of --pending / --show RUN_ID is required.",
            EXIT_CONFIG_ERROR,
        )

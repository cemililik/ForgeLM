"""``forgelm approve`` and ``forgelm reject`` dispatchers (Article 14).

The two commands share the audit-event helper set (resolve approver, find
the matching ``human_approval.required`` event, load training metrics from
the on-disk manifest, build a webhook notifier from the co-located config)
and the ``_run_*_cmd`` dispatchers themselves. Co-locating them avoids
splitting cohesive helpers across files.
"""

from __future__ import annotations

import json
import os
import sys
import types
from typing import Optional

import yaml

from .._exit_codes import EXIT_CONFIG_ERROR, EXIT_TRAINING_ERROR
from .._logging import logger

_STAGING_SUFFIX = ".staging"


def _resolve_approver_identity() -> str:
    """Resolve the operator identity for an approve/reject audit entry.

    Mirrors :class:`forgelm.compliance.AuditLogger`'s operator resolution so
    a `human_approval.granted` / `human_approval.rejected` event identifies
    the human exactly the way pre-existing pipeline events do:

    1. ``FORGELM_OPERATOR`` env var (highest priority — explicit operator
       identification, used in CI/CD and shared workstation setups).
    2. ``getpass.getuser()`` (the OS-reported username; falls back to the
       ``USER`` / ``USERNAME`` env var on its own).
    3. ``"anonymous"`` if both fail (no valid env vars and no shell session).

    Pulled out so the approve/reject handlers don't reach into AuditLogger's
    constructor logic and so the test harness has a single hook to monkey-patch.
    """
    explicit = os.getenv("FORGELM_OPERATOR")
    if explicit:
        return explicit
    try:
        import getpass

        return getpass.getuser()
    except (KeyError, OSError, ImportError):
        return "anonymous"


def _find_human_approval_required_event(audit_log_path: str, run_id: str) -> Optional[dict]:
    """Return the most-recent ``human_approval.required`` event for *run_id*.

    Reads ``audit_log.jsonl`` line-by-line to keep memory usage flat for
    long-lived training directories. Returns ``None`` when no matching event
    exists. Malformed lines are skipped and counted; the operator gets a
    warning if any lines were skipped so a corrupt entry can't silently mask
    a genuine "no event" result.
    """
    if not os.path.isfile(audit_log_path):
        return None

    latest_match = None
    skipped_lines = 0
    try:
        fh = open(audit_log_path, "r", encoding="utf-8")
    except OSError as exc:
        logger.error("Cannot open audit log %s: %s", audit_log_path, exc)
        return None
    with fh:
        for raw in fh:
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
            if event.get("event") == "human_approval.required" and event.get("run_id") == run_id:
                latest_match = event
    if skipped_lines:
        logger.warning("Skipped %d malformed line(s) while parsing %s.", skipped_lines, audit_log_path)
    return latest_match


_TERMINAL_DECISION_EVENTS = frozenset({"human_approval.granted", "human_approval.rejected"})


def _find_human_approval_decision_event(audit_log_path: str, run_id: str) -> Optional[dict]:
    """Return the most-recent terminal decision event for *run_id*, or None.

    A terminal decision is either ``human_approval.granted`` or
    ``human_approval.rejected``. Finding one before attempting promotion
    prevents double-approve and approve-after-reject races.
    """
    if not os.path.isfile(audit_log_path):
        return None

    latest_decision = None
    try:
        fh = open(audit_log_path, "r", encoding="utf-8")
    except OSError as exc:
        logger.error("Cannot open audit log %s: %s", audit_log_path, exc)
        return None
    with fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("event") in _TERMINAL_DECISION_EVENTS and event.get("run_id") == run_id:
                latest_decision = event
    return latest_decision


def _atomic_rename_or_move(src: str, dst: str) -> str:
    """Atomically promote *src* → *dst*.

    Tries ``os.rename`` first — atomic on the same filesystem and the only
    operation that meaningfully prevents a concurrent ``forgelm approve``
    on the same staging directory from racing. Falls back to ``shutil.move``
    on ``OSError(EXDEV)`` so cross-device output mounts keep working.

    Returns the strategy used (``"rename"`` or ``"move"``) so the caller
    can record it in the audit event.
    """
    import errno
    import shutil

    try:
        os.rename(src, dst)
        return "rename"
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        logger.debug(
            "Staging directory %s and final directory %s live on different filesystems; "
            "falling back to shutil.move (copy + delete). The promotion is no longer "
            "atomic, but the staging artefacts are preserved on copy failure.",
            src,
            dst,
        )
        shutil.move(src, dst)
        return "move"


def _load_metrics_from_manifest(output_dir: str) -> dict:
    """Read final metrics from ``compliance/training_manifest.yaml`` if present."""
    manifest_path = os.path.join(output_dir, "compliance", "training_manifest.yaml")
    if not os.path.isfile(manifest_path):
        return {}
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            manifest = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Could not read training manifest at %s: %s", manifest_path, exc)
        return {}
    metrics = manifest.get("final_metrics", {})
    return metrics if isinstance(metrics, dict) else {}


def _build_approval_notifier(output_dir: str):
    """Construct a WebhookNotifier from a co-located forgelm config, if any.

    Approve / reject runs do not require ``--config``; the operator just
    points at the training output directory. We look for the webhook config
    inside ``<output_dir>/compliance/compliance_report.json``; if it is not
    there the notifier returns a no-op ``WebhookNotifier`` whose
    ``_resolve_url`` yields ``None`` so the gate still completes cleanly.
    """
    from ...webhook import WebhookNotifier

    class _Carrier:
        def __init__(self, webhook_cfg):
            # WebhookNotifier accesses self.config (= config.webhook) via attribute
            # lookup (.url, .notify_on_success, etc.). The co-located config is a
            # plain JSON dict, so convert it to a SimpleNamespace before handing it
            # to WebhookNotifier to avoid AttributeError on dict-style values.
            if isinstance(webhook_cfg, dict):
                self.webhook = types.SimpleNamespace(**webhook_cfg)
            else:
                self.webhook = webhook_cfg  # None → _resolve_url returns None cleanly

    config_path = os.path.join(output_dir, "compliance", "compliance_report.json")
    webhook_cfg = None
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                report = json.load(fh)
            if isinstance(report, dict):
                raw_cfg = report.get("webhook_config")
                webhook_cfg = raw_cfg if isinstance(raw_cfg, dict) else None
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("Could not load co-located webhook config from %s: %s", config_path, exc)
    return WebhookNotifier(_Carrier(webhook_cfg))


def _output_error_and_exit(output_format: str, msg: str, exit_code: int) -> None:
    """Emit *msg* as a structured JSON error or a log record, then exit."""
    if output_format == "json":
        print(json.dumps({"success": False, "error": msg}))
    else:
        logger.error(msg)
    sys.exit(exit_code)


def _run_approve_cmd(args, output_format: str) -> None:
    """Promote ``final_model.staging/`` → ``final_model/`` after human review."""
    # Late import via the package facade so monkeypatched
    # ``forgelm.cli._build_approval_notifier`` references resolve correctly.
    from forgelm import cli as _cli_facade

    output_dir = args.output_dir
    run_id = args.run_id
    audit_log_path = os.path.join(output_dir, "audit_log.jsonl")

    # Read the audit event first so we can use the trainer-recorded staging_path
    # (which reflects the configured final_model_dir) rather than a hardcoded default.
    required_event = _cli_facade._find_human_approval_required_event(audit_log_path, run_id)
    if required_event is None:
        _output_error_and_exit(
            output_format,
            f"No human_approval.required event for run_id={run_id!r} found in {audit_log_path!r}. "
            "Refusing to promote — verify the run_id matches the original training run.",
            EXIT_CONFIG_ERROR,
        )

    decision_event = _cli_facade._find_human_approval_decision_event(audit_log_path, run_id)
    if decision_event is not None:
        prior = decision_event.get("event", "unknown")
        _output_error_and_exit(
            output_format,
            f"Run {run_id!r} already has a terminal decision ({prior!r}). "
            "Refusing to promote — re-approve is not allowed.",
            EXIT_CONFIG_ERROR,
        )

    staging_path = required_event.get("staging_path") or os.path.join(output_dir, f"final_model{_STAGING_SUFFIX}")
    # Derive final_path by stripping the staging suffix (and any runtime suffix
    # appended after it, such as ".<run_id>") from staging_path. rfind locates
    # the last occurrence of _STAGING_SUFFIX so "final_model.staging.abc123"
    # correctly yields "final_model" regardless of any trailing run_id segment.
    _idx = staging_path.rfind(_STAGING_SUFFIX)
    final_path = staging_path[:_idx] if _idx != -1 else staging_path

    if not os.path.isdir(staging_path):
        _output_error_and_exit(
            output_format,
            f"Staging directory not found at {staging_path!r}. "
            "Either the run did not exit with code 4, or it was already approved/cleaned up.",
            EXIT_CONFIG_ERROR,
        )

    if os.path.lexists(final_path):
        _output_error_and_exit(
            output_format,
            f"Cannot promote: final directory already exists at {final_path!r}. Move or delete it first.",
            EXIT_CONFIG_ERROR,
        )

    try:
        promote_strategy = _cli_facade._atomic_rename_or_move(staging_path, final_path)
    except OSError as exc:
        _output_error_and_exit(
            output_format,
            f"Failed to promote {staging_path!r} → {final_path!r}: {exc}",
            EXIT_TRAINING_ERROR,
        )

    from ...compliance import AuditLogger

    audit = AuditLogger(output_dir, run_id=run_id)
    approver = _cli_facade._resolve_approver_identity()
    audit.log_event(
        "human_approval.granted",
        gate="final_model",
        run_id=run_id,
        approver=approver,
        comment=args.comment or "",
        promote_strategy=promote_strategy,
    )

    metrics = _cli_facade._load_metrics_from_manifest(output_dir)
    notifier = _cli_facade._build_approval_notifier(output_dir)
    run_name = os.path.basename(os.path.normpath(output_dir)) or "approved"
    notifier.notify_success(run_name=run_name, metrics=metrics)

    if output_format == "json":
        print(
            json.dumps(
                {
                    "success": True,
                    "run_id": run_id,
                    "approver": approver,
                    "final_model_path": final_path,
                    "promote_strategy": promote_strategy,
                },
                indent=2,
            )
        )
    else:
        logger.info("Approved run %s; final model promoted to %s.", run_id, final_path)


def _run_reject_cmd(args, output_format: str) -> None:
    """Record a human-approval rejection (preserves staging directory)."""
    from forgelm import cli as _cli_facade

    output_dir = args.output_dir
    run_id = args.run_id
    audit_log_path = os.path.join(output_dir, "audit_log.jsonl")

    required_event = _cli_facade._find_human_approval_required_event(audit_log_path, run_id)
    if required_event is None:
        _output_error_and_exit(
            output_format,
            f"No human_approval.required event for run_id={run_id!r} found in {audit_log_path!r}. "
            "Refusing to record a rejection on a run that did not request one.",
            EXIT_CONFIG_ERROR,
        )

    decision_event = _cli_facade._find_human_approval_decision_event(audit_log_path, run_id)
    if decision_event is not None:
        prior = decision_event.get("event", "unknown")
        _output_error_and_exit(
            output_format,
            f"Run {run_id!r} already has a terminal decision ({prior!r}). "
            "Refusing to record another decision — re-rejection is not allowed.",
            EXIT_CONFIG_ERROR,
        )

    staging_path = required_event.get("staging_path") or os.path.join(output_dir, f"final_model{_STAGING_SUFFIX}")

    if not os.path.isdir(staging_path):
        _output_error_and_exit(
            output_format,
            f"Staging directory not found at {staging_path!r}. Nothing to reject.",
            EXIT_CONFIG_ERROR,
        )

    from ...compliance import AuditLogger

    audit = AuditLogger(output_dir, run_id=run_id)
    approver = _cli_facade._resolve_approver_identity()
    audit.log_event(
        "human_approval.rejected",
        gate="final_model",
        run_id=run_id,
        approver=approver,
        comment=args.comment or "",
        staging_path=staging_path,
    )

    notifier = _cli_facade._build_approval_notifier(output_dir)
    run_name = os.path.basename(os.path.normpath(output_dir)) or "rejected"
    reason = f"human_approval.rejected: {args.comment}" if args.comment else "human_approval.rejected"
    notifier.notify_failure(run_name=run_name, reason=reason)

    if output_format == "json":
        print(
            json.dumps(
                {
                    "success": True,
                    "run_id": run_id,
                    "approver": approver,
                    "staging_path": staging_path,
                    "comment": args.comment or "",
                },
                indent=2,
            )
        )
    else:
        logger.info(
            "Rejected run %s; staging directory preserved at %s for forensic review.",
            run_id,
            staging_path,
        )

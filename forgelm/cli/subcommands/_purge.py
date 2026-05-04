"""``forgelm purge`` subcommand (Phase 21 — GDPR Article 17 erasure).

Implements the operator-facing surface specified in
``docs/analysis/code_reviews/gdpr-erasure-design-202605021414.md``:

- ``forgelm purge --row-id <id> --corpus <path>`` — atomic JSONL row
  erasure with hashed audit event (Article 17 right-to-erasure for
  training corpus rows).
- ``forgelm purge --run-id <id> --kind {staging,artefacts}`` —
  run-scoped artefact erasure (staging directory or compliance bundle).
- ``forgelm purge --check-policy [--config <path>]`` — read-only
  retention-policy violation report against the loaded config's
  ``retention:`` block.

Audit-event vocabulary (six new events per design §5.1):

- ``data.erasure_requested`` — emitted FIRST, before any deletion;
  carries the hashed ``target_id`` so a forensic reviewer sees the
  intent even if the deletion itself fails.
- ``data.erasure_completed`` — emitted LAST after the disk operation
  succeeded; carries ``bytes_freed`` + ``files_modified`` + (corpus
  mode) ``pre_erasure_line_number``.
- ``data.erasure_failed`` — emitted when the disk operation raised;
  the chain shows ``request → fail`` instead of ``request → complete``,
  so an operator scanning the log can spot the unfinished erasure.
- ``data.erasure_warning_memorisation`` — corpus row erasure ran
  while a ``final_model/`` exists for any run that consumed this
  corpus.  The row is gone from disk but may still be memorised in
  the trained weights.
- ``data.erasure_warning_synthetic_data_present`` — corpus row erasure
  ran with synthetic-data snapshots present; the row may have produced
  derivative snippets the row→snippet mapping no longer connects.
- ``data.erasure_warning_external_copies`` — the loaded config has a
  non-empty ``webhook`` block; downstream consumers may have received
  notices that referenced the now-erased data.

Exit-code contract (per ``docs/standards/error-handling.md``):

- 0 — success or ``--check-policy`` report (gate-not-report semantic
  per design §10 Q5).
- 1 — config error (unknown ``row-id``, missing corpus, mutually
  exclusive flag combination, conflicting retention values).
- 2 — runtime error (I/O, permission denied, atomic rename failure).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, NoReturn, Optional, Tuple

from .._exit_codes import EXIT_CONFIG_ERROR, EXIT_SUCCESS, EXIT_TRAINING_ERROR
from .._logging import logger

# Audit event vocabulary (design §5.1).  Centralised so a future rename
# cannot drift across the dispatcher and the test fixtures.
_EVT_ERASURE_REQUESTED = "data.erasure_requested"
_EVT_ERASURE_COMPLETED = "data.erasure_completed"
_EVT_ERASURE_FAILED = "data.erasure_failed"
_EVT_WARN_MEMORISATION = "data.erasure_warning_memorisation"
_EVT_WARN_SYNTHETIC_DATA = "data.erasure_warning_synthetic_data_present"
_EVT_WARN_EXTERNAL_COPIES = "data.erasure_warning_external_copies"

# Persistent per-output-dir salt file.  Mode 0600.  Design §5.4
# F-R5-05: persistent regardless of FORGELM_AUDIT_SECRET presence so
# subsequent invocations without the env var still hash deterministically.
_SALT_FILENAME = ".forgelm_audit_salt"
_SALT_BYTES = 16
_SALT_FILE_MODE = 0o600

# Corpus row id keys we accept on erasure.  Operators with id-less corpora
# must pre-populate ids via ``forgelm audit --add-row-ids`` (Phase 28
# follow-up; line-number fallback is rejected per design §4.2 to defend
# against silent wrong-row deletion on a re-ordered file).
_ROW_ID_KEYS: Tuple[str, ...] = ("id", "row_id")

# Allowed --kind values per design §4.1.  ``logs`` is intentionally
# absent (audit logs are append-only Article 17(3)(b) and never deleted
# automatically — the trainer + the tool record the request, the
# operator handles the residual disposal manually).
_VALID_RUN_KINDS: Tuple[str, ...] = ("staging", "artefacts")


def _output_error_and_exit(output_format: str, msg: str, exit_code: int) -> NoReturn:
    """Emit *msg* as a structured JSON error or a log record, then exit.

    Mirrors the helpers in :mod:`._approve` and :mod:`._approvals` so
    the JSON envelope contract is identical across the compliance
    family of subcommands.  ``-> NoReturn`` so the type checker knows
    control never returns.
    """
    if output_format == "json":
        print(json.dumps({"success": False, "error": msg}))
    else:
        logger.error(msg)
    sys.exit(exit_code)


# ---------------------------------------------------------------------------
# Salt resolution + target_id hashing (design §5.4)
# ---------------------------------------------------------------------------


def _resolve_salt(output_dir: str) -> Tuple[bytes, str]:
    """Return ``(salt_bytes, salt_source)`` for ``target_id`` hashing.

    Salt resolution per design §5.4:

    - The persistent per-output-dir salt at
      ``<output_dir>/.forgelm_audit_salt`` is **always** consulted
      (created on first call with mode 0600).
    - When ``FORGELM_AUDIT_SECRET`` is set, its first 16 bytes are
      XOR'd with the persistent salt to derive the actual hashing
      salt; ``salt_source`` is recorded as ``"env_var"`` so a salt-
      source toggle between invocations is detectable in the chain
      via the ``salt_source`` audit-event field.
    - When the env var is absent, the persistent salt is used
      verbatim; ``salt_source = "per_dir"``.

    Raises :class:`OSError` when the salt file cannot be created or
    read; the caller surfaces the I/O error as ``EXIT_TRAINING_ERROR``.
    """
    salt_path = os.path.join(output_dir, _SALT_FILENAME)
    if not os.path.isfile(salt_path):
        os.makedirs(output_dir, exist_ok=True)
        # Atomic create-only write so two concurrent purges cannot both
        # generate a different salt and race each other.  ``O_EXCL``
        # guarantees the open fails if the file appeared since the
        # ``isfile`` check.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            fd = os.open(salt_path, flags, _SALT_FILE_MODE)
        except FileExistsError:
            # Another process created it between the check and our
            # open — fall through to read.
            pass
        else:
            try:
                os.write(fd, secrets.token_bytes(_SALT_BYTES))
            finally:
                os.close(fd)
    with open(salt_path, "rb") as fh:
        persistent = fh.read(_SALT_BYTES)
    if len(persistent) < _SALT_BYTES:
        # Truncated / corrupted salt file — refuse rather than silently
        # produce a weak hash.
        raise OSError(
            f"Salt file {salt_path!r} is shorter than {_SALT_BYTES} bytes "
            "(corrupted or truncated).  Delete the file to regenerate."
        )
    env_secret = os.environ.get("FORGELM_AUDIT_SECRET", "").encode("utf-8")
    if env_secret:
        env_prefix = env_secret[:_SALT_BYTES].ljust(_SALT_BYTES, b"\x00")
        # XOR the env-var prefix with the persistent salt.  Either
        # source alone is insufficient; both together produce the
        # actual hashing salt.
        salt = bytes(a ^ b for a, b in zip(persistent, env_prefix))
        return salt, "env_var"
    return persistent, "per_dir"


def _hash_target_id(raw_value: str, salt: bytes) -> str:
    """Hex SHA-256 of ``salt + raw_value``.  Stable, side-effect free."""
    return hashlib.sha256(salt + raw_value.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Corpus row erasure (--row-id / --corpus)
# ---------------------------------------------------------------------------


def _validate_row_id_args(args, output_format: str) -> None:
    """Refuse --row-id invocations that would silently delete the wrong row.

    Design §4.2 rejects three patterns at the CLI:

    - line-number values (``--row-id 42`` where 42 looks numeric and
      no JSONL ``id`` field exists is the legacy line-number form;
      we refuse to disambiguate);
    - directory-mode corpus paths (multi-file purges loop in operator
      script, not in this tool);
    - bare invocation without ``--corpus``.
    """
    if not args.corpus:
        _output_error_and_exit(
            output_format,
            "`--row-id` requires `--corpus <path>`. Bare row-id invocations are "
            "rejected per Article 17 (per-row decision + per-row audit event).",
            EXIT_CONFIG_ERROR,
        )
    if not os.path.isfile(args.corpus):
        _output_error_and_exit(
            output_format,
            f"Corpus file not found: {args.corpus!r}.  Multi-file purges are an "
            "operator script (loop over files), not a `forgelm purge` mode — see "
            "design §4.1 rationale.",
            EXIT_CONFIG_ERROR,
        )


def _find_matching_rows(corpus_path: str, row_id: str) -> List[Tuple[int, Dict[str, Any]]]:
    """Locate rows whose ``id`` (or ``row_id``) field equals ``row_id``.

    Returns ``[(line_number, row_dict)]`` in append order.  Skips
    malformed (non-JSON, non-dict-root) lines silently — they are
    auditor's problem, not ours, and they cannot match by definition.
    """
    matches: List[Tuple[int, Dict[str, Any]]] = []
    with open(corpus_path, "r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            for key in _ROW_ID_KEYS:
                if str(row.get(key, "")) == row_id:
                    matches.append((line_no, row))
                    break
    return matches


def _atomic_rewrite_dropping_lines(corpus_path: str, line_numbers_to_drop: List[int]) -> int:
    """Rewrite ``corpus_path`` excluding the given 1-based line numbers.

    Uses a temp file in the same directory + ``os.replace`` for atomic
    swap — operators get either the full pre-erasure file or the full
    post-erasure file, never a partial state.  Returns the byte count
    freed.

    Raises :class:`OSError` on any I/O failure; the caller is responsible
    for emitting ``data.erasure_failed`` and surfacing
    ``EXIT_TRAINING_ERROR``.
    """
    drop_set = set(line_numbers_to_drop)
    pre_size = os.path.getsize(corpus_path)
    parent = os.path.dirname(os.path.abspath(corpus_path)) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".forgelm_purge_", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            with open(corpus_path, "r", encoding="utf-8") as src:
                for line_no, line in enumerate(src, start=1):
                    if line_no in drop_set:
                        continue
                    out.write(line)
        os.replace(tmp_path, corpus_path)
    except OSError:
        # Best-effort cleanup of the temp file if the swap failed.
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:  # pragma: no cover — defensive
                logger.debug("Could not clean up purge temp file %s", tmp_path)
        raise
    post_size = os.path.getsize(corpus_path)
    return pre_size - post_size


def _detect_warning_conditions(
    output_dir: str,
    config_loaded: Optional[Any],
) -> Tuple[List[str], Dict[str, Any]]:
    """Return ``(warning_event_names, extra_fields_per_event)`` for the
    warning events that should fire alongside ``data.erasure_completed``.

    Per design §5.1:

    - ``data.erasure_warning_memorisation`` when any ``final_model/``
      exists in the operator's output dir tree (a trained model may
      have memorised the row).
    - ``data.erasure_warning_synthetic_data_present`` when any
      ``synthetic_data*.jsonl`` exists (the row may have produced
      derivative snippets).
    - ``data.erasure_warning_external_copies`` when the loaded config
      has a non-empty ``webhook`` block (downstream consumers may
      have received notices).
    """
    warnings: List[str] = []
    extras: Dict[str, Any] = {}

    final_model_dir = os.path.join(output_dir, "final_model")
    if os.path.isdir(final_model_dir):
        warnings.append(_EVT_WARN_MEMORISATION)
        extras["affected_run_ids"] = _scan_run_ids_with_final_model(output_dir)

    synthetic_files = sorted(str(p) for p in Path(output_dir).glob("synthetic_data*.jsonl") if p.is_file())
    if synthetic_files:
        warnings.append(_EVT_WARN_SYNTHETIC_DATA)
        extras["synthetic_files"] = synthetic_files

    webhook_targets = _extract_webhook_targets(config_loaded)
    if webhook_targets:
        warnings.append(_EVT_WARN_EXTERNAL_COPIES)
        extras["webhook_targets"] = webhook_targets

    return warnings, extras


def _scan_run_ids_with_final_model(output_dir: str) -> List[str]:
    """Best-effort: enumerate run ids whose ``final_model/`` is present.

    Looks for ``final_model.staging.<run_id>/`` left as forensic
    artefacts after promotion (or any directory matching the staging
    suffix pattern).  Empty list when nothing matches; the caller
    treats it as "we know one run consumed the corpus, identity
    unknown".
    """
    pattern = re.compile(r"final_model\.staging\.([A-Za-z0-9._-]+)$")
    run_ids: List[str] = []
    try:
        for entry in os.listdir(output_dir):
            match = pattern.match(entry)
            if match:
                run_ids.append(match.group(1))
    except OSError:
        return []
    return sorted(set(run_ids))


def _extract_webhook_targets(config_loaded: Optional[Any]) -> List[str]:
    """Return redacted webhook URLs from the loaded config, or ``[]``.

    Pulls ``config.webhook.url_*`` if present; we redact the path /
    query (which carries credentials) using the same ``_mask_netloc``
    helper that the HTTP discipline uses for log emission.
    """
    if config_loaded is None or getattr(config_loaded, "webhook", None) is None:
        return []
    webhook = config_loaded.webhook
    targets: List[str] = []
    for attr in ("url_success", "url_failure", "url_safety_alert", "url_compliance_alert"):
        url = getattr(webhook, attr, None)
        if url:
            try:
                from forgelm._http import _mask_netloc

                targets.append(_mask_netloc(url))
            except Exception:  # noqa: BLE001 — best-effort redaction
                targets.append("<webhook-url-redacted>")
    return sorted(set(targets))


def _run_purge_row_id(args, output_format: str) -> None:
    """Handle ``forgelm purge --row-id <id> --corpus <path>``."""
    _validate_row_id_args(args, output_format)
    output_dir = args.output_dir or os.path.dirname(os.path.abspath(args.corpus)) or "."
    os.makedirs(output_dir, exist_ok=True)

    try:
        salt, salt_source = _resolve_salt(output_dir)
    except OSError as exc:
        _output_error_and_exit(
            output_format,
            f"Could not resolve audit salt for {output_dir!r}: {exc}",
            EXIT_TRAINING_ERROR,
        )

    target_id_hash = _hash_target_id(args.row_id, salt)
    justification = args.justification or "(operator did not supply --justification)"

    # Late import so a fresh checkout without `forgelm[ingestion]` etc.
    # can still run `forgelm doctor` without hitting AuditLogger's
    # operator-identity validation.
    from forgelm.compliance import AuditLogger
    from forgelm.config import ConfigError

    try:
        audit = AuditLogger(output_dir)
    except ConfigError as exc:
        _output_error_and_exit(output_format, str(exc), EXIT_CONFIG_ERROR)

    config_loaded = _maybe_load_config(getattr(args, "config", None))

    request_fields: Dict[str, Any] = {
        "target_kind": "row",
        "target_id": target_id_hash,
        "salt_source": salt_source,
        "corpus_path": os.path.abspath(args.corpus),
        "justification": justification,
        "dry_run": bool(args.dry_run),
    }
    audit.log_event(_EVT_ERASURE_REQUESTED, **request_fields)

    matches = _find_matching_rows(args.corpus, args.row_id)
    row_matches_mode = getattr(args, "row_matches", "one")
    if not matches:
        # Audit a failed event so the chain shows request → fail.
        audit.log_event(
            _EVT_ERASURE_FAILED,
            **request_fields,
            error_class="NoMatchingRow",
            error_message=f"No row with id matching {args.row_id!r} found in corpus.",
        )
        _output_error_and_exit(
            output_format,
            f"No row with id={args.row_id!r} in {args.corpus!r}.  Refusing to delete.",
            EXIT_CONFIG_ERROR,
        )
    if len(matches) > 1 and row_matches_mode == "one":
        audit.log_event(
            _EVT_ERASURE_FAILED,
            **request_fields,
            error_class="MultiMatchRefused",
            error_message=f"{len(matches)} rows matched id={args.row_id!r}; --row-matches=one refuses ambiguity.",
            match_count=len(matches),
        )
        _output_error_and_exit(
            output_format,
            f"{len(matches)} rows matched id={args.row_id!r} in {args.corpus!r}; "
            "--row-matches defaults to 'one' (refuse on ambiguity).  Pass --row-matches=all to "
            "delete every match (operator confirms intent), or supply a unique id.",
            EXIT_CONFIG_ERROR,
        )

    line_numbers = [ln for ln, _row in matches]
    pre_first_line = line_numbers[0]

    if args.dry_run:
        # Dry-run: do not touch the corpus; emit a completed event with
        # ``dry_run=True`` so the chain reflects the intent.
        audit.log_event(
            _EVT_ERASURE_COMPLETED,
            **request_fields,
            bytes_freed=0,
            files_modified=[],
            pre_erasure_line_number=pre_first_line,
            match_count=len(matches),
        )
        _emit_purge_success(
            output_format,
            {
                "mode": "row",
                "dry_run": True,
                "row_id_hash": target_id_hash,
                "salt_source": salt_source,
                "matches": len(matches),
                "first_line": pre_first_line,
                "warnings": [],
            },
        )
        return

    try:
        bytes_freed = _atomic_rewrite_dropping_lines(args.corpus, line_numbers)
    except OSError as exc:
        audit.log_event(
            _EVT_ERASURE_FAILED,
            **request_fields,
            error_class=exc.__class__.__name__,
            error_message=str(exc),
        )
        _output_error_and_exit(
            output_format,
            f"Atomic rewrite of {args.corpus!r} failed: {exc}.  Corpus left unchanged.",
            EXIT_TRAINING_ERROR,
        )

    warning_events, warning_extras = _detect_warning_conditions(output_dir, config_loaded)
    audit.log_event(
        _EVT_ERASURE_COMPLETED,
        **request_fields,
        bytes_freed=bytes_freed,
        files_modified=[os.path.abspath(args.corpus)],
        pre_erasure_line_number=pre_first_line,
        match_count=len(matches),
    )
    for event_name in warning_events:
        audit.log_event(event_name, **request_fields, **warning_extras)

    _emit_purge_success(
        output_format,
        {
            "mode": "row",
            "dry_run": False,
            "row_id_hash": target_id_hash,
            "salt_source": salt_source,
            "matches": len(matches),
            "first_line": pre_first_line,
            "bytes_freed": bytes_freed,
            "warnings": warning_events,
        },
    )


# ---------------------------------------------------------------------------
# Run-scoped erasure (--run-id / --kind)
# ---------------------------------------------------------------------------


def _run_purge_run_id(args, output_format: str) -> None:
    """Handle ``forgelm purge --run-id <id> --kind {staging,artefacts}``."""
    if args.kind not in _VALID_RUN_KINDS:
        _output_error_and_exit(
            output_format,
            f"--kind must be one of {sorted(_VALID_RUN_KINDS)!r}; got {args.kind!r}.",
            EXIT_CONFIG_ERROR,
        )
    output_dir = args.output_dir or "."
    if not os.path.isdir(output_dir):
        _output_error_and_exit(
            output_format,
            f"--output-dir not found: {output_dir!r}.",
            EXIT_CONFIG_ERROR,
        )

    from forgelm.compliance import AuditLogger
    from forgelm.config import ConfigError

    try:
        audit = AuditLogger(output_dir, run_id=args.run_id)
    except ConfigError as exc:
        _output_error_and_exit(output_format, str(exc), EXIT_CONFIG_ERROR)

    request_fields: Dict[str, Any] = {
        "target_kind": args.kind,
        "target_id": args.run_id,
        "output_dir": os.path.abspath(output_dir),
        "justification": args.justification or "(operator did not supply --justification)",
        "dry_run": bool(args.dry_run),
    }
    audit.log_event(_EVT_ERASURE_REQUESTED, **request_fields)

    target_paths = _resolve_run_kind_targets(output_dir, args.run_id, args.kind)
    if not target_paths:
        audit.log_event(
            _EVT_ERASURE_FAILED,
            **request_fields,
            error_class="NoMatchingArtefacts",
            error_message=f"No {args.kind!r} artefacts found for run_id={args.run_id!r}.",
        )
        _output_error_and_exit(
            output_format,
            f"No {args.kind!r} artefacts found for run_id={args.run_id!r} under {output_dir!r}.",
            EXIT_CONFIG_ERROR,
        )

    if args.dry_run:
        audit.log_event(
            _EVT_ERASURE_COMPLETED,
            **request_fields,
            bytes_freed=0,
            files_modified=[],
        )
        _emit_purge_success(
            output_format,
            {
                "mode": "run",
                "kind": args.kind,
                "dry_run": True,
                "run_id": args.run_id,
                "would_delete": [str(p) for p in target_paths],
            },
        )
        return

    bytes_freed = 0
    files_modified: List[str] = []
    try:
        for path in target_paths:
            bytes_freed += _delete_path(path)
            files_modified.append(str(path))
    except OSError as exc:
        audit.log_event(
            _EVT_ERASURE_FAILED,
            **request_fields,
            error_class=exc.__class__.__name__,
            error_message=str(exc),
            files_modified=files_modified,
        )
        _output_error_and_exit(
            output_format,
            f"Deletion failed mid-batch: {exc}.  {len(files_modified)} of "
            f"{len(target_paths)} target(s) removed before failure.",
            EXIT_TRAINING_ERROR,
        )

    audit.log_event(
        _EVT_ERASURE_COMPLETED,
        **request_fields,
        bytes_freed=bytes_freed,
        files_modified=files_modified,
    )
    _emit_purge_success(
        output_format,
        {
            "mode": "run",
            "kind": args.kind,
            "dry_run": False,
            "run_id": args.run_id,
            "deleted": files_modified,
            "bytes_freed": bytes_freed,
        },
    )


def _resolve_run_kind_targets(output_dir: str, run_id: str, kind: str) -> List[Path]:
    """Return the on-disk paths the ``--kind`` flag refers to for ``run_id``."""
    paths: List[Path] = []
    base = Path(output_dir)
    if kind == "staging":
        # Match both ``final_model.staging.<run_id>/`` (Phase 9 v2 layout)
        # and ``final_model.staging/`` for legacy runs.
        explicit = base / f"final_model.staging.{run_id}"
        canonical = base / "final_model.staging"
        for candidate in (explicit, canonical):
            if candidate.exists():
                paths.append(candidate)
    elif kind == "artefacts":
        compliance_dir = base / "compliance"
        if compliance_dir.is_dir():
            # Compliance bundle filenames embed the run_id; we match them
            # generously to cover both ``compliance_<run_id>.json`` and
            # raw ``annex_iv_<run_id>.json``.
            for fname in os.listdir(compliance_dir):
                fpath = compliance_dir / fname
                if fpath.is_file() and run_id in fname:
                    paths.append(fpath)
    return paths


def _delete_path(path: Path) -> int:
    """Remove a file or directory; return bytes freed."""
    if path.is_dir() and not path.is_symlink():
        size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        shutil.rmtree(path)
        return size
    size = path.stat().st_size
    path.unlink()
    return size


# ---------------------------------------------------------------------------
# Retention policy report (--check-policy)
# ---------------------------------------------------------------------------


def _run_purge_check_policy(args, output_format: str) -> None:
    """Handle ``forgelm purge --check-policy [--config <path>]``.

    Always exits 0 (per design §10 Q5: report-not-gate semantic).
    Operators wiring a CI gate use ``--output-format json`` and pipe
    to ``jq '.violations | length'`` themselves.
    """
    config_loaded = _maybe_load_config(getattr(args, "config", None))
    if config_loaded is None or getattr(config_loaded, "retention", None) is None:
        msg = (
            "No `retention:` block in the loaded config; nothing to enforce.  "
            "See `docs/guides/gdpr_erasure.md` for the schema."
        )
        if output_format == "json":
            print(json.dumps({"success": True, "violations": [], "note": msg}))
        else:
            print(msg)
        sys.exit(EXIT_SUCCESS)

    output_dir = args.output_dir or "."
    violations = _scan_retention_violations(config_loaded.retention, output_dir)
    if output_format == "json":
        print(json.dumps({"success": True, "violations": violations, "count": len(violations)}, indent=2))
    else:
        if not violations:
            print(f"No retention-policy violations under {output_dir!r}.")
        else:
            print(f"Retention-policy violations under {output_dir!r} ({len(violations)}):")
            for v in violations:
                age_days = v.get("age_days", "?")
                horizon = v.get("horizon_days", "?")
                print(
                    f"  {v.get('artefact_kind', '?')}: {v.get('path', '?')} "
                    f"(age {age_days}d, horizon {horizon}d, age_source={v.get('age_source', '?')})"
                )
    sys.exit(EXIT_SUCCESS)


def _scan_retention_violations(retention, output_dir: str) -> List[Dict[str, Any]]:
    """Walk ``output_dir`` and report artefacts past their retention horizon.

    Belt-and-suspenders age resolution (design §3.3):

    1. **Belt** (preferred):  for run-scoped artefacts, the canonical
       age is the ``timestamp`` of the run's ``audit_log.jsonl`` genesis
       event (HMAC-signed when the operator opted in).
    2. **Suspenders**:  fall back to filesystem ``mtime`` and tag the
       violation with ``age_source="mtime"`` so an operator scanning
       the report knows the age signal is filesystem-derived.
    """
    violations: List[Dict[str, Any]] = []
    now = time.time()

    audit_log_path = os.path.join(output_dir, "audit_log.jsonl")
    audit_age_seconds = _age_from_audit_log(audit_log_path, now)

    horizons = (
        ("audit_log", audit_log_path, retention.audit_log_retention_days),
        ("staging_dir", os.path.join(output_dir, "final_model.staging"), retention.staging_ttl_days),
        ("compliance_bundle", os.path.join(output_dir, "compliance"), retention.ephemeral_artefact_retention_days),
        (
            "data_audit_report",
            os.path.join(output_dir, "data_audit_report.json"),
            retention.ephemeral_artefact_retention_days,
        ),
    )
    for kind, path, horizon_days in horizons:
        if horizon_days == 0 or not os.path.exists(path):
            continue
        age_seconds, age_source = _resolve_artefact_age(path, audit_age_seconds, now)
        age_days = age_seconds / 86400.0
        if age_days > horizon_days:
            violations.append(
                {
                    "artefact_kind": kind,
                    "path": path,
                    "age_days": round(age_days, 1),
                    "horizon_days": horizon_days,
                    "age_source": age_source,
                }
            )
    return violations


def _age_from_audit_log(audit_log_path: str, now: float) -> Optional[float]:
    """Extract the genesis-event timestamp from the audit log; return age."""
    if not os.path.isfile(audit_log_path):
        return None
    try:
        with open(audit_log_path, "r", encoding="utf-8") as fh:
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
                ts = event.get("timestamp")
                if isinstance(ts, str):
                    from datetime import datetime, timezone

                    try:
                        when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=timezone.utc)
                    return now - when.timestamp()
                return None
    except OSError:
        return None
    return None


def _resolve_artefact_age(
    path: str,
    audit_age_seconds: Optional[float],
    now: float,
) -> Tuple[float, str]:
    """Belt + suspenders age resolution; return ``(age_seconds, source)``."""
    if audit_age_seconds is not None:
        return audit_age_seconds, "audit"
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return 0.0, "mtime"
    return now - mtime, "mtime"


# ---------------------------------------------------------------------------
# Helpers + dispatcher entry
# ---------------------------------------------------------------------------


def _maybe_load_config(config_path: Optional[str]):
    """Best-effort load the ``ForgeConfig`` from YAML.

    Returns the loaded config or ``None`` when the path is absent /
    unreadable / invalid — purge subcommands are still expected to run
    when the operator did not pass ``--config`` (especially the row-id
    erasure path, which is config-agnostic).
    """
    if not config_path:
        return None
    try:
        from forgelm.config import load_config

        return load_config(config_path)
    except Exception as exc:  # noqa: BLE001 — best-effort: config is optional
        logger.debug("purge: could not load config %s: %s", config_path, exc)
        return None


def _emit_purge_success(output_format: str, payload: Dict[str, Any]) -> None:
    """Emit the success envelope for a purge subcommand."""
    if output_format == "json":
        print(json.dumps({"success": True, **payload}, indent=2))
    else:
        mode = payload.get("mode", "?")
        if mode == "row":
            if payload.get("dry_run"):
                print(
                    f"[dry-run] Would erase {payload.get('matches')} row(s) starting at line "
                    f"{payload.get('first_line')} (target_id_hash={payload.get('row_id_hash')[:16]}…, "
                    f"salt_source={payload.get('salt_source')})."
                )
            else:
                warns = payload.get("warnings") or []
                warn_str = f"; warnings: {', '.join(warns)}" if warns else ""
                print(f"Erased {payload.get('matches')} row(s); {payload.get('bytes_freed')} bytes freed{warn_str}.")
        elif mode == "run":
            if payload.get("dry_run"):
                paths = payload.get("would_delete") or []
                print(
                    f"[dry-run] Would delete {len(paths)} {payload.get('kind')} artefact(s) for run {payload.get('run_id')!r}:"
                )
                for p in paths:
                    print(f"  - {p}")
            else:
                deleted = payload.get("deleted") or []
                print(
                    f"Deleted {len(deleted)} {payload.get('kind')} artefact(s) for run "
                    f"{payload.get('run_id')!r}; {payload.get('bytes_freed')} bytes freed."
                )


def _run_purge_cmd(args, output_format: str) -> None:
    """Top-level dispatcher for ``forgelm purge``.

    Mode resolution:

    - ``--check-policy`` is a standalone flag; no other purge mode
      may be combined with it (argparse enforces, defensive check
      below).
    - ``--row-id`` requires ``--corpus``.
    - ``--run-id`` requires ``--kind``.
    """
    if getattr(args, "check_policy", False):
        if args.row_id or args.run_id:
            _output_error_and_exit(
                output_format,
                "--check-policy is mutually exclusive with --row-id / --run-id.",
                EXIT_CONFIG_ERROR,
            )
        _run_purge_check_policy(args, output_format)
        return
    if args.row_id and args.run_id:
        _output_error_and_exit(
            output_format,
            "--row-id and --run-id are mutually exclusive (different erasure scopes).",
            EXIT_CONFIG_ERROR,
        )
    if args.row_id:
        _run_purge_row_id(args, output_format)
        sys.exit(EXIT_SUCCESS)
    if args.run_id:
        _run_purge_run_id(args, output_format)
        sys.exit(EXIT_SUCCESS)
    _output_error_and_exit(
        output_format,
        "forgelm purge: one of --row-id <id> --corpus <path> / --run-id <id> --kind {staging,artefacts} / --check-policy is required.",
        EXIT_CONFIG_ERROR,
    )


__all__ = [
    "_run_purge_cmd",
    "_run_purge_row_id",
    "_run_purge_run_id",
    "_run_purge_check_policy",
    "_resolve_salt",
    "_hash_target_id",
    "_find_matching_rows",
    "_atomic_rewrite_dropping_lines",
    "_detect_warning_conditions",
    "_scan_retention_violations",
]

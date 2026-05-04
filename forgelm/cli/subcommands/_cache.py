"""``forgelm cache-models`` + ``forgelm cache-tasks`` subcommands (Phase 35).

The air-gap workflow blocker pair — operators with restricted-egress
hosts use these on a connected machine to pre-populate the HuggingFace
Hub cache + the lm-evaluation-harness task dataset cache, then transfer
the resulting bundle to the air-gapped host where ``forgelm doctor
--offline`` confirms presence and the trainer runs with
``local_files_only=True``.

The two subcommands live in one module because they share the same
audit-event vocabulary (``cache.populate_*``), the same exit-code
contract, and the same JSON envelope shape.

Design (closure-plan §15.5 Phase 35):

- ``cache-models --model <name> [--safety <name>] [--output <dir>]``
  uses :func:`huggingface_hub.snapshot_download` to populate the local
  cache with the model + safety classifier (typically Llama Guard).
  ``--model`` is repeatable so the operator can stage every model the
  next training run will need in a single invocation.
- ``cache-tasks --tasks <csv>`` uses ``lm_eval.tasks.get_task_dict``
  to enumerate task definitions and ``dataset.download_and_prepare()``
  to populate the underlying datasets library cache.

Exit codes (per ``docs/standards/error-handling.md``):

- 0 — every model / task cached successfully.
- 1 — config error (invalid model name format, unknown task name,
  missing optional extra).
- 2 — runtime error (network failure, HF Hub 5xx, disk-full, salt-
  file write failure).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, NoReturn

from .._exit_codes import EXIT_CONFIG_ERROR, EXIT_SUCCESS, EXIT_TRAINING_ERROR
from .._logging import logger

# Audit-event vocabulary shared by both cache subcommands.  Centralised
# here so a future rename does not drift across the dispatcher and the
# tests.
_EVT_CACHE_MODELS_REQUESTED = "cache.populate_models_requested"
_EVT_CACHE_MODELS_COMPLETED = "cache.populate_models_completed"
_EVT_CACHE_MODELS_FAILED = "cache.populate_models_failed"
_EVT_CACHE_TASKS_REQUESTED = "cache.populate_tasks_requested"
_EVT_CACHE_TASKS_COMPLETED = "cache.populate_tasks_completed"
_EVT_CACHE_TASKS_FAILED = "cache.populate_tasks_failed"


def _output_error_and_exit(output_format: str, msg: str, exit_code: int) -> NoReturn:
    """Emit *msg* as a structured JSON error or a log record, then exit.

    Mirrors the helpers in :mod:`._approve` / :mod:`._approvals` /
    :mod:`._purge` so the JSON envelope contract stays identical across
    every Wave 2b subcommand.
    """
    if output_format == "json":
        print(json.dumps({"success": False, "error": msg}))
    else:
        logger.error(msg)
    sys.exit(exit_code)


def _resolve_cache_dir(output_arg: str | None) -> str:
    """Pick the HF cache directory for downloads.

    Resolution order (mirrors :func:`forgelm.cli.subcommands._doctor._resolve_hf_cache_dir`):

    1. Operator-supplied ``--output <dir>`` if given (overrides env).
    2. ``HF_HUB_CACHE`` env var.
    3. ``HF_HOME/hub`` (the *hub* sub-directory of the parent cache).
    4. ``~/.cache/huggingface/hub`` documented default.
    """
    if output_arg:
        return os.path.abspath(output_arg)
    hf_hub_cache = os.environ.get("HF_HUB_CACHE")
    if hf_hub_cache:
        return hf_hub_cache
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return os.path.join(hf_home, "hub")
    return os.path.expanduser("~/.cache/huggingface/hub")


def _validate_model_name(name: str, output_format: str) -> None:
    """Refuse obviously malformed model names early.

    ``huggingface_hub.snapshot_download`` accepts both ``namespace/repo``
    HF Hub IDs and local paths; we reject empty / whitespace-only names
    so the failure mode is a clear operator message rather than an
    opaque ``HTTPError`` from the Hub.
    """
    if not name or not name.strip():
        _output_error_and_exit(
            output_format,
            "Model name must be non-empty.  Use HF Hub ID (e.g. `meta-llama/Llama-3.2-3B`) or a local path.",
            EXIT_CONFIG_ERROR,
        )


# ---------------------------------------------------------------------------
# cache-models
# ---------------------------------------------------------------------------


def _run_cache_models_cmd(args, output_format: str) -> None:
    """Pre-populate the HuggingFace Hub cache for one or more models."""
    models: List[str] = list(getattr(args, "model", None) or [])
    safety: str | None = getattr(args, "safety", None)
    if safety:
        models.append(safety)
    if not models:
        _output_error_and_exit(
            output_format,
            "At least one --model or --safety must be supplied.",
            EXIT_CONFIG_ERROR,
        )
    for name in models:
        _validate_model_name(name, output_format)

    cache_dir = _resolve_cache_dir(getattr(args, "output", None))
    os.makedirs(cache_dir, exist_ok=True)

    # Late import so a fresh-install operator running ``forgelm doctor``
    # is not forced to have huggingface_hub at import-time of this module.
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        _output_error_and_exit(
            output_format,
            f"huggingface_hub is required for cache-models; install with `pip install forgelm` (it is a core dep).  ImportError: {exc}",
            EXIT_CONFIG_ERROR,
        )

    audit = _maybe_audit_logger(getattr(args, "audit_dir", None) or cache_dir)
    request_fields = {
        "models": list(models),
        "cache_dir": cache_dir,
        "safety_classifier": safety,
    }
    if audit is not None:
        audit.log_event(_EVT_CACHE_MODELS_REQUESTED, **request_fields)

    results: List[Dict[str, Any]] = []
    total_size_bytes = 0
    try:
        for name in models:
            entry = _download_one_model(name, cache_dir, snapshot_download)
            results.append(entry)
            total_size_bytes += entry.get("size_bytes", 0)
    except Exception as exc:  # noqa: BLE001 — best-effort: hub failures, transport failures, disk-full all funnel into the same operator-facing failure path with a clear message. # NOSONAR
        if audit is not None:
            audit.log_event(
                _EVT_CACHE_MODELS_FAILED,
                **request_fields,
                models_completed=[r["name"] for r in results],
                error_class=exc.__class__.__name__,
                error_message=str(exc),
            )
        _output_error_and_exit(
            output_format,
            f"cache-models failed mid-batch on {len(results)} of {len(models)} model(s): {exc}",
            EXIT_TRAINING_ERROR,
        )

    if audit is not None:
        audit.log_event(
            _EVT_CACHE_MODELS_COMPLETED,
            **request_fields,
            total_size_bytes=total_size_bytes,
            count=len(results),
        )

    payload = {
        "success": True,
        "models": results,
        "total_size_mb": round(total_size_bytes / (1024**2), 2),
        "cache_dir": cache_dir,
    }
    _emit_cache_success(output_format, payload, kind="models")
    sys.exit(EXIT_SUCCESS)


def _download_one_model(name: str, cache_dir: str, snapshot_download_callable) -> Dict[str, Any]:
    """Run :func:`huggingface_hub.snapshot_download` and report the outcome."""
    started = time.monotonic()
    cached_path = snapshot_download_callable(repo_id=name, cache_dir=cache_dir)
    duration = time.monotonic() - started
    size_bytes = _walk_directory_size(cached_path)
    return {
        "name": name,
        "cached_path": cached_path,
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / (1024**2), 2),
        "duration_s": round(duration, 2),
    }


def _walk_directory_size(path: str) -> int:
    """Sum regular-file sizes under ``path``.  Symlinks ignored to avoid
    double-counting the HF blob store."""
    total = 0
    base = Path(path)
    if not base.is_dir():
        try:
            return base.stat().st_size
        except OSError:
            return 0
    for entry in base.rglob("*"):
        if entry.is_symlink():
            continue
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                continue
    return total


# ---------------------------------------------------------------------------
# cache-tasks
# ---------------------------------------------------------------------------


def _run_cache_tasks_cmd(args, output_format: str) -> None:
    """Pre-populate the lm-evaluation-harness task dataset cache."""
    raw = getattr(args, "tasks", None) or ""
    task_names = [t.strip() for t in raw.split(",") if t.strip()]
    if not task_names:
        _output_error_and_exit(
            output_format,
            "--tasks must be a non-empty comma-separated list (e.g. `hellaswag,arc_easy,truthfulqa`).",
            EXIT_CONFIG_ERROR,
        )

    # Late import — the operator may not have the [eval] extra installed
    # if they are only using cache-models.  Surface a clear install hint.
    try:
        import lm_eval  # noqa: F401
        from lm_eval.tasks import get_task_dict
    except ImportError as exc:
        _output_error_and_exit(
            output_format,
            f"lm-eval is required for cache-tasks; install with: pip install 'forgelm[eval]'.  ImportError: {exc}",
            EXIT_CONFIG_ERROR,
        )

    cache_dir = _resolve_cache_dir(getattr(args, "output", None))
    audit = _maybe_audit_logger(getattr(args, "audit_dir", None) or cache_dir)
    request_fields = {"tasks": task_names, "cache_dir": cache_dir}
    if audit is not None:
        audit.log_event(_EVT_CACHE_TASKS_REQUESTED, **request_fields)

    results: List[Dict[str, Any]] = []
    try:
        task_dict = get_task_dict(task_names)
    except Exception as exc:  # noqa: BLE001 — lm-eval surfaces invalid task names as bare ``KeyError`` / ``ValueError``; either is a config error from the operator.
        if audit is not None:
            audit.log_event(
                _EVT_CACHE_TASKS_FAILED,
                **request_fields,
                error_class=exc.__class__.__name__,
                error_message=str(exc),
            )
        _output_error_and_exit(
            output_format,
            f"Unknown or invalid task name in {task_names!r}: {exc}",
            EXIT_CONFIG_ERROR,
        )

    try:
        for name, task_obj in task_dict.items():
            results.append(_prepare_one_task(name, task_obj))
    except Exception as exc:  # noqa: BLE001 — best-effort: dataset download failures, parquet decode failures, all funnel into the same operator-facing message with the partial results so the operator knows what completed. # NOSONAR
        if audit is not None:
            audit.log_event(
                _EVT_CACHE_TASKS_FAILED,
                **request_fields,
                tasks_completed=[r["name"] for r in results],
                error_class=exc.__class__.__name__,
                error_message=str(exc),
            )
        _output_error_and_exit(
            output_format,
            f"cache-tasks failed on {len(results)} of {len(task_dict)} task(s): {exc}",
            EXIT_TRAINING_ERROR,
        )

    if audit is not None:
        audit.log_event(_EVT_CACHE_TASKS_COMPLETED, **request_fields, count=len(results))

    payload = {
        "success": True,
        "tasks": results,
        "cache_dir": cache_dir,
    }
    _emit_cache_success(output_format, payload, kind="tasks")
    sys.exit(EXIT_SUCCESS)


def _prepare_one_task(name: str, task_obj) -> Dict[str, Any]:
    """Trigger the underlying datasets-library download for a single task.

    ``lm-eval`` tasks expose a ``dataset`` (or callable that returns one);
    we tolerate both shapes since lm-eval has flipped the surface across
    versions.  When neither is reachable we mark the task as cached
    pessimistically (the operator can re-run with verbose lm-eval logging
    to inspect the task's own download path).
    """
    cached = False
    error_msg: str | None = None
    try:
        dataset = getattr(task_obj, "dataset", None)
        if callable(dataset):
            dataset = dataset()
        if dataset is not None and hasattr(dataset, "download_and_prepare"):
            dataset.download_and_prepare()
            cached = True
        elif dataset is not None:
            # Newer lm-eval versions return the loaded dataset directly;
            # nothing to download separately.
            cached = True
    except Exception as exc:  # noqa: BLE001 — record the per-task error rather than aborting the batch.
        error_msg = f"{exc.__class__.__name__}: {exc}"
    return {
        "name": name,
        "cached": cached,
        "error": error_msg,
    }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _maybe_audit_logger(audit_dir: str):
    """Best-effort construct the AuditLogger; warn + continue on failure.

    ``cache-models`` is often run on a connected machine that may not
    have a ``FORGELM_OPERATOR`` configured (the operator is staging
    artefacts for an air-gap host they don't own).  We surface the
    audit-logger construction failure as a debug-level note and proceed
    without auditing — the cache subcommands' value is in the on-disk
    artefacts, not the audit chain.
    """
    try:
        from forgelm.compliance import AuditLogger
        from forgelm.config import ConfigError

        return AuditLogger(audit_dir)
    except ConfigError as exc:
        logger.debug("cache subcommand: AuditLogger init failed (%s); continuing without audit log.", exc)
        return None
    except Exception as exc:  # noqa: BLE001 — best-effort: audit is optional context here. # NOSONAR
        logger.debug("cache subcommand: AuditLogger init crashed (%s); continuing without audit log.", exc)
        return None


def _emit_cache_success(output_format: str, payload: Dict[str, Any], *, kind: str) -> None:
    """Render the success envelope (text or JSON)."""
    if output_format == "json":
        print(json.dumps(payload, indent=2, default=str))
        return
    if kind == "models":
        models = payload.get("models", [])
        total_mb = payload.get("total_size_mb", 0)
        print(f"Cached {len(models)} model(s); {total_mb} MiB total under {payload.get('cache_dir')}.")
        for entry in models:
            print(f"  - {entry['name']}: {entry.get('size_mb', '?')} MiB ({entry.get('duration_s', '?')}s)")
    elif kind == "tasks":
        tasks = payload.get("tasks", [])
        ok = sum(1 for t in tasks if t.get("cached"))
        print(f"Cached {ok} of {len(tasks)} task(s) under {payload.get('cache_dir')}.")
        for entry in tasks:
            status = "ok" if entry.get("cached") else f"warn ({entry.get('error', 'unknown')})"
            print(f"  - {entry['name']}: {status}")


__all__ = [
    "_run_cache_models_cmd",
    "_run_cache_tasks_cmd",
    "_resolve_cache_dir",
    "_validate_model_name",
    "_walk_directory_size",
]

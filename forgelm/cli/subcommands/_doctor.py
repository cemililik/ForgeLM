"""``forgelm doctor`` env-check subcommand (Phase 34).

The first command an operator should run after installation.  Probes the
environment ForgeLM expects (Python, torch, CUDA, GPU, optional extras,
HF Hub reachability, disk space, audit-log identity) and emits a
structured pass / warn / fail report — text by default, JSON envelope
when ``--output-format json`` is set.

Design goals (closure plan §9.5 Phase 34):

- **Self-contained.**  Probes use stdlib only at module load.  Heavy
  deps (torch, huggingface_hub) are imported lazily inside the
  individual check functions so ``forgelm doctor`` can run on a
  brand-new machine where torch is not yet installed without crashing.
- **Honest pass / warn / fail.**  ``warn`` is reserved for "operator
  may want to address this" (e.g. optional extra missing); ``fail``
  is reserved for "ForgeLM cannot work this way" (e.g. Python version
  too old).  Air-gap (``--offline``) skips the HF Hub network probe
  rather than reporting it as a failure.
- **Public exit-code contract.**  0 when every check passes, 1 when at
  least one fails (config-error class), 2 when a probe itself crashed
  (runtime-error class — operator-actionable bug, not config).
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .._exit_codes import EXIT_CONFIG_ERROR, EXIT_SUCCESS, EXIT_TRAINING_ERROR
from .._logging import logger

# Status vocabulary.  Centralised so a future rename (e.g. "warn" ->
# "warning") cannot drift across the renderers and the JSON contract.
_STATUS_PASS = "pass"
_STATUS_WARN = "warn"
_STATUS_FAIL = "fail"

# Optional extras advertised in pyproject.toml [project.optional-dependencies].
# Each entry is ``(extra_name, importable_module, human_purpose_blurb)``.
# ``importable_module`` is the package the extra installs that we probe via
# ``importlib.util.find_spec`` — a successful spec resolve means the extra is
# present.  Doctor never *imports* the module (avoids triggering torch /
# transformers / spacy heavy load on a healthy probe).
_OPTIONAL_EXTRAS: Tuple[Tuple[str, str, str], ...] = (
    ("qlora", "bitsandbytes", "4-bit / 8-bit QLoRA training"),
    ("unsloth", "unsloth", "Unsloth-accelerated training (Linux GPUs only)"),
    ("deepspeed", "deepspeed", "DeepSpeed ZeRO + offload distributed training"),
    ("evaluation", "lm_eval", "lm-evaluation-harness benchmark scoring"),
    ("wandb", "wandb", "Weights & Biases experiment tracking"),
    ("mergekit", "mergekit", "Model-merge backend for the merge mode"),
    ("ingestion", "pypdf", "PDF / DOCX / EPUB ingestion"),
    ("ingestion-pii-ml", "presidio_analyzer", "Presidio ML-NER PII detection in audit"),
    ("ingestion-scale", "datasketch", "MinHash LSH for >50K-row dedup"),
)

# Disk-space thresholds for the workspace check.  Tuned for "enough room
# to download a 7B-parameter model + run one fine-tune" — ~50 GB safe,
# 10-50 GB warn, <10 GB fail.
_DISK_FAIL_GB = 10.0
_DISK_WARN_GB = 50.0


@dataclass
class _CheckResult:
    """Outcome of one diagnostic probe.

    ``status`` is one of pass / warn / fail.  ``name`` is operator-
    facing; ``detail`` carries the actual finding (Python version
    string, GPU count, missing extra name, etc.) so the operator can
    act without re-running the probe themselves.
    """

    name: str
    status: str
    detail: str
    # Optional structured fields that downstream tooling may want
    # (CI gate that filters by category, dashboard widget, etc.).
    extras: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_python_version() -> _CheckResult:
    """Pin Python to the supported window.

    ForgeLM declares ``python_requires=">=3.10"`` in pyproject.toml.  We
    treat 3.10 as the floor (fail below), 3.11+ as the recommended
    surface (pass above), 3.10.x as warn-with-explanation (still works
    but operators should be tracking 3.11 / 3.12).
    """
    version = sys.version_info
    label = f"{version.major}.{version.minor}.{version.micro}"
    if version < (3, 10):
        return _CheckResult(
            name="python.version",
            status=_STATUS_FAIL,
            detail=f"Python {label} is below the supported floor (>=3.10). Upgrade Python to >=3.11.",
            extras={"version": label, "minimum": "3.10", "recommended": "3.11"},
        )
    if version < (3, 11):
        return _CheckResult(
            name="python.version",
            status=_STATUS_WARN,
            detail=f"Python {label} is supported but >=3.11 is recommended for performance + typing improvements.",
            extras={"version": label, "minimum": "3.10", "recommended": "3.11"},
        )
    return _CheckResult(
        name="python.version",
        status=_STATUS_PASS,
        detail=f"Python {label} ({platform.python_implementation()}).",
        extras={"version": label, "implementation": platform.python_implementation()},
    )


def _check_torch_cuda() -> _CheckResult:
    """Detect torch + CUDA availability.

    CPU-only is a *legitimate* setup (small experiments, CI smoke,
    inference-only deployments) so a missing CUDA does not fail —
    it warns so the operator notices that a GPU run will fail later.
    """
    try:
        import torch
    except ImportError:
        return _CheckResult(
            name="torch.installed",
            status=_STATUS_FAIL,
            detail="torch is not installed. Install with: pip install 'forgelm'.",
            extras={"installed": False},
        )
    cuda_available = bool(torch.cuda.is_available())
    cuda_version = getattr(torch.version, "cuda", None) if cuda_available else None
    if not cuda_available:
        return _CheckResult(
            name="torch.cuda",
            status=_STATUS_WARN,
            detail=(
                f"torch {torch.__version__} installed but CUDA is unavailable. "
                "CPU-only runs are supported but training will be very slow; "
                "expect to use this only for tiny experiments or smoke tests."
            ),
            extras={
                "torch_version": torch.__version__,
                "cuda_available": False,
            },
        )
    return _CheckResult(
        name="torch.cuda",
        status=_STATUS_PASS,
        detail=f"torch {torch.__version__} with CUDA {cuda_version}.",
        extras={
            "torch_version": torch.__version__,
            "cuda_available": True,
            "cuda_version": cuda_version,
        },
    )


def _check_gpu_inventory() -> _CheckResult:
    """Enumerate visible GPUs + per-device VRAM.

    Skipped (returns ``warn``) when CUDA is unavailable — no point
    enumerating zero devices.
    """
    try:
        import torch
    except ImportError:
        return _CheckResult(
            name="gpu.inventory",
            status=_STATUS_FAIL,
            detail="torch is not installed.",
            extras={"installed": False},
        )
    if not torch.cuda.is_available():
        return _CheckResult(
            name="gpu.inventory",
            status=_STATUS_WARN,
            detail="No CUDA devices visible; CPU-only mode.",
            extras={"device_count": 0},
        )
    count = torch.cuda.device_count()
    devices: List[Dict[str, Any]] = []
    for idx in range(count):
        try:
            props = torch.cuda.get_device_properties(idx)
        except (RuntimeError, AssertionError) as exc:  # pragma: no cover — defensive
            devices.append(
                {
                    "index": idx,
                    "error": f"could not query device {idx}: {exc}",
                }
            )
            continue
        # ``total_memory`` is bytes; convert to GiB for the operator-
        # facing label and keep raw bytes in the structured payload.
        vram_gib = round(props.total_memory / (1024**3), 1)
        devices.append(
            {
                "index": idx,
                "name": props.name,
                "vram_gib": vram_gib,
                "vram_bytes": props.total_memory,
            }
        )
    if count == 0:
        return _CheckResult(
            name="gpu.inventory",
            status=_STATUS_WARN,
            detail="CUDA reports no visible devices.",
            extras={"device_count": 0},
        )
    summary = ", ".join(f"GPU{d['index']}: {d.get('name', '?')} ({d.get('vram_gib', '?')} GiB)" for d in devices)
    return _CheckResult(
        name="gpu.inventory",
        status=_STATUS_PASS,
        detail=f"{count} GPU(s) — {summary}.",
        extras={"device_count": count, "devices": devices},
    )


def _check_optional_extra(extra: str, module: str, purpose: str) -> _CheckResult:
    """Probe one optional extra without triggering its heavy import side effects."""
    import importlib.util

    spec = importlib.util.find_spec(module)
    if spec is None:
        return _CheckResult(
            name=f"extras.{extra}",
            status=_STATUS_WARN,
            detail=f"Optional extra missing — install with: pip install 'forgelm[{extra}]' (purpose: {purpose}).",
            extras={"extra": extra, "module": module, "installed": False},
        )
    return _CheckResult(
        name=f"extras.{extra}",
        status=_STATUS_PASS,
        detail=f"Installed (module {module}, purpose: {purpose}).",
        extras={"extra": extra, "module": module, "installed": True},
    )


def _check_hf_hub_reachable(timeout_seconds: float = 5.0) -> _CheckResult:
    """HEAD https://huggingface.co/api/models to verify the Hub is reachable.

    Skipped by the caller in ``--offline`` mode.  Treats a connection
    failure as a *warning* rather than a fail because a transient outage
    (operator's wifi, captive portal, corp proxy down) shouldn't refuse
    a doctor run that may exist precisely to surface that fact.
    """
    try:
        import urllib.error
        import urllib.request

        request = urllib.request.Request("https://huggingface.co/api/models", method="HEAD")
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status_code = response.status
        if 200 <= status_code < 400:
            return _CheckResult(
                name="hf_hub.reachable",
                status=_STATUS_PASS,
                detail=f"HuggingFace Hub reachable (HTTP {status_code}).",
                extras={"reachable": True, "status_code": status_code},
            )
        return _CheckResult(
            name="hf_hub.reachable",
            status=_STATUS_WARN,
            detail=f"HuggingFace Hub returned HTTP {status_code}.",
            extras={"reachable": False, "status_code": status_code},
        )
    except urllib.error.URLError as exc:
        return _CheckResult(
            name="hf_hub.reachable",
            status=_STATUS_WARN,
            detail=f"Could not reach HuggingFace Hub: {exc.reason}. Check network / proxy.",
            extras={"reachable": False, "error": str(exc.reason)},
        )
    except (TimeoutError, socket.timeout):
        return _CheckResult(
            name="hf_hub.reachable",
            status=_STATUS_WARN,
            detail=f"HuggingFace Hub probe timed out after {timeout_seconds}s.",
            extras={"reachable": False, "timeout_seconds": timeout_seconds},
        )
    except OSError as exc:  # pragma: no cover — defensive (DNS failure path)
        return _CheckResult(
            name="hf_hub.reachable",
            status=_STATUS_WARN,
            detail=f"Network error reaching HuggingFace Hub: {exc}.",
            extras={"reachable": False, "error": str(exc)},
        )


def _check_hf_cache_offline() -> _CheckResult:
    """Inspect the local HF cache (``--offline`` mode replacement for the Hub probe).

    A populated cache means an air-gapped run can satisfy
    ``local_files_only=True`` without any network access.  An empty cache
    is a warning — the operator may need to run ``forgelm cache-models``
    (Phase 35) before training.
    """
    cache_dir = os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface/hub")
    if not os.path.isdir(cache_dir):
        return _CheckResult(
            name="hf_hub.offline_cache",
            status=_STATUS_WARN,
            detail=(
                f"HF cache not found at {cache_dir}. Air-gapped runs need pre-cached models — "
                "see `forgelm cache-models` (Phase 35) once available, or set HF_HOME and pre-populate."
            ),
            extras={"cache_dir": cache_dir, "exists": False},
        )
    # Bytes used by the cache.  We sum sizes of regular files only; symlinks
    # in the HF cache point at the blob store and would be double-counted.
    total_bytes = 0
    file_count = 0
    for root, _dirs, files in os.walk(cache_dir):
        for filename in files:
            full = os.path.join(root, filename)
            if os.path.islink(full):
                continue
            try:
                total_bytes += os.path.getsize(full)
                file_count += 1
            except OSError:
                # Skip files that disappeared between the walk and the size
                # call (race with concurrent HF download).
                continue
    cache_gib = round(total_bytes / (1024**3), 2)
    offline_env = os.environ.get("HF_HUB_OFFLINE")
    return _CheckResult(
        name="hf_hub.offline_cache",
        status=_STATUS_PASS if file_count > 0 else _STATUS_WARN,
        detail=(
            f"HF cache at {cache_dir}: {cache_gib} GiB across {file_count} file(s). "
            f"HF_HUB_OFFLINE={offline_env or 'unset'}."
        ),
        extras={
            "cache_dir": cache_dir,
            "exists": True,
            "size_gib": cache_gib,
            "file_count": file_count,
            "hf_hub_offline_env": offline_env,
        },
    )


def _check_disk_space(path: str = ".") -> _CheckResult:
    """Workspace free-space probe.

    Disk space is a frequent source of late-failing training runs (a
    fine-tune that crashes mid-checkpoint because the workspace is
    full).  ``shutil.disk_usage`` works cross-platform and is in the
    stdlib so this probe runs without any optional dep.
    """
    try:
        usage = shutil.disk_usage(path)
    except OSError as exc:  # pragma: no cover — defensive (permission denied)
        return _CheckResult(
            name="disk.workspace",
            status=_STATUS_FAIL,
            detail=f"Could not query disk usage at {path!r}: {exc}.",
            extras={"path": os.path.abspath(path), "error": str(exc)},
        )
    free_gib = round(usage.free / (1024**3), 1)
    total_gib = round(usage.total / (1024**3), 1)
    if free_gib < _DISK_FAIL_GB:
        status = _STATUS_FAIL
    elif free_gib < _DISK_WARN_GB:
        status = _STATUS_WARN
    else:
        status = _STATUS_PASS
    return _CheckResult(
        name="disk.workspace",
        status=status,
        detail=f"Workspace {os.path.abspath(path)} — {free_gib} GiB free of {total_gib} GiB.",
        extras={
            "path": os.path.abspath(path),
            "free_gib": free_gib,
            "total_gib": total_gib,
            "fail_threshold_gib": _DISK_FAIL_GB,
            "warn_threshold_gib": _DISK_WARN_GB,
        },
    )


def _check_operator_identity() -> _CheckResult:
    """Article 12 record-keeping reminder.

    ``FORGELM_OPERATOR`` set explicitly is the recommended path for
    CI / pipelines (so audit events carry a meaningful identity).
    Unset is not a failure — the AuditLogger falls back to
    ``getuser()@host`` which is fine on a developer workstation —
    but warn so a CI deployer is reminded to pin it.
    """
    explicit = os.environ.get("FORGELM_OPERATOR")
    if explicit:
        return _CheckResult(
            name="operator.identity",
            status=_STATUS_PASS,
            detail=f"FORGELM_OPERATOR set to {explicit!r}; audit events will carry this identity.",
            extras={"FORGELM_OPERATOR": explicit, "source": "env"},
        )
    # Try to resolve the fallback identity AuditLogger would use so
    # the operator sees what their audit events would look like.
    try:
        import getpass

        username = getpass.getuser()
    except (KeyError, OSError, ImportError):
        username = None
    hostname = socket.gethostname() or "unknown-host"
    if username:
        fallback = f"{username}@{hostname}"
        return _CheckResult(
            name="operator.identity",
            status=_STATUS_WARN,
            detail=(
                f"FORGELM_OPERATOR not set; audit events will fall back to {fallback!r}. "
                "Pin FORGELM_OPERATOR=<id> for CI / pipeline runs so the audit log identifies a stable identity."
            ),
            extras={"FORGELM_OPERATOR": None, "fallback": fallback, "source": "getpass"},
        )
    return _CheckResult(
        name="operator.identity",
        status=_STATUS_FAIL,
        detail=(
            "FORGELM_OPERATOR not set AND getpass.getuser() could not resolve a username. "
            "Set FORGELM_OPERATOR=<id> (or FORGELM_ALLOW_ANONYMOUS_OPERATOR=1 to opt in to "
            "anonymous audit entries — not recommended for EU AI Act Article 12)."
        ),
        extras={"FORGELM_OPERATOR": None, "fallback": None},
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


# Order matters for the text rendering — keep it grouped (env first,
# hardware next, optional extras, then network, then operator identity).
def _build_check_plan(*, offline: bool) -> List[Tuple[str, Callable[[], _CheckResult]]]:
    """Return the ordered list of ``(label, callable)`` probe entries.

    The label is only used in error reporting if a probe itself crashes;
    each ``_CheckResult`` carries its own ``name`` for the renderer.
    """
    plan: List[Tuple[str, Callable[[], _CheckResult]]] = [
        ("python.version", _check_python_version),
        ("torch.cuda", _check_torch_cuda),
        ("gpu.inventory", _check_gpu_inventory),
    ]
    for extra_name, module, purpose in _OPTIONAL_EXTRAS:
        plan.append((f"extras.{extra_name}", _make_extra_probe(extra_name, module, purpose)))
    if offline:
        plan.append(("hf_hub.offline_cache", _check_hf_cache_offline))
    else:
        plan.append(("hf_hub.reachable", _check_hf_hub_reachable))
    plan.append(("disk.workspace", _check_disk_space))
    plan.append(("operator.identity", _check_operator_identity))
    return plan


def _make_extra_probe(extra: str, module: str, purpose: str) -> Callable[[], _CheckResult]:
    """Build a zero-arg closure that probes one optional extra.

    Defined as a top-level helper rather than a lambda so the closure
    binding is explicit and the probe is easy to unit-test by name.
    """

    def _probe() -> _CheckResult:
        return _check_optional_extra(extra, module, purpose)

    return _probe


def _run_all_checks(*, offline: bool) -> List[_CheckResult]:
    """Execute every probe in order, catching crashes per-probe.

    A probe that raises an unexpected exception is converted into a
    ``fail`` result so the rest of the report still renders — partial
    diagnostics are more useful than zero diagnostics when something is
    broken.
    """
    results: List[_CheckResult] = []
    for label, probe in _build_check_plan(offline=offline):
        try:
            results.append(probe())
        except Exception as exc:  # noqa: BLE001 — best-effort: per-probe catch keeps the rest of the report rendering when one diagnostic crashes; converting to fail lets the operator see the broken probe name + traceback class instead of silently dropping it.
            logger.exception("Doctor probe %r raised: %s", label, exc)
            results.append(
                _CheckResult(
                    name=label,
                    status=_STATUS_FAIL,
                    detail=f"Probe crashed: {exc.__class__.__name__}: {exc}",
                    extras={"crashed": True, "error_class": exc.__class__.__name__},
                )
            )
    return results


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


_STATUS_GLYPHS: Dict[str, str] = {
    _STATUS_PASS: "✓",
    _STATUS_WARN: "!",
    _STATUS_FAIL: "✗",
}


def _render_text(results: List[_CheckResult]) -> str:
    """Render a tabular text report.

    Plain ASCII so the output stays readable in CI logs, redirected
    files, and SSH sessions without colour support.  One line per check
    plus a summary footer.
    """
    pass_count = sum(1 for r in results if r.status == _STATUS_PASS)
    warn_count = sum(1 for r in results if r.status == _STATUS_WARN)
    fail_count = sum(1 for r in results if r.status == _STATUS_FAIL)

    lines: List[str] = ["forgelm doctor — environment check", ""]
    name_width = max(len(r.name) for r in results) if results else 0
    for result in results:
        glyph = _STATUS_GLYPHS.get(result.status, "?")
        lines.append(f"  [{glyph} {result.status}] {result.name:<{name_width}}  {result.detail}")
    lines.append("")
    lines.append(f"Summary: {pass_count} pass, {warn_count} warn, {fail_count} fail.")
    return "\n".join(lines)


def _render_json(results: List[_CheckResult]) -> str:
    """Render the JSON envelope.

    Shape mirrors other ForgeLM subcommand contracts:
    ``{"success": bool, "checks": [...], "summary": {"pass": N, "warn": N, "fail": N}}``.
    ``success`` is True iff no check failed (warns are operator-actionable
    but do not flip the contract).
    """
    payload_checks = [
        {
            "name": r.name,
            "status": r.status,
            "detail": r.detail,
            "extras": r.extras,
        }
        for r in results
    ]
    summary = {
        "pass": sum(1 for r in results if r.status == _STATUS_PASS),
        "warn": sum(1 for r in results if r.status == _STATUS_WARN),
        "fail": sum(1 for r in results if r.status == _STATUS_FAIL),
    }
    envelope = {
        "success": summary["fail"] == 0,
        "checks": payload_checks,
        "summary": summary,
    }
    return json.dumps(envelope, indent=2)


def _resolve_exit_code(results: List[_CheckResult]) -> int:
    """Map the result list to one of the public exit codes.

    Contract:
    - 0 (EXIT_SUCCESS) — every check passed (warn included; warns are
      operator-actionable but do not block)
    - 1 (EXIT_CONFIG_ERROR) — at least one check returned ``fail`` (a
      misconfiguration the operator can correct)
    - 2 (EXIT_TRAINING_ERROR) — a probe itself crashed (an unexpected
      doctor bug, surfaced as runtime-error class so CI/CD retry logic
      treats it the same way as other runtime failures)
    """
    crashed = any(r.extras.get("crashed") for r in results)
    if crashed:
        return EXIT_TRAINING_ERROR
    has_fail = any(r.status == _STATUS_FAIL for r in results)
    return EXIT_CONFIG_ERROR if has_fail else EXIT_SUCCESS


def _run_doctor_cmd(args, output_format: str) -> None:
    """Top-level dispatcher for ``forgelm doctor``.

    Reads ``args.offline`` (argparse default ``False``) and emits either
    the text report or the JSON envelope.  Exits with the public
    contract code resolved by :func:`_resolve_exit_code`.
    """
    offline = bool(getattr(args, "offline", False))
    results = _run_all_checks(offline=offline)
    if output_format == "json":
        print(_render_json(results))
    else:
        print(_render_text(results))
    sys.exit(_resolve_exit_code(results))


# Re-exports for tests / monkeypatch — kept stable.
__all__ = [
    "_CheckResult",
    "_check_python_version",
    "_check_torch_cuda",
    "_check_gpu_inventory",
    "_check_optional_extra",
    "_check_hf_hub_reachable",
    "_check_hf_cache_offline",
    "_check_disk_space",
    "_check_operator_identity",
    "_build_check_plan",
    "_run_all_checks",
    "_render_text",
    "_render_json",
    "_resolve_exit_code",
    "_run_doctor_cmd",
    "_OPTIONAL_EXTRAS",
]


def _maybe_unused() -> Optional[None]:  # pragma: no cover — kept for typing import alignment
    return None

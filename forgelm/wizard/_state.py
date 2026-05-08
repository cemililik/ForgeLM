"""Wizard state, persistence, summary + step-diff helpers.

Persistence (Phase 22 / G6): state snapshot is YAML at
``$XDG_CACHE_HOME/forgelm/wizard_state.yaml`` (or
``~/.cache/forgelm/wizard_state.yaml`` when XDG is unset).  Schema
versioned so a future shape change can clear stale snapshots cleanly.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import yaml

from ._io import _print

logger = logging.getLogger("forgelm.wizard")


# ---------------------------------------------------------------------------
# Wizard-wide defaults — kept in lockstep with the Pydantic schema in
# ``forgelm/config.py``.  Wherever a wizard-side default deliberately
# differs from the schema, the comment names the rationale.
# ---------------------------------------------------------------------------


DEFAULT_MAX_LENGTH = 2048
# ``LoraConfigModel.r`` default in ``forgelm/config.py`` is ``8``; the
# wizard tracks the schema default exactly so an operator who accepts
# every prompt produces a YAML byte-equivalent to ``ForgeConfig()``.
DEFAULT_LORA_R = 8
DEFAULT_LORA_ALPHA = 2 * DEFAULT_LORA_R
DEFAULT_DROPOUT = 0.1
DEFAULT_EPOCHS = 3
DEFAULT_BATCH_SIZE = 4
DEFAULT_LR = 2e-5

# Curated popular-model presets.  This list and the
# ``USE_CASE_PRESETS`` in ``site/js/wizard.js`` are intentionally kept
# in lockstep — the operator using both surfaces sees the same
# recommended models.
POPULAR_MODELS: List[str] = [
    "meta-llama/Llama-3.1-8B-Instruct",
    "Qwen/Qwen2.5-7B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "microsoft/Phi-3-mini-4k-instruct",
    "HuggingFaceTB/SmolLM2-1.7B-Instruct",
]


TARGET_MODULE_PRESETS: Dict[str, List[str]] = {
    "standard": ["q_proj", "v_proj"],
    "extended": ["q_proj", "k_proj", "v_proj", "o_proj"],
    "full": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
}


# Common dataset-format hints for preference-based trainers
# (DPO/SimPO/ORPO).
_PREFERENCE_COLUMNS_HINT = "Columns: prompt, chosen, rejected"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


# Bumped whenever the on-disk wizard-state shape changes.  Version
# mismatches are silently ignored (treated as "no resume available").
_STATE_VERSION = 1


def _wizard_state_dir() -> Path:
    """Return the directory the wizard persists its state under.

    Honours ``XDG_CACHE_HOME`` per the XDG Base Directory spec; falls
    back to ``~/.cache/forgelm`` when unset.  The directory is created
    on first write — no side effects on plain reads.
    """
    xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
    base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return base / "forgelm"


def _wizard_state_path() -> Path:
    """Absolute path to ``wizard_state.yaml``."""
    return _wizard_state_dir() / "wizard_state.yaml"


def _save_wizard_state(state: Mapping[str, Any]) -> None:
    """Persist *state* to ``_wizard_state_path()``.

    Best-effort: filesystem errors (read-only home, ENOSPC, sandboxed
    container) are logged at WARNING and swallowed — the wizard's
    contract is to *produce a config*, not to guarantee resumability.
    """
    target = _wizard_state_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        snapshot = {"v": _STATE_VERSION, **dict(state)}
        with open(target, "w", encoding="utf-8") as fh:
            yaml.safe_dump(snapshot, fh, default_flow_style=False, sort_keys=False)
        # Wizard state can carry compliance metadata (provider name,
        # contact, governance fields) that operators consider sensitive.
        # ``0o600`` keeps it readable only by the operator running the
        # wizard.  Best-effort: chmod is a no-op on Windows / FAT.
        try:
            os.chmod(target, 0o600)
        except OSError:  # pragma: no cover — best-effort permission tightening
            pass
    except OSError as exc:
        logger.warning("Could not persist wizard state to %s: %s", target, exc)


def _load_wizard_state() -> Optional[Dict[str, Any]]:
    """Load a previously-saved state snapshot, returning ``None`` on miss.

    Version mismatches and parse errors return ``None`` — the wizard
    falls back to defaults rather than asking the operator to debug a
    stale snapshot.
    """
    target = _wizard_state_path()
    if not target.is_file():
        return None
    try:
        with open(target, "r", encoding="utf-8") as fh:
            snapshot = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Could not read wizard state from %s: %s", target, exc)
        return None
    if not isinstance(snapshot, dict) or snapshot.get("v") != _STATE_VERSION:
        return None
    snapshot.pop("v", None)
    return snapshot


def _clear_wizard_state() -> None:
    """Remove a stale state snapshot, swallowing filesystem errors."""
    target = _wizard_state_path()
    try:
        if target.is_file():
            target.unlink()
    except OSError as exc:  # pragma: no cover — best-effort cleanup
        logger.warning("Could not remove wizard state at %s: %s", target, exc)


# ---------------------------------------------------------------------------
# Wizard-state dataclass — threaded through every step in the
# orchestrator.  Persisted via the helpers above.
# ---------------------------------------------------------------------------


# Sentinel for the "manual" use-case (no preselect).  Mirrored in
# ``_byod._MANUAL_USE_CASE`` for callers that want to import from
# either submodule.
_MANUAL_USE_CASE = "custom"


@dataclass
class _WizardState:
    """In-memory snapshot of every wizard answer + the partial config dict.

    Persisted after each completed step to ``wizard_state.yaml`` so a
    refresh / Ctrl-C / fresh session resumes where the operator left
    off.
    """

    experience: str = "expert"  # "beginner" | "expert"
    use_case: str = _MANUAL_USE_CASE
    current_step: int = 0
    completed_steps: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Step-diff preview — Phase 22 / G7.  Each step prints the keys it
# just added or changed, mirroring the web wizard's live YAML preview
# at terminal-friendly granularity.
# ---------------------------------------------------------------------------


def _flatten_dict(d: Mapping[str, Any], *, prefix: str = "") -> Dict[str, Any]:
    """Recursively flatten a dict into ``dotted.path → value`` entries."""
    out: Dict[str, Any] = {}
    for key, value in d.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            out.update(_flatten_dict(value, prefix=path))
        else:
            out[path] = value
    return out


def _print_step_diff(prev: Mapping[str, Any], curr: Mapping[str, Any], step_label: str) -> None:
    """Print a ``+ key.path: value`` diff for everything *curr* added vs *prev*."""
    prev_flat = _flatten_dict(prev)
    curr_flat = _flatten_dict(curr)
    added = {k: v for k, v in curr_flat.items() if k not in prev_flat}
    changed = {k: (prev_flat[k], v) for k, v in curr_flat.items() if k in prev_flat and prev_flat[k] != v}
    if not added and not changed:
        return
    _print(f"\n  Step diff ({step_label}):")
    for key in sorted(added):
        _print(f"    + {key}: {added[key]!r}")
    for key in sorted(changed):
        before, after = changed[key]
        _print(f"    ~ {key}: {before!r} → {after!r}")


# ---------------------------------------------------------------------------
# Save + summary helpers
# ---------------------------------------------------------------------------


def _save_config_to_file(config: Dict[str, Any], requested_filename: str) -> str:
    """Write *config* as YAML; falls back to a unique filename on OSError.

    Uses ``yaml.safe_dump`` so unknown Python objects (e.g. accidental
    ``Path`` / ``set`` leak from a collector) raise a representable
    error instead of silently emitting a Python-only ``!!python/object``
    tag that ``ForgeConfig`` then rejects on load.
    """
    try:
        with open(requested_filename, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        _print(f"\n  Config saved to: {requested_filename}")
        logger.info("Wizard config saved to %s", requested_filename)
        return requested_filename
    except OSError as e:
        logger.error("Could not save wizard config to %s: %s", requested_filename, e)
        _print(f"\n  Error: Could not save config to {requested_filename}: {e}")

    from datetime import datetime as _dt

    base = os.path.splitext(os.path.basename(requested_filename))[0] or "my_config"
    fallback = os.path.join(
        os.path.expanduser("~"),
        f"{base}_{_dt.now().strftime('%Y%m%d_%H%M%S')}.yaml",
    )
    try:
        with open(fallback, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        _print(f"  Saved to fallback location: {fallback}")
        logger.info("Wizard config saved to fallback location %s", fallback)
        return fallback
    except OSError as e:
        logger.error("Fallback wizard config save also failed (%s): %s", fallback, e)
        _print(f"  Fallback save also failed ({fallback}): {e}")
        raise


def _strategy_label(*, use_galore: bool, load_in_4bit: bool, method: str) -> str:
    """Human-readable label for the strategy summary line."""
    if use_galore:
        return "GaLore"
    base = "QLoRA" if load_in_4bit else "LoRA"
    if method != "lora":
        return f"{base} + {method.upper()}"
    return base


def _print_wizard_summary(config: Dict[str, Any]) -> None:
    """Print a multi-section summary of the resolved config + the full YAML."""
    _print("\n" + "=" * 60)
    _print("  Configuration Summary")
    _print("=" * 60)
    model = config["model"]["name_or_path"]
    backend = config["model"].get("backend", "transformers")
    load_in_4bit = config["model"].get("load_in_4bit", False)
    lora_method = config.get("lora", {}).get("method", "lora")
    use_galore = bool(config["training"].get("galore_enabled", False))
    trainer = config["training"].get("trainer_type", "sft").upper()
    lora_r = config.get("lora", {}).get("r", DEFAULT_LORA_R)
    lora_alpha = config.get("lora", {}).get("alpha", DEFAULT_LORA_ALPHA)
    dataset = config.get("data", {}).get("dataset_name_or_path", "(not set)")
    epochs = config["training"].get("num_train_epochs", DEFAULT_EPOCHS)
    batch = config["training"].get("per_device_train_batch_size", DEFAULT_BATCH_SIZE)
    output = config["training"].get("output_dir", "./checkpoints")
    _print(f"  Model:    {model}")
    _print(f"  Backend:  {backend}")
    _print(f"  Strategy: {_strategy_label(use_galore=use_galore, load_in_4bit=load_in_4bit, method=lora_method)}")
    _print(f"  Trainer:  {trainer}")
    _print(f"  LoRA:     r={lora_r}, alpha={lora_alpha}")
    _print(f"  Dataset:  {dataset}")
    _print(f"  Epochs:   {epochs}, Batch: {batch}")
    _print(f"  Output:   {output}/final_model")
    sections = [k for k in config.keys() if k not in ("model", "lora", "training", "data")]
    if sections:
        _print(f"  Extras:   {', '.join(sorted(sections))}")
    _print("\n  Full YAML preview:")
    _print("  " + "─" * 58)
    yaml_text = yaml.safe_dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True)
    for line in yaml_text.splitlines():
        _print(f"  {line}")
    _print("  " + "─" * 58)


def _strip_internal_meta(config: Mapping[str, Any]) -> Dict[str, Any]:
    """Remove keys prefixed with ``_wizard_`` before writing the YAML."""
    return {k: v for k, v in config.items() if not str(k).startswith("_wizard_")}

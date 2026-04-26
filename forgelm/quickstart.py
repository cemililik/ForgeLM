"""Quickstart layer — Phase 10.5.

Generates a ready-to-train YAML config from a small library of curated
templates. Same YAML schema as a hand-written config; the trainer doesn't
know whether a config came from quickstart or from the wizard.

Templates ship with conservative defaults (QLoRA 4-bit NF4, rank=8, batch=1
with gradient accumulation, gradient checkpointing on, safety/compliance
opt-in only) so a first-time user gets a working model on an 8-12 GB
consumer GPU rather than a CUDA OOM.

Usage (CLI):
    forgelm quickstart customer-support
    forgelm quickstart code-assistant --model deepseek-ai/deepseek-coder-1.3b-instruct
    forgelm quickstart --list

Usage (programmatic):
    from forgelm.quickstart import run_quickstart, list_templates
    result = run_quickstart("customer-support", dry_run=True)
    print(result.config_path)
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger("forgelm.quickstart")


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Template:
    """A curated quickstart entry — config + bundled dataset + sizing hints."""

    name: str  # CLI handle (kebab-case)
    title: str  # human-readable banner
    description: str  # one-line rationale
    primary_model: str  # 7B-class default
    fallback_model: str  # smaller variant for <8 GB GPUs
    trainer_type: str  # sft | grpo (matches TrainingConfig.trainer_type)
    estimated_minutes: int  # rough wall-clock on the primary model
    min_vram_for_primary_gb: float  # threshold under which fallback is chosen
    bundled_dataset: bool  # False ⇒ user must supply --dataset
    license_note: str  # one-line license for the bundled dataset


TEMPLATES: Dict[str, Template] = {
    "customer-support": Template(
        name="customer-support",
        title="Customer Support Assistant",
        description="Polite, brand-safe support replies. SFT on a tiny seed FAQ dataset.",
        primary_model="Qwen/Qwen2.5-7B-Instruct",
        fallback_model="HuggingFaceTB/SmolLM2-1.7B-Instruct",
        trainer_type="sft",
        estimated_minutes=15,
        min_vram_for_primary_gb=10.0,
        bundled_dataset=True,
        license_note="CC-BY-SA 4.0 (authored by ForgeLM contributors)",
    ),
    "code-assistant": Template(
        name="code-assistant",
        title="Code Assistant",
        description="Short code-question Q&A. SFT on a curated programming seed set.",
        primary_model="Qwen/Qwen2.5-Coder-7B-Instruct",
        fallback_model="HuggingFaceTB/SmolLM2-1.7B-Instruct",
        trainer_type="sft",
        estimated_minutes=25,
        min_vram_for_primary_gb=10.0,
        bundled_dataset=True,
        license_note="CC-BY-SA 4.0 (authored by ForgeLM contributors)",
    ),
    "domain-expert": Template(
        name="domain-expert",
        title="Domain Expert (BYOD — bring your own docs)",
        description="Empty data — pair with `forgelm ingest` (Phase 11) or a custom JSONL.",
        primary_model="Qwen/Qwen2.5-7B-Instruct",
        fallback_model="HuggingFaceTB/SmolLM2-1.7B-Instruct",
        trainer_type="sft",
        estimated_minutes=20,
        min_vram_for_primary_gb=10.0,
        bundled_dataset=False,
        license_note="N/A — user-supplied data",
    ),
    "medical-qa-tr": Template(
        name="medical-qa-tr",
        title="Medical Q&A (Türkçe / Turkish)",
        description="Turkish medical-question SFT seed. Disclaimers baked in; not clinical advice.",
        primary_model="Qwen/Qwen2.5-7B-Instruct",
        fallback_model="HuggingFaceTB/SmolLM2-1.7B-Instruct",
        trainer_type="sft",
        estimated_minutes=15,
        min_vram_for_primary_gb=10.0,
        bundled_dataset=True,
        license_note="CC-BY-SA 4.0 (authored by ForgeLM contributors; not medical advice)",
    ),
    "grpo-math": Template(
        name="grpo-math",
        title="Math Reasoning via GRPO",
        description="Group Relative Policy Optimization on grade-school math problems.",
        primary_model="Qwen/Qwen2.5-Math-7B-Instruct",
        fallback_model="Qwen/Qwen2.5-Math-1.5B-Instruct",
        trainer_type="grpo",
        estimated_minutes=45,
        min_vram_for_primary_gb=12.0,
        bundled_dataset=True,
        license_note="CC-BY-SA 4.0 (math problems authored by ForgeLM contributors)",
    ),
}


# ---------------------------------------------------------------------------
# Filesystem accessors
# ---------------------------------------------------------------------------


def templates_dir() -> Path:
    """Absolute path to the bundled `forgelm/templates/` directory."""
    return Path(__file__).resolve().parent / "templates"


def template_assets(name: str) -> Tuple[Path, Optional[Path]]:
    """Return (config_path, dataset_path-or-None) for a template's bundled files."""
    base = templates_dir() / name
    config_path = base / "config.yaml"
    if not config_path.is_file():
        raise FileNotFoundError(f"Template '{name}' missing config.yaml at {config_path}")
    data_path = base / "data.jsonl"
    return config_path, (data_path if data_path.is_file() else None)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_templates() -> List[Template]:
    """Return all registered templates in stable insertion order."""
    return list(TEMPLATES.values())


def get_template(name: str) -> Template:
    """Look up a template by its CLI name; raises with a helpful message on miss."""
    if name not in TEMPLATES:
        available = ", ".join(sorted(TEMPLATES.keys()))
        raise ValueError(f"Unknown template '{name}'. Available: {available}")
    return TEMPLATES[name]


def auto_select_model(template: Template, available_vram_gb: Optional[float]) -> Tuple[str, str]:
    """Pick the appropriate model for the user's GPU.

    Returns ``(model_name, selection_reason)`` so callers can surface the
    decision in logs / wizard summaries instead of silently downsizing.
    """
    if available_vram_gb is None:
        return template.primary_model, "no-gpu-detected (using primary model; configure --offline if missing weights)"
    if available_vram_gb < template.min_vram_for_primary_gb:
        return (
            template.fallback_model,
            f"available VRAM {available_vram_gb:.1f} GB < {template.min_vram_for_primary_gb} GB — auto-downsized",
        )
    return template.primary_model, f"available VRAM {available_vram_gb:.1f} GB ≥ primary requirement"


@dataclass
class QuickstartResult:
    """Outcome of a quickstart run."""

    template: Template
    config_path: Path  # generated YAML on disk
    chosen_model: str
    selection_reason: str
    dataset_path: str
    dry_run: bool
    started_training: bool = False
    extra_notes: List[str] = field(default_factory=list)


def _detect_available_vram_gb() -> Optional[float]:
    """Best-effort total VRAM lookup; returns None if no GPU or torch missing."""
    try:
        import torch  # local import — quickstart should not pull torch into --help
    except ImportError:
        return None
    try:
        if not torch.cuda.is_available():
            return None
        _, total = torch.cuda.mem_get_info()
        # Use total (capacity) rather than free (current snapshot) for the
        # "will this template fit at all" question.
        return total / (1024**3)
    except Exception as exc:  # pragma: no cover — best-effort only
        logger.debug("VRAM probe failed: %s", exc)
        return None


def _resolve_dataset(template: Template, dataset_override: Optional[str], scratch_dir: Path) -> Tuple[str, List[str]]:
    """Resolve the dataset path and return (final_path, extra_notes)."""
    notes: List[str] = []
    if dataset_override:
        return dataset_override, notes

    _, bundled = template_assets(template.name)
    if bundled is None:
        # domain-expert and any other BYOD templates land here.
        raise ValueError(
            f"Template '{template.name}' does not bundle a dataset. "
            "Pass --dataset PATH or generate one via `forgelm ingest` (Phase 11)."
        )
    # Copy the bundled dataset next to the generated config so users can edit
    # it without touching the package install.
    dest = scratch_dir / f"{template.name}.jsonl"
    if dest.resolve() != bundled.resolve():
        scratch_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bundled, dest)
        notes.append(f"copied seed dataset to {dest}")
    return str(dest), notes


def _materialize_config(template: Template, chosen_model: str, dataset_path: str) -> Dict[str, Any]:
    """Load the bundled YAML and patch in the runtime overrides."""
    config_path, _ = template_assets(template.name)
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    cfg.setdefault("model", {})["name_or_path"] = chosen_model
    cfg.setdefault("data", {})["dataset_name_or_path"] = dataset_path
    return cfg


def _default_output_path(template_name: str) -> Path:
    """Default location for the generated YAML: ``./configs/<template>-<ts>.yaml``."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("configs") / f"{template_name}-{timestamp}.yaml"


def run_quickstart(
    template_name: str,
    *,
    model_override: Optional[str] = None,
    dataset_override: Optional[str] = None,
    output_path: Optional[str] = None,
    dry_run: bool = False,
    available_vram_gb: Optional[float] = None,
) -> QuickstartResult:
    """Generate a config from a template and (optionally) report next steps.

    Args:
        template_name: One of the keys in :data:`TEMPLATES` (e.g. ``"customer-support"``).
        model_override: Skip auto-select and force a specific HF Hub ID.
        dataset_override: Use this dataset path instead of the bundled seed.
        output_path: Destination for the generated YAML. Defaults to
            ``./configs/<template>-<timestamp>.yaml``.
        dry_run: Generate the YAML without invoking training.
        available_vram_gb: Override the auto-detected GPU capacity (mainly for tests).

    Returns:
        A :class:`QuickstartResult` describing what was generated and chosen.
    """
    template = get_template(template_name)

    if available_vram_gb is None:
        available_vram_gb = _detect_available_vram_gb()

    if model_override:
        chosen_model = model_override
        selection_reason = "model-override flag"
    else:
        chosen_model, selection_reason = auto_select_model(template, available_vram_gb)

    config_target = Path(output_path) if output_path else _default_output_path(template_name)
    config_target.parent.mkdir(parents=True, exist_ok=True)

    dataset_path, dataset_notes = _resolve_dataset(template, dataset_override, config_target.parent)

    cfg = _materialize_config(template, chosen_model, dataset_path)

    with open(config_target, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)

    logger.info(
        "quickstart: template=%s model=%s dataset=%s config=%s (%s)",
        template.name,
        chosen_model,
        dataset_path,
        config_target,
        selection_reason,
    )

    return QuickstartResult(
        template=template,
        config_path=config_target,
        chosen_model=chosen_model,
        selection_reason=selection_reason,
        dataset_path=dataset_path,
        dry_run=dry_run,
        started_training=False,
        extra_notes=dataset_notes,
    )


# ---------------------------------------------------------------------------
# CLI helpers (used by forgelm.cli)
# ---------------------------------------------------------------------------


def format_template_list() -> str:
    """Render the template registry as a human-readable list."""
    lines = ["Available quickstart templates:", ""]
    for tpl in list_templates():
        bundled = "✔ bundled data" if tpl.bundled_dataset else "✘ user-supplied data"
        lines.append(f"  {tpl.name}")
        lines.append(f"    {tpl.title} — {tpl.description}")
        lines.append(
            f"    primary={tpl.primary_model}  fallback={tpl.fallback_model}  "
            f"trainer={tpl.trainer_type}  ~{tpl.estimated_minutes}min  {bundled}"
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def summarize_result(result: QuickstartResult) -> str:
    """Plain-text summary printed by the CLI after generation."""
    lines = [
        f"Template       : {result.template.name} — {result.template.title}",
        f"Model          : {result.chosen_model}",
        f"Selection      : {result.selection_reason}",
        f"Dataset        : {result.dataset_path}",
        f"Generated YAML : {result.config_path}",
        f"Trainer        : {result.template.trainer_type}",
        f"Est. wall-clock: ~{result.template.estimated_minutes} minutes on primary model",
    ]
    for note in result.extra_notes:
        lines.append(f"Note           : {note}")
    if result.dry_run:
        lines.append("")
        lines.append(f"Dry-run only. To start training: forgelm --config {result.config_path}")
    return "\n".join(lines)

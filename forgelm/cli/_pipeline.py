"""Phase 14 — Multi-stage training pipeline orchestrator.

Top-level entry point for ``forgelm --config pipeline.yaml`` runs.  The
orchestrator iterates over the ordered :class:`PipelineConfig.stages`,
materialises a flat :class:`ForgeConfig` per stage via
:func:`forgelm.config.merge_pipeline_stage_config`, hands it to a fresh
:class:`forgelm.trainer.ForgeTrainer`, and threads the state through a
crash-safe JSON state file + an append-only audit-log event stream.

Layering rule — see ``docs/roadmap/phase-14-pipeline-chains.md`` Task 2:
``forgelm/trainer.py`` is **not** aware of the pipeline layer.  Each
stage is a single-stage run from the trainer's point of view; only this
module knows there is an outer loop.  When a config carries no
``pipeline:`` block, this module is never imported.

Key responsibilities:

- **Auto-chain** each stage's ``model.name_or_path`` to the previous
  stage's output path (or honour an explicit stage override / CLI
  ``--input-model`` override).
- **Per-stage gates** — auto-revert and human-approval are composed
  one stage at a time; a failed gate stops the chain and marks
  downstream stages ``skipped_due_to_prior_revert``.
- **Crash-safe state** — every stage transition is atomically written to
  ``<root_output_dir>/pipeline_state.json`` (tmp file + ``os.replace``).
  ``--resume-from`` reads that file and skips ``completed`` stages whose
  outputs still exist on disk.
- **Annex-IV manifest** — every transition also rewrites
  ``<root_output_dir>/compliance/pipeline_manifest.json`` (delegated to
  :mod:`forgelm.compliance`) so reviewers can correlate every chain
  failure to a frozen artefact.
- **Audit + webhook** — emits ``pipeline.started`` / ``.stage_started``
  / ``.stage_completed`` / ``.stage_reverted`` / ``.completed`` audit
  events alongside the existing per-stage ``training.*`` vocabulary; the
  webhook notifier gains ``notify_pipeline_*`` methods that the orchestrator
  calls at the same transitions.
- **Exit-code routing** — the pipeline aggregates per-stage outcomes
  via ``worst_exit = max(worst_exit, code)``, which gives the
  precedence order
  ``EXIT_AWAITING_APPROVAL (4)`` > ``EXIT_EVAL_FAILURE (3)`` >
  ``EXIT_TRAINING_ERROR (2)`` > ``EXIT_CONFIG_ERROR (1)`` >
  ``EXIT_SUCCESS (0)``.  In practice an approval gate causes an
  immediate ``break`` (no later stages run) and any other failure
  sets ``chain_broken = True`` (downstream stages skip), so the
  precedence rule is reached only when a single stage produces a
  single non-zero code.  Numeric ordering of the exit-code constants
  matches the documented severity ramp — operators reading the exit
  code in a shell only see the "worst" outcome from a single stage
  that ran.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from ..config import ForgeConfig, PipelineConfig, PipelineStage, merge_pipeline_stage_config
from ._exit_codes import (
    EXIT_AWAITING_APPROVAL,
    EXIT_CONFIG_ERROR,
    EXIT_EVAL_FAILURE,
    EXIT_SUCCESS,
    EXIT_TRAINING_ERROR,
)

logger = logging.getLogger("forgelm.pipeline")


# ---------------------------------------------------------------------------
# State enums + dataclasses
# ---------------------------------------------------------------------------


StageStatusLiteral = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "gated_pending_approval",
    "skipped_due_to_prior_revert",
    "skipped_by_filter",
]
"""Per-stage status values.  See Phase 14 Task 3 for the meaning of each."""


InputSourceLiteral = Literal["root", "chain", "stage_explicit", "cli_override"]
"""How the orchestrator resolved a stage's input model path.  Recorded on
the per-stage state so reviewers can trace any chain interruption
(``cli_override`` is the operator escape hatch that intentionally breaks
the chain)."""


FinalStatusLiteral = Literal[
    "in_progress",
    "completed",
    "stopped_at_stage",
    "gated_pending_approval",
]


@dataclass
class PipelineStageState:
    """Per-stage state snapshot persisted to disk + included in the manifest."""

    name: str
    index: int
    trainer_type: str
    status: StageStatusLiteral = "pending"
    input_model: Optional[str] = None
    input_source: Optional[InputSourceLiteral] = None
    output_model: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    training_manifest: Optional[str] = None
    metrics: Dict[str, float] = field(default_factory=dict)
    gate_decision: Optional[str] = None
    auto_revert_triggered: bool = False
    skipped_reason: Optional[str] = None
    exit_code: Optional[int] = None
    error: Optional[str] = None


@dataclass
class PipelineState:
    """Top-level pipeline-run state snapshot.

    Round-tripped to ``pipeline_state.json`` after every stage transition.
    Compatible with :mod:`json` (atomic-write via tmp + ``os.replace``);
    no nested non-serialisable types.
    """

    pipeline_run_id: str
    pipeline_config_hash: str
    forgelm_version: str
    started_at: str
    finished_at: Optional[str] = None
    final_status: FinalStatusLiteral = "in_progress"
    stopped_at: Optional[str] = None
    stages: List[PipelineStageState] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_iso_now() -> str:
    """UTC ISO-8601 timestamp with seconds precision.

    Mirrors the format ``forgelm/compliance.py`` already uses for audit
    log entries so timestamps line up across the two surfaces.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _generate_run_id() -> str:
    """Return a pipeline run id of shape ``pl_YYYY-MM-DD_<6-hex>``.

    The date prefix lets operators eyeball runs by week without consulting
    the manifest; the 6-hex suffix gives ~16 million combinations per day,
    which is more than enough to disambiguate same-day re-runs even in
    aggressive CI loops.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"pl_{today}_{secrets.token_hex(3)}"


def _compute_pipeline_config_hash(pipeline_yaml_bytes: bytes) -> str:
    """SHA-256 of the *raw bytes* of the pipeline YAML file.

    Hashing the bytes (not the parsed dict) is intentional: it locks the
    on-disk artefact, which is what regulators audit.  YAML
    comments / key ordering / whitespace are all in scope; an operator
    who edits the file between runs gets a different hash even if the
    semantic content is unchanged, and the ``--resume-from`` stale-state
    guard catches it.
    """
    return "sha256:" + hashlib.sha256(pipeline_yaml_bytes).hexdigest()


def _pipeline_paths(root_cfg: ForgeConfig) -> Dict[str, str]:
    """Resolve the canonical filesystem paths for the pipeline run.

    All pipeline-level artefacts (state file, manifest, audit log) live
    under :attr:`PipelineConfig.output_dir` (defaults to
    ``./pipeline_run``).  Per-stage trainer artefacts continue to live
    under each stage's own ``training.output_dir`` (as in single-stage
    runs) — the pipeline output dir is the *index* directory, distinct
    from the stage checkpoint directories so operators can ``rm -rf``
    individual stages without nuking the pipeline manifest.
    """
    if root_cfg.pipeline is None:  # defensive — orchestrator constructor catches this earlier
        raise ValueError("Cannot derive pipeline paths from a config with no `pipeline` block.")
    root_output_dir = root_cfg.pipeline.output_dir
    return {
        "root_output_dir": root_output_dir,
        "state_file": os.path.join(root_output_dir, "pipeline_state.json"),
        "manifest_dir": os.path.join(root_output_dir, "compliance"),
        "manifest_file": os.path.join(root_output_dir, "compliance", "pipeline_manifest.json"),
    }


def _atomic_write_json(path: str, payload: Dict[str, Any]) -> None:
    """Write ``payload`` to ``path`` atomically.

    Pattern: serialise to a sibling ``<path>.tmp`` then ``os.replace`` it
    onto the final name — guarantees a reader on any concurrent process
    either sees the previous version or the new version, never a half-
    written file.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False)
    os.replace(tmp, path)


def _serialise_state(state: PipelineState) -> Dict[str, Any]:
    """Return a JSON-ready dict representation of a :class:`PipelineState`."""
    return asdict(state)


def _deserialise_state(payload: Dict[str, Any]) -> PipelineState:
    """Round-trip :class:`PipelineState` from its on-disk JSON shape.

    Tolerates unknown keys (future-forward compat) and missing optionals
    (legacy state files).  Type-coerces ``stages[]`` back into
    :class:`PipelineStageState` instances so the rest of the orchestrator
    sees a strongly-typed object.
    """
    stages_raw = payload.get("stages", [])
    stages = [
        PipelineStageState(**{k: v for k, v in s.items() if k in PipelineStageState.__dataclass_fields__})
        for s in stages_raw
    ]
    return PipelineState(
        pipeline_run_id=payload["pipeline_run_id"],
        pipeline_config_hash=payload["pipeline_config_hash"],
        forgelm_version=payload.get("forgelm_version", "unknown"),
        started_at=payload["started_at"],
        finished_at=payload.get("finished_at"),
        final_status=payload.get("final_status", "in_progress"),
        stopped_at=payload.get("stopped_at"),
        stages=stages,
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class PipelineOrchestrator:
    """Drives a multi-stage pipeline run end-to-end.

    Constructor takes the root config and the *bytes* of the pipeline YAML
    (the bytes are hashed for the stale-resume guard; the parsed config
    drives the actual stage iteration).
    """

    def __init__(
        self,
        root_cfg: ForgeConfig,
        pipeline_yaml_bytes: bytes,
        *,
        output_format: str = "text",
    ) -> None:
        if root_cfg.pipeline is None:
            # Defensive — callers should only reach this path when a
            # ``pipeline:`` block is present.  A None ``pipeline`` here
            # signals a CLI dispatch bug; fail loud rather than running
            # an empty pipeline.
            raise ValueError("PipelineOrchestrator instantiated with a config that has no `pipeline` block.")
        self.root_cfg: ForgeConfig = root_cfg
        self.pipeline: PipelineConfig = root_cfg.pipeline
        self.config_hash: str = _compute_pipeline_config_hash(pipeline_yaml_bytes)
        self.output_format: str = output_format
        self.paths: Dict[str, str] = _pipeline_paths(root_cfg)

    # -- run-mode entry points ------------------------------------------------

    def run(
        self,
        *,
        stage_filter: Optional[str] = None,
        resume_from: Optional[str] = None,
        force_resume: bool = False,
        input_model_override: Optional[str] = None,
    ) -> int:
        """Execute the pipeline.  Returns a process exit code.

        ``stage_filter`` and ``resume_from`` are mutually exclusive; the
        caller (CLI parser) validates this before reaching here.

        Exit-code aggregation uses ``worst_exit = max(worst_exit, code)``
        across stages, giving the numeric precedence:
        ``EXIT_AWAITING_APPROVAL (4)`` > ``EXIT_EVAL_FAILURE (3)`` >
        ``EXIT_TRAINING_ERROR (2)`` > ``EXIT_CONFIG_ERROR (1)`` >
        ``EXIT_SUCCESS (0)``.  An approval gate triggers an immediate
        ``break`` (later stages stay ``pending``) and any other non-zero
        outcome sets ``chain_broken = True`` (later stages skip with
        ``skipped_due_to_prior_revert``), so multi-stage compounding is
        rare — in practice the return value reflects the single failing
        stage's exit code.
        """
        # 1. Load (or initialise) state.
        existing = self._load_state_file()
        if resume_from is not None and existing is None:
            logger.error(
                "Cannot --resume-from %r: no pipeline_state.json found at %s.  Run the pipeline once first.",
                resume_from,
                self.paths["state_file"],
            )
            return EXIT_CONFIG_ERROR
        if resume_from is not None:
            refusal = self._validate_resume_state(existing, force=force_resume)
            if refusal is not None:
                # Library-style refusal — return the exit code through
                # the normal ``run()`` flow rather than ``sys.exit``-ing
                # mid-method.  Matches the surrounding error paths
                # (missing state file, unknown stage name) and keeps the
                # test surface uniform on ``assert code == EXIT_CONFIG_ERROR``.
                return EXIT_CONFIG_ERROR
            state = existing
        else:
            state = self._init_state()

        # 2. Determine which stages to execute.
        stages_to_skip_completed: List[str] = []
        if resume_from is not None:
            try:
                resume_idx = next(i for i, s in enumerate(self.pipeline.stages) if s.name == resume_from)
            except StopIteration:
                logger.error(
                    "Cannot --resume-from %r: stage name not found in pipeline (valid names: %s).",
                    resume_from,
                    ", ".join(s.name for s in self.pipeline.stages),
                )
                return EXIT_CONFIG_ERROR
            # Mark anything before the resume point that's already
            # ``completed`` on disk as kept-as-is.
            for prior_state in state.stages[:resume_idx]:
                if (
                    prior_state.status == "completed"
                    and prior_state.output_model
                    and os.path.isdir(prior_state.output_model)
                ):
                    stages_to_skip_completed.append(prior_state.name)
                    logger.info(
                        "Resuming: stage %r already completed at %s; skipping.",
                        prior_state.name,
                        prior_state.output_model,
                    )

        if stage_filter is not None and not any(s.name == stage_filter for s in self.pipeline.stages):
            logger.error(
                "Cannot --stage %r: stage name not found in pipeline (valid names: %s).",
                stage_filter,
                ", ".join(s.name for s in self.pipeline.stages),
            )
            return EXIT_CONFIG_ERROR

        # 2a. ``--stage <name>`` on a non-first stage requires the previous
        # stage's output to already exist on disk (auto-chain resolution),
        # unless ``--input-model`` provides an explicit override.  Refuse
        # to silently fall back to the root ``model.name_or_path`` — that
        # would produce a chain whose stage N is trained on the root base
        # model, not on the previous stage's output, contradicting every
        # operator's expectation of what ``--stage dpo_stage`` means.
        prev_output_for_filter: Optional[str] = None
        if stage_filter is not None and input_model_override is None:
            filter_idx = next(i for i, s in enumerate(self.pipeline.stages) if s.name == stage_filter)
            if filter_idx > 0:
                prev_stage = self.pipeline.stages[filter_idx - 1]
                # Project the previous stage's would-be output path by
                # running it through the merge helper with no chain (so
                # we get its declared ``training.output_dir`` honestly).
                prev_merged = merge_pipeline_stage_config(self.root_cfg, prev_stage, prev_output_model=None)
                candidate = os.path.join(prev_merged.training.output_dir, "final_model")
                if not os.path.isdir(candidate):
                    logger.error(
                        "Stage %r requires the previous stage's output at %s; "
                        "pass --input-model <path> to override or run the full "
                        "pipeline first.",
                        stage_filter,
                        candidate,
                    )
                    return EXIT_CONFIG_ERROR
                prev_output_for_filter = candidate

        # 3. Emit pipeline.started + webhook (only on a fresh run).
        if resume_from is None:
            self._audit_event(
                "pipeline.started",
                pipeline_run_id=state.pipeline_run_id,
                config_hash=self.config_hash,
                stage_count=len(self.pipeline.stages),
                stage_names=[s.name for s in self.pipeline.stages],
            )
            self._notify_pipeline("started", state)

        # 4. Iterate stages.
        worst_exit: int = EXIT_SUCCESS
        # When ``--stage X`` is set on a non-first stage, seed ``prev_output``
        # with the previous stage's on-disk output path resolved above so the
        # filtered stage auto-chains correctly.  In every other mode, the
        # initial ``prev_output`` is None and the iteration accumulates it
        # naturally from each completed stage.
        prev_output: Optional[str] = prev_output_for_filter
        chain_broken: bool = False  # set when a stage auto-reverts; later stages skip
        for i, stage in enumerate(self.pipeline.stages):
            stage_state = state.stages[i]

            # --stage filter: only run the named stage; mark others skipped_by_filter.
            if stage_filter is not None and stage.name != stage_filter:
                stage_state.status = "skipped_by_filter"
                stage_state.skipped_reason = f"--stage {stage_filter!r} was specified; only that stage runs."
                self._save_state(state)
                continue

            # --resume-from: skip already-completed stages with on-disk output.
            if stage.name in stages_to_skip_completed:
                prev_output = stage_state.output_model
                continue

            # Chain-broken (prior stage reverted): mark remaining as skipped_due_to_prior_revert.
            if chain_broken:
                stage_state.status = "skipped_due_to_prior_revert"
                stage_state.skipped_reason = (
                    f"Stage {state.stopped_at!r} triggered auto_revert; downstream stages did not run."
                )
                self._save_state(state)
                continue

            # Run this stage.
            stage_state.index = i
            stage_state.name = stage.name
            stage_state.trainer_type = (
                stage.training.trainer_type if stage.training else self.root_cfg.training.trainer_type
            )
            stage_state.started_at = _utc_iso_now()
            stage_state.status = "running"
            self._save_state(state)

            # Resolve the input-model override only for the filtered stage
            # (a CLI ``--input-model`` flag attaches to a single stage run).
            override_for_this_stage = (
                input_model_override if (stage_filter is not None and stage.name == stage_filter) else None
            )

            exit_code = self._run_single_stage(
                stage=stage,
                stage_state=stage_state,
                prev_output=prev_output,
                input_model_override=override_for_this_stage,
                state=state,
            )
            stage_state.exit_code = exit_code
            stage_state.finished_at = _utc_iso_now()

            # Duration calc — wrap in try/except to be robust against
            # missing started_at on a constructor edge case.
            try:
                start_dt = datetime.fromisoformat(stage_state.started_at)
                end_dt = datetime.fromisoformat(stage_state.finished_at)
                stage_state.duration_seconds = (end_dt - start_dt).total_seconds()
            except (TypeError, ValueError):
                stage_state.duration_seconds = None

            # Decide where the pipeline goes next, given this stage's outcome.
            if exit_code == EXIT_AWAITING_APPROVAL:
                # Human-approval gate fired.  Pipeline exits; remaining
                # stages stay ``pending`` so a subsequent ``--resume-from``
                # picks them up after operator action.
                stage_state.status = "gated_pending_approval"
                state.final_status = "gated_pending_approval"
                state.stopped_at = stage.name
                state.finished_at = _utc_iso_now()
                worst_exit = max(worst_exit, EXIT_AWAITING_APPROVAL)
                self._save_state(state)
                # Phase 14 review F-N-1: dedicated ``pipeline.stage_gated``
                # event (instead of ``pipeline.stage_completed`` with a
                # ``gate_decision=approval_pending`` sub-field).  Lets
                # dashboard / SIEM rules filter on the event name alone
                # without parsing payload sub-fields — "stage_completed"
                # reads as "stage finished cleanly" to a regex-based
                # alert rule.
                self._audit_event(
                    "pipeline.stage_gated",
                    pipeline_run_id=state.pipeline_run_id,
                    stage_name=stage.name,
                    gate_decision="approval_pending",
                    staging_path=stage_state.output_model,
                )
                # No pipeline.completed event yet — pipeline is not done.
                break

            if exit_code == EXIT_SUCCESS:
                stage_state.status = "completed"
                stage_state.gate_decision = "passed"
                self._save_state(state)
                self._audit_event(
                    "pipeline.stage_completed",
                    pipeline_run_id=state.pipeline_run_id,
                    stage_name=stage.name,
                    gate_decision="passed",
                    metrics=stage_state.metrics,
                )
                prev_output = stage_state.output_model
                continue

            # Anything else (EXIT_TRAINING_ERROR / EXIT_EVAL_FAILURE):
            # the chain stops here.  Subsequent stages skip with
            # ``skipped_due_to_prior_revert`` (the canonical reason
            # name regardless of whether the failure was a trainer
            # crash or a gate failure — both are "stage N failed,
            # downstream stages did not run").
            stage_state.status = "failed"
            stage_state.gate_decision = "failed"
            chain_broken = True
            state.stopped_at = stage.name
            worst_exit = max(worst_exit, exit_code)
            self._save_state(state)
            self._audit_event(
                "pipeline.stage_reverted" if stage_state.auto_revert_triggered else "pipeline.stage_completed",
                pipeline_run_id=state.pipeline_run_id,
                stage_name=stage.name,
                gate_decision="failed",
                auto_revert_triggered=stage_state.auto_revert_triggered,
            )
            self._notify_pipeline(
                "reverted" if stage_state.auto_revert_triggered else "stage_failed", state, stage_state=stage_state
            )

        # 5. Final state + manifest + pipeline.completed event.
        if state.final_status == "in_progress":
            if worst_exit == EXIT_SUCCESS:
                state.final_status = "completed"
            else:
                state.final_status = "stopped_at_stage"
            state.finished_at = _utc_iso_now()
        self._save_state(state)

        if state.final_status in ("completed", "stopped_at_stage"):
            self._audit_event(
                "pipeline.completed",
                pipeline_run_id=state.pipeline_run_id,
                final_status=state.final_status,
                stopped_at=state.stopped_at,
            )
            self._notify_pipeline("completed", state)

        # 6. Emit human-readable / JSON envelope summary.
        self._emit_summary(state)

        return worst_exit

    def dry_run(self) -> int:
        """Validate every stage without allocating any GPU resources.

        Collects all per-stage Pydantic / merge errors before exiting,
        mirroring ``pytest --collectonly``.  Returns
        :data:`EXIT_CONFIG_ERROR (1)` if any stage fails validation,
        :data:`EXIT_SUCCESS (0)` otherwise.
        """
        errors: List[str] = []
        prev_output: Optional[str] = None
        for stage in self.pipeline.stages:
            try:
                merged = merge_pipeline_stage_config(
                    self.root_cfg,
                    stage,
                    prev_output_model=prev_output,
                )
            except Exception as exc:  # noqa: BLE001 — best-effort: collect every per-stage validation error for a single operator report instead of stopping at the first.
                errors.append(f"Stage {stage.name!r}: merge failed: {exc}")
                continue

            # Project the output path the next stage would auto-chain to.
            prev_output = os.path.join(merged.training.output_dir, "final_model")

        if errors:
            logger.error("Pipeline dry-run found %d stage error(s):", len(errors))
            for e in errors:
                logger.error("  %s", e)
            return EXIT_CONFIG_ERROR

        logger.info(
            "Pipeline dry-run OK: %d stage(s) validated; no GPU was allocated.",
            len(self.pipeline.stages),
        )
        return EXIT_SUCCESS

    # -- internals ------------------------------------------------------------

    def _init_state(self) -> PipelineState:
        """Build a fresh :class:`PipelineState` from the parsed pipeline."""
        from .._version import __version__

        stages = [
            PipelineStageState(
                name=s.name,
                index=i,
                trainer_type=(s.training.trainer_type if s.training else self.root_cfg.training.trainer_type),
            )
            for i, s in enumerate(self.pipeline.stages)
        ]
        return PipelineState(
            pipeline_run_id=_generate_run_id(),
            pipeline_config_hash=self.config_hash,
            forgelm_version=__version__,
            started_at=_utc_iso_now(),
            stages=stages,
        )

    def _validate_resume_state(self, existing: PipelineState, *, force: bool) -> Optional[str]:
        """Stale-state guard for ``--resume-from``.

        If the on-disk state file's ``pipeline_config_hash`` differs from
        the current parse of the pipeline YAML, the operator edited the
        file between the failed run and the resume call — resuming
        against a different config silently produces a chain whose
        history doesn't match its current shape.  We refuse unless
        ``--force-resume`` is set (logged at WARNING **and** emitted as a
        ``pipeline.force_resume`` audit event so reviewers see why the
        divergence was accepted).

        Return semantics:

        - ``None`` — the resume is OK to proceed (no hash divergence, or
          divergence accepted via ``--force-resume``).
        - error-string — the resume must abort; the caller maps this to
          ``EXIT_CONFIG_ERROR``.  Using a return value (rather than
          ``sys.exit`` mid-method) keeps the orchestrator's exit policy
          consistent with the rest of ``run()`` — every refusal flows
          back through the same ``return`` branch, the same audit-log
          finalisation runs, and the test surface uses a uniform
          ``assert code == EXIT_CONFIG_ERROR`` shape.
        """
        if existing.pipeline_config_hash == self.config_hash:
            return None
        if not force:
            msg = (
                f"Refusing to --resume-from: pipeline_config_hash mismatch.\n"
                f"  on-disk: {existing.pipeline_config_hash}\n"
                f"  current: {self.config_hash}\n"
                "Pass --force-resume to override (logged for audit)."
            )
            logger.error(msg)
            return msg
        old_hash = existing.pipeline_config_hash
        logger.warning(
            "Resuming with --force-resume despite pipeline_config_hash mismatch: %s → %s.",
            old_hash,
            self.config_hash,
        )
        # Append-only audit event so a reviewer reading the JSONL stream
        # later can distinguish an operator-approved stale-config resume
        # from a normal resume.  Emitted BEFORE the stored hash is
        # updated so the event payload still records both sides of the
        # divergence.
        self._audit_event(
            "pipeline.force_resume",
            pipeline_run_id=existing.pipeline_run_id,
            old_config_hash=old_hash,
            new_config_hash=self.config_hash,
        )
        # Update the stored hash to match the now-trusted current config
        # so subsequent transitions don't trip the guard again.
        existing.pipeline_config_hash = self.config_hash
        return None

    def _load_state_file(self) -> Optional[PipelineState]:
        path = self.paths["state_file"]
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to read pipeline_state.json at %s: %s.  Treating as missing.", path, e)
            return None
        # Phase 14 review F-R1-S4: a tampered state file (wrong shape,
        # missing required keys, ``stages`` not a list of dicts, etc.)
        # could crash ``_deserialise_state`` with an opaque
        # ``TypeError`` / ``KeyError`` traceback instead of producing
        # an actionable config-error path.  Catch the common shape
        # failures here and treat the file as missing — the caller's
        # ``--resume-from`` branch then surfaces ``EXIT_CONFIG_ERROR``
        # with a clear message.
        try:
            return _deserialise_state(payload)
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(
                "pipeline_state.json at %s is structurally invalid (%s); treating as missing.",
                path,
                e,
            )
            return None

    def _save_state(self, state: PipelineState) -> None:
        """Persist state file + refresh pipeline manifest.

        Both writes are atomic.  Manifest export is delegated to
        :mod:`forgelm.compliance` so the schema lives in one place.
        """
        _atomic_write_json(self.paths["state_file"], _serialise_state(state))
        # Lazy import — compliance has its own heavy deps for the
        # Annex-IV verifier path; only needed when we actually export.
        from ..compliance import generate_pipeline_manifest

        manifest = generate_pipeline_manifest(state=state, root_cfg=self.root_cfg)
        _atomic_write_json(self.paths["manifest_file"], manifest)

    def _audit_event(self, event: str, **fields: Any) -> None:
        """Append-only audit log entry under the **pipeline** root output dir.

        Two separate audit-log streams exist on a multi-stage run:

        - **Pipeline-level** (this method): ``<pipeline.output_dir>/
          audit_log.jsonl`` — carries ``pipeline.*`` lifecycle events
          (started / stage_started / stage_completed / stage_gated /
          stage_reverted / force_resume / completed).
        - **Stage-level** (emitted by each ``ForgeTrainer``):
          ``<stage.training.output_dir>/audit_log.jsonl`` — carries the
          existing ``training.*`` vocabulary unchanged from a single-
          stage v0.6.0 run.

        Both files are append-only JSONL.  Reviewers can correlate by
        joining on ``pipeline_run_id`` (present in every pipeline event)
        with the per-stage ``training_manifest.json`` ``training_run_id``.
        See ``docs/guides/pipeline.md`` "Audit events" for the full
        join key matrix.
        """
        try:
            from ..compliance import AuditLogger

            audit = AuditLogger(self.paths["root_output_dir"])
            audit.log_event(event, **fields)
        except Exception as exc:  # noqa: BLE001 — audit emission is best-effort telemetry; a write failure must not abort the pipeline.
            logger.warning("Failed to emit audit event %r: %s", event, exc)

    def _notify_pipeline(
        self,
        kind: Literal["started", "completed", "reverted", "stage_failed"],
        state: PipelineState,
        *,
        stage_state: Optional[PipelineStageState] = None,
    ) -> None:
        """Webhook fan-out for pipeline lifecycle transitions.

        Notifier methods are optional (added in Phase 14, defended via
        ``getattr`` so a fork that pinned an older webhook module
        doesn't crash here).
        """
        try:
            from ..webhook import WebhookNotifier

            notifier = WebhookNotifier(self.root_cfg)
            stage_count = len(self.pipeline.stages)
            if kind == "started":
                method = getattr(notifier, "notify_pipeline_started", None)
                if method:
                    method(run_id=state.pipeline_run_id, stage_count=stage_count)
            elif kind == "completed":
                method = getattr(notifier, "notify_pipeline_completed", None)
                if method:
                    method(run_id=state.pipeline_run_id, final_status=state.final_status, stopped_at=state.stopped_at)
            elif kind == "reverted":
                method = getattr(notifier, "notify_pipeline_reverted", None)
                if method and stage_state is not None:
                    method(
                        run_id=state.pipeline_run_id,
                        stage_name=stage_state.name,
                        reason=stage_state.error or "auto_revert",
                    )
            # ``stage_failed`` is currently only an audit event — no
            # dedicated webhook method.  Existing per-stage
            # ``training.failure`` from ForgeTrainer's notifier covers
            # the operator surface; the pipeline-level event would be
            # redundant noise on Slack.
        except Exception as exc:  # noqa: BLE001 — best-effort notification; webhook outage must not derail the pipeline.
            logger.warning("Failed to emit pipeline webhook %r: %s", kind, exc)

    def _run_single_stage(
        self,
        *,
        stage: PipelineStage,
        stage_state: PipelineStageState,
        prev_output: Optional[str],
        input_model_override: Optional[str],
        state: PipelineState,
    ) -> int:
        """Materialise the per-stage ForgeConfig, run the trainer, record results.

        Returns the per-stage exit code; the caller decides what to do
        with it (continue, halt, gate).
        """
        # Resolve input source for audit clarity.
        if input_model_override is not None:
            stage_state.input_source = "cli_override"
        elif stage.model is not None:
            stage_state.input_source = "stage_explicit"
        elif prev_output is not None:
            stage_state.input_source = "chain"
        else:
            stage_state.input_source = "root"

        # Merge config (any merge-time validation failure surfaces here).
        try:
            stage_cfg = merge_pipeline_stage_config(
                self.root_cfg,
                stage,
                prev_output_model=prev_output,
                input_model_override=input_model_override,
            )
        except Exception as exc:  # noqa: BLE001 — config-merge failure is a fatal stage error; routes through the standard config-error exit code.
            stage_state.error = f"Config merge failed: {exc}"
            logger.error("Stage %r config merge failed: %s", stage.name, exc)
            return EXIT_CONFIG_ERROR

        stage_state.input_model = stage_cfg.model.name_or_path

        # ``forgelm`` chain-presence guard: when the orchestrator
        # auto-chained the input model from the previous stage's output,
        # refuse to proceed unless that exact directory exists.  Phase
        # 14 review F-S-1: pre-fix this checked ``os.path.dirname(...)``
        # (the parent), accepting ``./stage1/`` even when ``./stage1/
        # final_model`` was missing and letting a bad chain state fall
        # through into ``get_model_and_tokenizer`` for a non-actionable
        # downstream crash.
        if stage_state.input_source == "chain":
            if not os.path.isdir(stage_cfg.model.name_or_path):
                stage_state.error = (
                    f"Stage {stage.name!r} requires the previous stage's output at "
                    f"{stage_cfg.model.name_or_path}; pass --input-model <path> to "
                    f"override or run the full pipeline first."
                )
                logger.error(stage_state.error)
                return EXIT_CONFIG_ERROR

        self._audit_event(
            "pipeline.stage_started",
            pipeline_run_id=state.pipeline_run_id,
            stage_name=stage.name,
            stage_index=stage_state.index,
            input_model=stage_state.input_model,
            input_source=stage_state.input_source,
        )

        # Defer heavy imports so dry-run / --stage on a different stage
        # doesn't load torch.
        try:
            from ..data import prepare_dataset
            from ..model import get_model_and_tokenizer
            from ..trainer import ForgeTrainer
            from ..utils import setup_authentication
        except ImportError as e:
            stage_state.error = f"Missing training dependency: {e}"
            logger.error(stage_state.error)
            return EXIT_TRAINING_ERROR

        try:
            if not stage_cfg.model.offline:
                setup_authentication(stage_cfg.auth.hf_token if stage_cfg.auth else None)

            model, tokenizer = get_model_and_tokenizer(stage_cfg)
            dataset = prepare_dataset(stage_cfg, tokenizer)
            trainer = ForgeTrainer(model=model, tokenizer=tokenizer, config=stage_cfg, dataset=dataset)
            result = trainer.train()
        except Exception as exc:  # noqa: BLE001 — top-of-stage catch.  ForgeTrainer.train() crosses every concern (HF load, dataset, TRL, safety, judge, audit, compliance, webhook); any uncaught exception must surface as a per-stage failure rather than a Python traceback that strands the pipeline state.
            stage_state.error = f"Trainer crashed: {exc}"
            logger.exception("Stage %r trainer crashed.", stage.name)
            return EXIT_TRAINING_ERROR

        # Capture results onto the stage state.
        stage_state.metrics = {k: float(v) for k, v in (result.metrics or {}).items() if isinstance(v, (int, float))}
        stage_state.auto_revert_triggered = bool(result.reverted)
        stage_state.training_manifest = os.path.join(
            stage_cfg.training.output_dir, "compliance", "training_manifest.json"
        )

        # Human-approval gate produces a non-zero exit + a staging_path.
        if result.staging_path:
            stage_state.output_model = result.staging_path
            return EXIT_AWAITING_APPROVAL

        # Auto-revert or gate failure: trainer returns success=False.
        if not result.success:
            stage_state.error = result.error or "Stage gate failed."
            return EXIT_EVAL_FAILURE

        # Normal success path.
        stage_state.output_model = result.final_model_path or os.path.join(stage_cfg.training.output_dir, "final_model")
        return EXIT_SUCCESS

    # -- summary --------------------------------------------------------------

    def _emit_summary(self, state: PipelineState) -> None:
        """Operator-facing run summary (text or JSON envelope)."""
        if self.output_format == "json":
            print(json.dumps(_serialise_state(state), indent=2))
            return

        logger.info("Pipeline %s — final_status=%s", state.pipeline_run_id, state.final_status)
        for s in state.stages:
            logger.info(
                "  [%s] %s — trainer=%s, exit=%s, output=%s",
                s.status,
                s.name,
                s.trainer_type,
                s.exit_code if s.exit_code is not None else "—",
                s.output_model or "—",
            )


# ---------------------------------------------------------------------------
# Entry point (CLI dispatcher delegates here)
# ---------------------------------------------------------------------------


def run_pipeline_from_args(
    root_cfg: ForgeConfig,
    pipeline_yaml_bytes: bytes,
    args: Any,
) -> int:
    """Dispatcher entry — orchestrates flag → orchestrator wiring.

    ``args`` is the parsed ``argparse.Namespace`` from the CLI; only the
    pipeline-relevant attributes are read.  Keeping this glue thin makes
    the orchestrator itself trivial to unit-test against a fake args
    namespace.
    """
    stage_filter = getattr(args, "stage", None)
    resume_from = getattr(args, "resume_from", None)
    force_resume = bool(getattr(args, "force_resume", False))
    # Phase 14 review F-F-2: argparse cannot reject an empty string
    # value for ``--input-model "" --stage X`` at parse time, and the
    # downstream merge helper uses ``is not None`` rather than a truthy
    # check, so the empty string would silently overwrite the auto-
    # chained model path.  Normalise to ``None`` here so the rest of the
    # orchestrator sees "no override" rather than "override with nothing".
    raw_input_model = getattr(args, "input_model", None)
    input_model_override = raw_input_model if raw_input_model else None
    output_format = getattr(args, "output_format", "text")
    dry_run = bool(getattr(args, "dry_run", False))

    if stage_filter and resume_from:
        logger.error("`--stage` and `--resume-from` are mutually exclusive.")
        return EXIT_CONFIG_ERROR
    if input_model_override and not stage_filter:
        logger.error("`--input-model` requires `--stage <name>`.")
        return EXIT_CONFIG_ERROR

    orchestrator = PipelineOrchestrator(
        root_cfg=root_cfg,
        pipeline_yaml_bytes=pipeline_yaml_bytes,
        output_format=output_format,
    )

    if dry_run:
        return orchestrator.dry_run()
    return orchestrator.run(
        stage_filter=stage_filter,
        resume_from=resume_from,
        force_resume=force_resume,
        input_model_override=input_model_override,
    )

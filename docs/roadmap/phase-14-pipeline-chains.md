# Phase 14: Multi-Stage Training Pipeline Chains

> **Status:** Implementation complete on `development` (branch `feat/phase-14-pipeline-chains`).  Awaiting `v0.7.0` PyPI tag for the final "Done" promotion to [completed-phases.md](completed-phases.md).  Originally targeted for `v0.6.0`; Phase 15 displaced it after the 2026-05-11 ingestion pilot — see [completed-phases.md#phase-15-ingestion-pipeline-reliability-v060](completed-phases.md#phase-15-ingestion-pipeline-reliability-v060).
>
> **Note:** This file details a single planned phase.  See [../roadmap.md](../roadmap.md) for the cross-phase summary.

**Goal:** Enable a single config file to define a sequential SFT → DPO → GRPO training pipeline, with each stage using the previous stage's output as its base model.  Eliminate the current requirement for manual config management across stages while preserving the existing single-stage workflow byte-identically.

**Estimated Effort:** Medium (4-6 weeks for Wave 1, including ~1 review-absorption round).  The "3-week minimum" optimistic floor in earlier drafts was retired because the per-stage state machine (Task 5) and the inheritance-merge semantics (Task 2) both have non-obvious edge cases that surface during reviewer absorption, mirroring the Phase 15 cycle (5 absorption rounds for a comparable surface area).

**Priority:** Medium-High — frequently requested by enterprise users since the v0.5.0 launch (preference / RL alignment workflows are the post-SFT default for regulated customers); low *core* implementation risk because every individual trainer already works.  The risk surface is in **orchestration semantics**, not trainer mechanics: inheritance merge, partial-run resume, and per-stage gate composition.

> **Context:** Enterprise ML teams running production post-training pipelines currently write 3+ separate config files, manually set `model.name_or_path` to each stage's output, copy LoRA / safety / compliance config blocks between them, and orchestrate execution themselves with shell scripts.  Every manual copy is an opportunity to drift — a LoRA `r` value that matches across stages by accident becomes one that mismatches after the next config edit.  A `pipeline:` config key that chains stages solves the orchestration *and* the drift problem in one move, while remaining fully config-driven, dry-run-validatable, and Annex-IV-traceable.

## Tasks

1. [ ] **`pipeline:` config section in `ForgeConfig`**
   New optional `pipeline.stages: List[PipelineStage]` section.  Each stage is a partial training config override layered onto the root config (see Task 2 for the merge semantics).  Stages execute sequentially; each stage's `model.name_or_path` is automatically set to the previous stage's `training.output_dir/final_model` (or, if the previous stage gated on human approval, to the staging path after approval).  Stage names must be unique within a pipeline and match `^[a-z0-9_]{1,32}$` so they can serve as identifiers in CLI flags (`--stage <name>`, `--resume-from <name>`) and audit-log fields without escaping.

   ```yaml
   pipeline:
     stages:
       - name: sft_stage
         training:
           trainer_type: "sft"
           output_dir: "./checkpoints/stage1_sft"
           num_train_epochs: 3
         data:
           dataset_name_or_path: "./data/sft_data.jsonl"

       - name: dpo_stage
         training:
           trainer_type: "dpo"
           output_dir: "./checkpoints/stage2_dpo"
           num_train_epochs: 1
         data:
           dataset_name_or_path: "./data/preferences.jsonl"

       - name: grpo_stage
         training:
           trainer_type: "grpo"
           output_dir: "./checkpoints/stage3_grpo"
         data:
           dataset_name_or_path: "./data/math_prompts.jsonl"
   ```

   **Acceptance:**
   - `ForgeConfig(**yaml_load(pipeline.yaml)).pipeline` is a typed `PipelineConfig` with a non-empty `stages` list and a unique-name validator (`pydantic.field_validator` raising `ValueError` on duplicate names).
   - Stage name pattern enforced at config load (`^[a-z0-9_]{1,32}$`); invalid name → `EXIT_CONFIG_ERROR (1)` with an actionable message naming the offending stage.
   - Empty `pipeline.stages: []` → rejected at load (a pipeline must have ≥ 1 stage; the operator who meant single-stage should not use the `pipeline:` key at all).
   - Backward compatibility: a config file without a `pipeline:` key produces `config.pipeline is None`; all existing CLI paths see no behavioural change.

2. [ ] **Stage inheritance and override semantics**
   Each stage inherits the top-level config as defaults; only fields the stage *explicitly sets* are overridden.  Detection of "explicitly set" uses Pydantic's `model_fields_set` (not "field happens to equal default") so a stage that writes `learning_rate: 2e-5` — the same as the root default — still flags as overridden and the trainer sees the stage's value.  This matters when reviewers expect "the YAML says it, so the YAML's value wins" symmetry.

   **Merge depth:** the merge is **section-wholesale**, *not* recursive-deep-merge.  If a stage declares `lora:`, the entire `lora` block replaces the root `lora` block — partial-override on a nested key is rejected at config load.  This is a deliberate trade-off: deep-merge nuances (`target_modules: [...]` append vs. replace?) compound across the 19 ForgeConfig submodels and turn config validation into an undebuggable maze.  Wholesale replacement gives one clear rule: "if you want to inherit, omit the block; if you want to override, supply the *full* block."

   **Inheritance matrix** (per top-level config section):

   | Section | Inheritance | Notes |
   |---|---|---|
   | `model.name_or_path` | **Auto-chained** (overrides root after stage 0) | Set to previous stage's `training.output_dir/final_model`.  Stage 0 still reads root `model.name_or_path`.  An explicit per-stage `model.name_or_path` is allowed and disables auto-chaining for that stage (operator escape hatch). |
   | `model.*` (other fields) | Inherited unless `model:` block overridden | `backend`, `load_in_4bit`, `trust_remote_code`, `max_length`, `chat_template` follow the root unless the stage supplies a full `model:` block. |
   | `lora` | Inherited unless `lora:` block overridden | Critical edge case: stage 2 DPO with a *different* `lora.r` than stage 1 SFT means stage 2 is **a fresh LoRA over the merged SFT model**, not a continuation of SFT's LoRA.  Documented in the operator guide. |
   | `data` | Inherited unless `data:` block overridden (strongly discouraged) | Pipelines that don't change the dataset between stages are vanishingly rare — almost every real chain has SFT use a curated SFT dataset, DPO use a preference pairs dataset, and GRPO use a math/reward dataset.  The schema does not *force* a per-stage override (operators may legitimately rerun the same dataset against a different trainer for ablation studies), but the operator guide flags the inheritance case as a smell and the dry-run summary prints a warning when two consecutive stages share the same `dataset_name_or_path`. |
   | `training` | Inherited unless `training:` block overridden | `trainer_type` is required per stage; the validator rejects a stage with no `training.trainer_type` even if the root supplies one (each stage explicitly states its alignment paradigm for audit clarity). |
   | `evaluation` | Inherited unless `evaluation:` block overridden | Per-stage gates (Task 5) live here; a stage that wants different `auto_revert` / `safety` config supplies a full `evaluation:` block. |
   | `distributed` | Inherited (always); no per-stage override | Distributed strategy must be consistent across the pipeline run.  Per-stage `distributed:` blocks rejected at load with a clear error. |
   | `webhook` | Inherited (always); no per-stage override | One webhook configuration covers the pipeline; per-stage events carry the stage name in the payload. |
   | `compliance` | Inherited (always); no per-stage override | Provider / system / risk metadata is pipeline-level, not stage-level. |
   | `synthetic`, `merge` | Stage-local only; rejected at the root level when `pipeline:` is set | These flags describe non-training modes — using them inside a pipeline stage is the wrong layer of abstraction (synthesise-then-train should be two separate operator invocations). |

   **Acceptance:**
   - `forgelm/config.py` exports `PipelineStage(BaseModel)` and `PipelineConfig(BaseModel)` Pydantic models with field-level validators implementing the matrix above.
   - The merge happens in a single helper `_merge_stage_into_root(root_cfg, stage) -> ForgeConfig`; the rest of the codebase consumes a flat `ForgeConfig` per stage with no awareness of the pipeline layer.  This keeps `forgelm/trainer.py` unmodified.
   - Per-stage `distributed:` block → `EXIT_CONFIG_ERROR (1)` with message `"distributed:" cannot appear in pipeline stage <name>; declare it at the root.`
   - Per-stage `model.name_or_path` is honoured and disables auto-chaining for that stage (logged at INFO).
   - Test fixture matrix covers: `inherited`, `overridden`, `auto-chained`, `rejected-per-stage` for each of the 11 rows above (44 test cases total).

3. [ ] **Pipeline compliance manifest**
   New artefact `compliance/pipeline_manifest.json` (JSON, not YAML — matches the existing `training_manifest.json` format the auditors are already trained on) captures the full multi-stage provenance.  **Per-stage `training_manifest.json` files are still emitted** inside each stage's `output_dir/compliance/` directory; the pipeline manifest is an *index* that ties them together, not a replacement.  Satisfies EU AI Act Annex IV's "complete training lineage" requirement at the chain level.

   **Schema (illustrative):**

   ```json
   {
     "forgelm_version": "0.7.0",
     "generated_at": "2026-06-15T12:34:56+00:00",
     "pipeline_run_id": "pl_2026-06-15_a1b2c3",
     "pipeline_config_hash": "sha256:<hash-of-the-pipeline-yaml-bytes>",
     "stages": [
       {
         "name": "sft_stage",
         "index": 0,
         "trainer_type": "sft",
         "status": "completed",
         "input_model": "meta-llama/Llama-3-8B",
         "output_model": "./checkpoints/stage1_sft/final_model",
         "started_at": "2026-06-15T12:34:56+00:00",
         "finished_at": "2026-06-15T14:21:08+00:00",
         "duration_seconds": 6372,
         "training_manifest": "./checkpoints/stage1_sft/compliance/training_manifest.json",
         "metrics": { "eval_loss": 0.42 },
         "gate_decision": "passed",
         "auto_revert_triggered": false
       },
       {
         "name": "dpo_stage",
         "index": 1,
         "trainer_type": "dpo",
         "status": "skipped_due_to_prior_revert",
         "input_model": "./checkpoints/stage1_sft/final_model",
         "output_model": null,
         "training_manifest": null,
         "skipped_reason": "Stage sft_stage triggered auto_revert; subsequent stages did not run."
       }
     ],
     "final_status": "stopped_at_stage",
     "stopped_at": "sft_stage",
     "annex_iv": { "<provider/system/risk metadata copied from root config>": "..." }
   }
   ```

   Stage `status` enum: `pending` | `running` | `completed` | `failed` | `gated_pending_approval` | `skipped_due_to_prior_revert` | `skipped_by_filter` (when `--stage X` runs only one stage).

   **Annex IV mapping:** the pipeline manifest discharges the same Article 11 / Annex IV obligations as the single-stage manifest, with two additions: (a) the **training lineage** is a chain rather than a single record, (b) the `pipeline_config_hash` proves the chain's *intent* is reproducible (the same config bytes always describe the same chain).  Existing `forgelm verify-annex-iv` validator gains a `--pipeline` mode that follows the index, validates each per-stage manifest, and asserts chain integrity (stage N's `input_model` must equal stage N-1's `output_model`).

   **Acceptance:**
   - `forgelm/compliance.py` exports `generate_pipeline_manifest(pipeline_state) -> Dict[str, Any]` and `export_pipeline_manifest(manifest, output_dir) -> str`.  The orchestrator writes the manifest after every stage state transition (atomic-rename pattern, matching the existing `_atomic_write_json` helper).
   - The manifest is **append-friendly under partial runs**: a `--stage sft_stage` invocation produces a 1-stage manifest with the other two stages as `status: skipped_by_filter`; a subsequent full run replaces the manifest atomically with a complete 3-stage version.
   - `forgelm verify-annex-iv --pipeline <run_dir>` returns exit 0 on a complete passing run, exits non-zero with a `chain_integrity_violation` reason when stage N's input doesn't match stage N-1's output.
   - The per-stage `training_manifest.json` files remain individually valid against the existing single-stage Annex IV schema — no field is renamed or removed at the stage level.

4. [ ] **CLI surface**

   ```bash
   # End-to-end pipeline run
   forgelm --config pipeline.yaml

   # Dry-run validates every stage (Pydantic + cross-stage chain integrity) before any GPU is allocated
   forgelm --config pipeline.yaml --dry-run

   # Run a single named stage in isolation (audit / re-run scenarios)
   forgelm --config pipeline.yaml --stage dpo_stage

   # Resume after a failed / interrupted run from a named stage onward
   forgelm --config pipeline.yaml --resume-from dpo_stage
   ```

   **`--dry-run` failure-collection mode.**  Each stage is validated independently; the dispatcher **collects all stage-level errors before exiting** rather than stopping at the first failure.  Mirrors `pytest --collectonly` and avoids the "fix one config bug, re-run, fix the next" loop that drives operators away.  Exit `EXIT_CONFIG_ERROR (1)` if any stage fails validation; the error report names every offending stage + field.  Chain-integrity validation (each stage's auto-chained `input_model` must point at a path under the previous stage's `output_dir`) runs *after* per-stage Pydantic validation passes.

   **`--stage <name>` semantics (partial-run resolution rules):**

   | Scenario | Behaviour |
   |---|---|
   | `--stage <name>` and `<name>` is the first stage | Reads root `model.name_or_path`; runs normally. |
   | `--stage <name>` and the previous stage's `output_dir/final_model` exists on disk | Auto-chains as if previous stage had just finished; INFO-logs the disk path being reused. |
   | `--stage <name>` and the previous stage's output is missing | Hard-fails with `EXIT_CONFIG_ERROR (1)`: `Stage <name> requires <prev_stage> output at <path>; pass --input-model <path> to override or run the full pipeline first.`  No silent fallback to root `model.name_or_path`. |
   | `--stage <name> --input-model <path>` | Operator escape hatch: skips the auto-chain, uses `<path>` as the stage's base model.  The audit-log event records `input_source: "cli_override"` so reviewers can trace why the chain "broke" intentionally. |
   | `--stage <name>` where `<name>` is not in the config | Hard-fails at parse time with the list of valid stage names. |

   **`--resume-from <name>` semantics (state machine + persistence):**
   - State file: `<root_output_dir>/pipeline_state.json` (atomic-write, JSON, schema mirrors the pipeline manifest's `stages[].status` enum).  Updated after every stage transition.
   - Resume rule: stages with `status: completed` and a `output_model` path that still exists on disk are **skipped** (logged at INFO) and their manifests are preserved.  The named stage and every stage after it are re-run.
   - Stale-state guard: if the on-disk `pipeline_state.json` was produced by a different `pipeline_config_hash` than the one being resumed against, the resume fails with `EXIT_CONFIG_ERROR (1)` — preventing "I resumed against a config that was edited mid-flight" silent divergence.  Override via `--force-resume` (logged at WARNING, recorded in the audit event).
   - Resume does **not** support intra-stage checkpoint resume in Phase 14.  HF `Trainer.train(resume_from_checkpoint=...)` integration is deferred to a Phase 14.x follow-up; Phase 14 only resumes at stage boundaries.

   **`--output-format json` envelope:**  pipeline runs emit a top-level JSON object with `pipeline_run_id`, `stages[]` (each with `status`, `started_at`, `finished_at`, per-stage exit code), and `final_status`.  Single-stage existing envelope unchanged.

   **Acceptance:**
   - `forgelm --config pipeline.yaml --dry-run` validates every stage and prints a per-stage diagnostic block; exits 0 on full success or 1 with the collected error report on any failure.
   - `forgelm --config pipeline.yaml --stage <name>` with a missing previous-stage output exits 1 with the message shape above (regression test asserts the exact message format so operators can grep for it in CI logs).
   - `forgelm --config pipeline.yaml --resume-from <name>` against a stale state file exits 1 with `pipeline_config_hash mismatch`; `--force-resume` allows the run with a WARNING.
   - `--stage <name>` for an unknown name lists the valid stage names in the error message (no opaque "stage not found").
   - `--output-format json` envelope passes `jq -e '.pipeline_run_id'` on every multi-stage invocation.

5. [ ] **Per-stage gates, auto-revert, and stage-boundary resume**
   Each stage carries its own `evaluation:` block (Task 2 inheritance matrix); the gate logic that already runs in `ForgeTrainer._post_training_gate` (loss thresholds, benchmark min-score, safety regression, judge min-score, human-approval) executes **per stage**.  If any stage fails an auto-revert, the pipeline stops at that stage; subsequent stages enter `status: skipped_due_to_prior_revert` in both the pipeline manifest and the state file.  The reverted model still exists on disk per the existing single-stage auto-revert contract — Phase 14 does not change auto-revert semantics, it just composes them.

   **Human approval gate within a pipeline.**  If a stage has `evaluation.require_human_approval: true`, the trainer follows the existing Phase 9 flow: model lands in `final_model.staging.<run_id>/`, exits with `EXIT_AWAITING_APPROVAL (4)`.  Pipeline-specific behaviour: the orchestrator captures the staging path in the pipeline state (`status: gated_pending_approval`), prints the resume command the operator needs (`forgelm --config pipeline.yaml --resume-from <next_stage>` after `forgelm approve <run_id>`), and exits with the same `EXIT_AWAITING_APPROVAL (4)` code so CI/CD wrappers see one consistent gate signal.  On resume, the auto-chained `input_model` for the next stage points at the *promoted* `final_model/` path (post-approval), not the `final_model.staging/` path.

   **Audit-log events (extends the existing 5-event vocabulary):**
   - `pipeline.started` — run id, config hash, stage count, stage names
   - `pipeline.stage_started` — stage name, index, input model, input source (chain/cli_override/root)
   - `pipeline.stage_completed` — stage name, metrics summary, gate decision (`passed` / `failed`)
   - `pipeline.stage_gated` — stage name, gate decision `approval_pending`, staging path (emitted instead of `stage_completed` when a stage exits `EXIT_AWAITING_APPROVAL`; lets dashboard / SIEM rules filter on the event name alone — Phase 14 review F-N-1)
   - `pipeline.stage_reverted` — stage name, auto-revert reason, halt-pipeline=true
   - `pipeline.force_resume` — operator-approved stale-hash override; carries `old_config_hash` + `new_config_hash` so reviewers can correlate to the audit trail (Phase 14 review F-B-2)
   - `pipeline.completed` — final status, total duration, stage count

   These events live alongside (not replacing) the existing per-stage `training.*` events emitted by `ForgeTrainer`.  Webhook notifier (`forgelm/webhook.py`) gains `notify_pipeline_started` / `notify_pipeline_completed` / `notify_pipeline_reverted` methods that wrap the existing 5-event vocabulary so Slack / Teams dashboards filtering on `event=training.failure` continue to work; pipeline-aware dashboards can additionally filter on the new `pipeline.*` events.

   **Acceptance:**
   - 3-stage SFT→DPO→GRPO pipeline where DPO stage's evaluation gate fails: pipeline manifest shows DPO `status: failed` + `auto_revert_triggered: true`, GRPO `status: skipped_due_to_prior_revert`, final exit code matches the failing stage's exit code (not `EXIT_SUCCESS`).
   - Same pipeline with `evaluation.require_human_approval: true` on the SFT stage: SFT exits with `EXIT_AWAITING_APPROVAL (4)`, pipeline state file records `status: gated_pending_approval` for SFT and `status: pending` for DPO / GRPO; after `forgelm approve <run_id>` + `forgelm --resume-from dpo_stage`, the pipeline picks up with DPO's input pointing at the promoted SFT `final_model/` path.
   - Webhook stub asserts that `pipeline.started` fires once, `pipeline.stage_completed` fires per stage, `pipeline.completed` fires once, payload schema matches the documented spec.
   - The existing single-stage `training.*` event vocabulary is unchanged; existing webhook consumers see no new events on non-pipeline runs.

## Requirements

- **Backward compatibility, byte-identical.** A config file without a `pipeline:` key produces *exactly* the same `forgelm/trainer.py` execution path as v0.6.0.  `forgelm/trainer.py` itself is unmodified by Phase 14; the pipeline orchestrator is a layer above it.  Regression test: re-run an existing single-stage config through Phase 14 code and assert the output JSONL / manifest / checkpoint bytes match a v0.6.0 reference fixture.
- **Each stage is independently testable** via `forgelm --config pipeline.yaml --stage <name>` (Task 4 partial-run rules).
- **Dry-run validates every stage** (Pydantic + chain integrity + manifest schema) before any GPU is allocated; collects all failures rather than stopping at the first.
- **Pipeline manifest integrates with existing `compliance.py`** — same atomic-write pattern, same JSON schema vocabulary; new fields added, none renamed or removed.
- **No new heavy dependencies.**  Phase 14 uses only the existing Pydantic / PyYAML / pure-Python surface.  No orchestration framework (Airflow / Prefect / Dagster) — pipelines stay in-process so the existing single-config-file UX scales to chains without a deployment story.
- **Determinism preserved.**  For any fixed `pipeline.yaml` + input bytes, the run is deterministic *modulo the existing single-stage non-determinism surface* (GPU floating-point, dataloader RNG).  The pipeline manifest's `pipeline_config_hash` proves config-level reproducibility.
- **Bilingual docs sweep.**  Operator-facing guides updated in EN + TR: new `docs/guides/pipeline.md` + `pipeline-tr.md` (canonical "first pipeline" walkthrough), updates to `docs/reference/configuration.md` + `-tr.md` (the new `pipeline:` block), updates to `docs/guides/cli.md` + `-tr.md` (`--stage`, `--resume-from`, `--force-resume`).  `tools/check_bilingual_parity.py --strict` must pass at PR open.
- **CLI help / wizard surface.**  `forgelm --help` lists the three new flags with one-line descriptions; `forgelm wizard` does *not* gain a pipeline path in Phase 14 (single-stage wizard is already complex; chained pipelines are operator-grade and use the manual YAML surface).  `tools/check_cli_help_consistency.py --strict` must pass.
- **Test budget.**  ≥ 30 new tests across `tests/test_pipeline_config.py` (inheritance matrix), `tests/test_pipeline_orchestrator.py` (orchestrator state machine), `tests/test_pipeline_cli.py` (flag interactions), `tests/test_pipeline_compliance.py` (manifest schema + Annex IV verification).  Coverage delta target: `+3 %` overall, with new pipeline modules ≥ 90 % line coverage.
- **Honest framing in user-facing docs.**  The "Limitations" section of `docs/guides/pipeline.md` calls out: (a) no intra-stage checkpoint resume (deferred), (b) no DAG semantics (sequential only), (c) no parallel stage execution (sequential only), (d) no `forgelm wizard` integration.  Operators see what does *not* work before they hit it.

## Test fixture sketch (Phase 15-style matrix)

Committed under `tests/fixtures/pipeline/`:

| Fixture | Purpose |
|---|---|
| `minimal_3_stage.yaml` | SFT → DPO → GRPO with the smallest valid config per stage; smoke baseline. |
| `inheritance_matrix.yaml` | Hits every row of the inheritance matrix (auto-chain, inherited, overridden, rejected-per-stage). |
| `gated_pending_approval.yaml` | Stage 1 has `require_human_approval: true`; orchestrator must exit `EXIT_AWAITING_APPROVAL (4)` and write the gate state. |
| `auto_revert_at_stage_2.yaml` | Stage 2 has a `max_acceptable_loss` that the synthetic eval guarantees to exceed; subsequent stages must record `skipped_due_to_prior_revert`. |
| `invalid_distributed_per_stage.yaml` | Per-stage `distributed:` block; orchestrator must reject at config-load time with the exact error message documented in Task 2. |
| `stale_state_resume.yaml` | Pair of configs differing in `learning_rate`; on resume against the first state file, the second config must trigger the `pipeline_config_hash mismatch` exit. |

Each fixture has a golden pipeline manifest committed alongside; regression suite runs `forgelm` against the fixture (with mocked trainers via the existing `MagicMock(ForgeTrainer)` pattern) and byte-compares.

## Delivery

- **Target release:** `v0.7.0`.  Re-slotted from the earlier `v0.6.0` placeholder; Phase 15 (Ingestion Pipeline Reliability) displaced it after the 2026-05-11 ingestion pilot exposed silent-failure gaps that demanded a focused release — see [completed-phases.md#phase-15-ingestion-pipeline-reliability-v060](completed-phases.md#phase-15-ingestion-pipeline-reliability-v060).
- **Entry gate (all must have held prior to the first Phase 14 PR):**
  - The 6 regression fixtures listed above were committed as zero-byte placeholders under `tests/fixtures/pipeline/` so the file paths were locked.
  - The Phase 14 issue (`#TBD`) was opened on GitHub referencing this file.
  - A Phase 14 GitHub label was created so review-round PRs could be grouped.
  - Baseline coverage of `forgelm/config.py` and `forgelm/compliance.py` was measured against the v0.6.0 tag and recorded in the Phase 14 issue (consistent with the Phase 15 entry-gate discipline).
- **CHANGELOG plan:** every Wave 1 task lands a one-line bullet under `[Unreleased]` per Keep-a-Changelog convention; at `v0.7.0` tag time the `[Unreleased]` block is renamed to `[0.7.0] — YYYY-MM-DD` per the existing release ritual.
- **Validation gate to ship Phase 14:** all 6 regression fixtures pass byte-comparison; bilingual parity + CLI help consistency guards green; full `pytest tests/` green; new `forgelm verify-annex-iv --pipeline <run_dir>` validator returns exit 0 on every fixture's golden manifest.  At least one end-to-end manual run against a 3-stage real pipeline (operator-supplied datasets) is signed off in the Phase 14 issue before the release tag.
- **Wave 2 / deferred items** (separate follow-up phases, not part of v0.7.0):
  - Intra-stage HF `Trainer.train(resume_from_checkpoint=...)` integration (would let `--resume-from` pick up mid-stage rather than at stage boundaries).
  - DAG pipelines (non-linear stage dependencies) — would require a different config schema and explicit dependency declaration; v0.7.x or later.
  - Parallel stage execution (independent branches running concurrently) — gated on the DAG schema; same horizon.
  - `forgelm wizard` pipeline path — gated on operator demand after v0.7.0 ships.

---

## Cross-references

- **Code surface affected:** [`forgelm/config.py`](../../forgelm/config.py) (new `PipelineStage` + `PipelineConfig` models, root-level `pipeline` field), [`forgelm/cli/_parser.py`](../../forgelm/cli/_parser.py) (`--stage`, `--resume-from`, `--force-resume`, `--input-model`), [`forgelm/cli/_dispatch.py`](../../forgelm/cli/_dispatch.py) + new `forgelm/cli/_pipeline.py` (orchestrator), [`forgelm/compliance.py`](../../forgelm/compliance.py) (`generate_pipeline_manifest`, `verify_annex_iv --pipeline` mode), [`forgelm/webhook.py`](../../forgelm/webhook.py) (`notify_pipeline_*` methods).  [`forgelm/trainer.py`](../../forgelm/trainer.py) is **not** modified — the orchestrator composes existing `ForgeTrainer` instances per stage.
- **User-facing surfaces to add/update:** new `docs/guides/pipeline.md` + `-tr.md` (planned, created by Phase 14 implementation), updates to [`docs/reference/configuration.md`](../reference/configuration.md) + `-tr.md`, new `docs/guides/cli.md` + `-tr.md` (planned), and [`config_template.yaml`](../../config_template.yaml) gains a commented-out `pipeline:` example block.
- **Standards consulted:** [`docs/standards/error-handling.md`](../standards/error-handling.md) (exit code stability), [`docs/standards/architecture.md`](../standards/architecture.md) (layering — orchestrator above trainer), [`docs/standards/testing.md`](../standards/testing.md) (fixture matrix discipline), [`docs/standards/localization.md`](../standards/localization.md) (EN ↔ TR mirror).
- **Pattern reference:** Phase 15's review-absorption discipline + fixture matrix is the working model — see [completed-phases.md#phase-15-ingestion-pipeline-reliability-v060](completed-phases.md#phase-15-ingestion-pipeline-reliability-v060).

## Release-time follow-up (deferred to the `v0.7.0` `cut-release` cycle)

Phase 14 implementation ships on the `development` branch ahead of the
PyPI tag.  The two operator-facing surfaces below are intentionally not
edited inside this PR — they are released-product surfaces and stay
v0.6.0-shaped until `cut-release` actually tags `v0.7.0`:

- **`docs/usermanuals/_meta.yaml` + `docs/usermanuals/{en,tr,de,fr,es,zh}/training/pipeline.md`** — new training-section page mirroring `docs/guides/pipeline.md`.  TOC entry needs 6 locale titles (`en`/`tr` mandatory; `de`/`fr`/`es`/`zh` fall back to EN per `docs/standards/localization.md`).
- **`site/features.html` + `site/index.html` + `site/js/translations.js`** — new "Multi-stage training pipelines" feature card and a hook into the existing `home.pipeline` (alignment-stack) section so the two distinct senses of the word "pipeline" don't collide visually.  6-language i18n keys (`features.pipeline.title`, `features.pipeline.body`, `home.pipeline.chain.cta`) gated at full parity by `tools/check_site_claims.py`.
- **`tools/update_site_version.py`** — Phase 14 ships under the `v0.7.0` literal bump, which the version guard rewrites across `site/*.html` and `site/js/translations.js` automatically.

The `cut-release` skill ([.claude/skills/cut-release/SKILL.md](../../.claude/skills/cut-release/SKILL.md)) walks these in order at `v0.7.0` tag time.

---

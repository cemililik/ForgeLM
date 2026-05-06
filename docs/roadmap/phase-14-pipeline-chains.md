# Phase 14: Multi-Stage Training Pipeline Chains

> **Not:** Bu dosya tek bir planlanan fazı detaylandırır. Tüm fazların özeti için [../roadmap.md](../roadmap.md).

**Goal:** Enable a single config file to define a sequential SFT → DPO → GRPO training pipeline, with each stage using the previous stage's output as its base model. Eliminate the current requirement for manual config management across stages.
**Estimated Effort:** Low-Medium (3-6 weeks)
**Priority:** Medium-High — frequently requested by enterprise users; low implementation risk (uses existing trainers)

> **Context:** Enterprise ML teams running production post-training pipelines currently need to write 3+ separate config files, manually set `model.name_or_path` to each stage's output, and orchestrate execution themselves. A `pipeline:` config key that chains stages solves this while remaining fully config-driven and testable.

### Tasks:

1. [ ] **`pipeline:` config section in ForgeConfig**
   New optional `pipeline: stages: [...]` section. Each stage is a full training config override. Stages execute sequentially; each stage's `model.name_or_path` is automatically set to the previous stage's `training.output_dir/final_model`.
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

2. [ ] **Stage inheritance and override semantics**
   Each stage inherits the top-level config as defaults. Only explicitly set fields are overridden per stage. LoRA config, model config (except `name_or_path`), distributed config, and safety config inherit from the root unless overridden per stage.

3. [ ] **Pipeline compliance artifacts**
   `compliance/pipeline_manifest.yaml` captures the full multi-stage provenance: stage names, input/output model paths, per-stage metrics and artifacts. Satisfies EU AI Act Annex IV requirement for complete training lineage documentation.

4. [ ] **CLI support**
   ```bash
   # Single pipeline run
   forgelm --config pipeline.yaml

   # Dry-run validates all stages
   forgelm --config pipeline.yaml --dry-run

   # Run specific stage only
   forgelm --config pipeline.yaml --stage dpo_stage

   # Resume from failed stage
   forgelm --config pipeline.yaml --resume-from dpo_stage
   ```

5. [ ] **Per-stage auto-revert and gates**
   Each stage can have independent evaluation gates. If a stage fails auto-revert, the pipeline stops and reports which stage failed. Subsequent stages are not run.

### Requirements:
- Single-stage configs (no `pipeline:` key) must be completely unaffected — 100% backward compatible.
- Each stage is independently testable via `--stage <name>`.
- Pipeline manifest integrates with existing `compliance.py` audit log.
- `--dry-run` validates all stages' configs before any GPU allocation.

### Delivery:
- Target release: `v0.6.0` (reslotted from earlier `v0.5.x` placeholders; Phase 14 is grouped with the Phase 13 Pro CLI tier per the v0.5.5 closure cycle's deferred-callout policy in `docs/usermanuals/{en,tr}/deployment/model-merging.md` and the [phase-12-6-closure-cycle.md](phase-12-6-closure-cycle.md) summary).
- No hard blockers; the v0.5.5 closure cycle has merged. Phase 14 starts after the v0.5.5 PyPI tag is published.

---

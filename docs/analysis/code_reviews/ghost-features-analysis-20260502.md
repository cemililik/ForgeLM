# Ghost Feature Analysis — ForgeLM CLI

**Date:** 2026-05-02 (v2 — full re-scan)  
**Branch:** closure/foundation-faz1-8 (current HEAD at time of analysis)  
**Scope:** All `forgelm <subcommand>` and flag references across **all** docs:
- `docs/usermanuals/` (EN + TR)
- `docs/guides/`, `docs/reference/`, `docs/qms/`, `docs/roadmap/`
- `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`
- `site/*.html`
- Cross-checked against:
  - `forgelm/cli/_parser.py` (registered subcommands + flags)
  - `forgelm/cli/subcommands/` (implementations)
  - `forgelm/config.py` (ForgeConfig structure)
  - `docs/analysis/code_reviews/closure-plan-202604300906.md`
  - `docs/roadmap/` directory

---

## Summary

**15 ghost subcommands** found in Category A: 12 subcommands that do not exist in the codebase, 1 documented under the wrong form (GH-011 — flag form `--benchmark-only` rather than a subcommand), 1 with alias-only confusion (GH-008 — `verify-log` vs the implemented `verify-audit`), 1 planned but not yet implemented (GH-013 — `forgelm purge`, scheduled for Faz 21). The complete document spans **28 entries**: 15 subcommands + 10 flags/options + 1 config key + 2 env vars (see the standalone "Total ghost count" line below the implemented-subcommand reference).

### Category A — Ghost subcommands (documented, not implemented)

| # | Command | Refs (all docs) | In code | Closure plan | Roadmap |
|---|---|---|---|---|---|
| GH-001 | `forgelm doctor` | 38 | ❌ | ❌ | ❌ |
| GH-002 | `forgelm cache-models` | 16 | ❌ | ❌ | ❌ |
| GH-003 | `forgelm cache-tasks` | 11 | ❌ | ❌ | ❌ |
| GH-004 | `forgelm verify-annex-iv` | 12 | ❌ | ❌ | ❌ |
| GH-005 | `forgelm safety-eval` | 12 | ❌ | ❌ | ❌ |
| GH-006 | `forgelm trend` | 10 | ❌ | ❌ | ❌ |
| GH-007 | `forgelm approvals` | 11 | ❌ | ❌ | ❌ |
| GH-008 | `forgelm verify-log` | 7 | ❌ alias confusion | ❌ | ❌ |
| GH-009 | `forgelm verify-gguf` | 7 | ❌ | ❌ | ❌ |
| GH-010 | `forgelm compare-runs` | 8 | ❌ | ❌ | ❌ |
| GH-011 | `forgelm benchmark` | 10 | ⚠️ wrong form | ❌ | ❌ |
| GH-012 | `forgelm batch-chat` | 7 | ❌ | ❌ | ❌ |
| GH-013 | `forgelm purge` | 8 | ❌ | ✅ Faz 21 | ❌ |
| GH-014 | `forgelm reverse-pii` | 2 | ❌ | ❌ | ❌ |
| GH-015 | `forgelm merge-sweep` | 2 | ❌ | ❌ | ❌ |

### Category B — Ghost flags / wrong flag names

| # | Documented as | Actual in parser | Severity |
|---|---|---|---|
| GH-016 | `--export-bundle` | `--compliance-export` | High — in QMS SOPs |
| GH-017 | `--estimate-cost` | not registered | Medium |
| GH-018 | `--resume-from PATH` | `--resume [PATH]` | Low — close but different |
| GH-019 | `--output-format plain\|json` | `text\|json` (not `plain`) | Low — naming nit |
| GH-020 | `forgelm deploy --target kserve\|triton` | choices: `ollama\|vllm\|tgi\|hf-endpoints` | Medium |
| GH-021 | `forgelm chat --base`, `--top-p`, `--safety`, `--load` | none of these exist | Medium |
| GH-022 | export quant `q6_k` and `fp16` | `f16` exists, `q6_k` does not | Low |
| GH-023 | `forgelm ingest --format raw\|instructions\|qa` | no `--format` on ingest | Medium |
| GH-024 | `forgelm ingest --language`, `--include`, `--exclude`, `--pii-locale` | only `--pii-ml-language` exists | Medium |
| GH-025 | chat slash commands `/load`, `/top_p`, `/max_tokens`, `/safety` | only `/reset /save /temperature /system /help /exit` | Low |

### Category C — Ghost config keys

| # | Documented as | Actual in config.py | Severity |
|---|---|---|---|
| GH-026 | `ingestion.retention.raw_documents.ttl_days` | no `ingestion` or `retention` top-level key exists in `ForgeConfig` | Medium |

### Category D — Ghost env vars

| # | Documented as | In code | Source |
|---|---|---|---|
| GH-027 | `FORGELM_RESUME_TOKEN` | not used anywhere in forgelm/ | cli.md env table |
| GH-028 | `FORGELM_CACHE_DIR` | not used anywhere in forgelm/ | cli.md env table |

### Category E — Planned (not yet implemented)

| # | Command | Closure plan | Expected wave |
|---|---|---|---|
| GH-013 | `forgelm purge` | ✅ Faz 21 | Wave 2 |

---

**Implemented subcommands** (for reference):  
`chat`, `export`, `deploy`, `quickstart`, `ingest`, `audit`, `verify-audit`, `approve`, `reject` — 9 total.

**Total ghost count: 28 entries** (15 subcommands + 10 flags/options + 1 config key + 2 env vars)

---

## Detailed Findings

---

### GH-001 — `forgelm doctor`

**Severity:** Critical (user-onboarding blocker)  
**References in usermanuals:** 30 occurrences across 10 files (5 EN source pages mirrored to TR; the table below lists every entry rather than collapsing pairs)

| File | Lines | Context |
|---|---|---|
| `docs/usermanuals/en/getting-started/installation.md` | 100, 103, 111 | Installation flow — "Run `forgelm doctor` before anything else" |
| `docs/usermanuals/en/getting-started/first-run.md` | 12, 29, 32, 41 | First-run diagram + step-by-step |
| `docs/usermanuals/en/operations/troubleshooting.md` | 8, 168, 173, 179 | "catches 80% of environment problems" |
| `docs/usermanuals/en/operations/air-gap.md` | 115, 124, 148 | `forgelm doctor --offline` variant |
| `docs/usermanuals/en/reference/cli.md` | 15 | CLI reference table |
| `docs/usermanuals/tr/getting-started/installation.md` | 100, 103, 111 | TR mirror |
| `docs/usermanuals/tr/getting-started/first-run.md` | 12, 29, 32, 41 | TR mirror |
| `docs/usermanuals/tr/operations/troubleshooting.md` | 8, 168, 173, 179 | TR mirror |
| `docs/usermanuals/tr/operations/air-gap.md` | 115, 124, 148 | TR mirror |
| `docs/usermanuals/tr/reference/cli.md` | 15 | TR mirror |

**Documented behavior:** Environment check — verifies Python version, PyTorch, CUDA availability, GPU detection, optional dep install status. `--offline` variant checks cached resources for air-gapped deployments.

**Code reality:** No `doctor` in `forgelm/cli/_parser.py`, no `_doctor.py` in `forgelm/cli/subcommands/`. Running `forgelm doctor` exits with "unrecognized arguments".

**Closure plan:** Not mentioned in any phase.  
**Roadmap:** Not mentioned in any file under `docs/roadmap/`.

**Impact:** This is the first command new users are told to run after installation. A user following `installation.md` or `first-run.md` will hit an immediate error. The `--offline` variant is central to the air-gap deployment guide.

**Options:**
- A) Implement `forgelm doctor` (see scope below)
- B) Remove all 30 references; replace with a manual checklist
- C) Add to closure plan as a new phase

**Suggested scope if implemented:** Python version check, `torch.cuda.is_available()`, GPU count + VRAM, check for optional extras (`[qlora]`, `[safety]`, `[evaluation]`, `[ingestion-pii-ml]`), output as structured table. `--offline` flag: additionally checks `HF_HUB_OFFLINE` environment + whether required model weights are in local cache.

---

### GH-002 — `forgelm cache-models`

**Severity:** High (air-gap workflow blocker)  
**References in usermanuals:** 12 occurrences across 4 files

| File | Lines | Context |
|---|---|---|
| `docs/usermanuals/en/operations/air-gap.md` | 25, 30, 54 | Pre-cache workflow: `--model`, `--safety` flags |
| `docs/usermanuals/en/operations/docker.md` | 101, 104 | Dockerfile `RUN` steps |
| `docs/usermanuals/en/reference/cli.md` | 28 | CLI reference table |
| `docs/usermanuals/tr/operations/air-gap.md` | 25, 30, 54 | TR mirror |
| `docs/usermanuals/tr/operations/docker.md` | 101, 104 | TR mirror |
| `docs/usermanuals/tr/reference/cli.md` | 28 | TR mirror |

**Documented behavior:** Pre-download HuggingFace model weights to local cache for air-gapped environments. Flags: `--model <name>`, `--safety <name>`.

**Code reality:** No `cache-models` subcommand. The underlying functionality (HF cache population) is achievable via `huggingface-cli download` or Python `snapshot_download()`, but ForgeLM exposes no wrapper.

**Closure plan:** Not mentioned.  
**Roadmap:** Not mentioned.

**Note:** Closely paired with GH-003 (`cache-tasks`). Both appear exclusively in air-gap and Docker operational guides. An operator following `air-gap.md` cannot execute either step as documented.

---

### GH-003 — `forgelm cache-tasks`

**Severity:** High (air-gap workflow blocker)  
**References in usermanuals:** 8 occurrences across 4 files

| File | Lines | Context |
|---|---|---|
| `docs/usermanuals/en/operations/air-gap.md` | 30, 101 | Pre-cache lm-eval tasks: `--tasks hellaswag,arc_easy,...` |
| `docs/usermanuals/en/operations/docker.md` | 107 | Dockerfile `RUN` step |
| `docs/usermanuals/en/reference/cli.md` | 29 | CLI reference table |
| `docs/usermanuals/en/reference/yaml-templates.md` | 315 | Comment: "Pre-requisites: forgelm cache-models / cache-tasks already run" |
| `docs/usermanuals/tr/operations/air-gap.md` | 30, 101 | TR mirror |
| `docs/usermanuals/tr/operations/docker.md` | 107 | TR mirror |
| `docs/usermanuals/tr/reference/cli.md` | 29 | TR mirror |

**Documented behavior:** Pre-download lm-evaluation-harness task datasets for air-gapped environments. Flags: `--tasks <comma-separated list>`.

**Code reality:** No `cache-tasks` subcommand.

**Closure plan:** Not mentioned.  
**Roadmap:** Not mentioned.

---

### GH-004 — `forgelm verify-annex-iv`

**Severity:** High (compliance workflow blocker)  
**References in usermanuals:** 8 occurrences across 4 files

| File | Lines | Context |
|---|---|---|
| `docs/usermanuals/en/compliance/annex-iv.md` | 137, 144 | "validates Annex IV artifact + re-computes manifest hashes" |
| `docs/usermanuals/en/operations/troubleshooting.md` | 155 | Fix for "Missing fields in Annex IV artifact" error |
| `docs/usermanuals/en/reference/cli.md` | 25 | CLI reference table |
| `docs/usermanuals/tr/compliance/annex-iv.md` | 137, 144 | TR mirror |
| `docs/usermanuals/tr/operations/troubleshooting.md` | 155 | TR mirror |
| `docs/usermanuals/tr/reference/cli.md` | 25 | TR mirror |

**Documented behavior:** Validate an `annex_iv.json` artifact — check required fields, re-compute manifest hashes, detect tampering.

**Code reality:** `forgelm/compliance.py` generates `annex_iv_metadata.json` (lines 680, 909-910) during training. There is no verification subcommand. `forgelm verify-audit` (Faz 6) verifies the audit log chain but not the Annex IV artifact.

**Closure plan:** Not mentioned. Note: `forgelm verify-audit` was planned and shipped (Faz 6) but serves a different purpose (audit chain integrity, not Annex IV field completeness).  
**Roadmap:** Not mentioned.

**Note:** The EU AI Act Article 11 + Annex IV documentation requirements make this a real compliance use-case, not purely aspirational.

---

### GH-005 — `forgelm safety-eval`

**Severity:** High (evaluation workflow gap)  
**References in usermanuals:** 8 occurrences across 4 files

| File | Lines | Context |
|---|---|---|
| `docs/usermanuals/en/evaluation/safety.md` | 76, 91 | Standalone safety evaluation with custom probe set |
| `docs/usermanuals/en/deployment/gguf-export.md` | 136 | Post-export safety check on GGUF model |
| `docs/usermanuals/en/reference/cli.md` | 20 | CLI reference table |
| `docs/usermanuals/tr/evaluation/safety.md` | 76, 91 | TR mirror |
| `docs/usermanuals/tr/deployment/gguf-export.md` | 136 | TR mirror |
| `docs/usermanuals/tr/reference/cli.md` | 20 | TR mirror |

**Documented behavior:** Standalone Llama Guard scoring against a model without full training run. Flags: `--model <path-or-name>`, `--probes <jsonl>`, `--default-probes`. Supports GGUF models.

**Code reality:** Safety evaluation code exists in `forgelm/safety.py` and runs inside the training pipeline. There is no standalone CLI entry point. `forgelm/cli/_no_train_modes.py` has a `--benchmark-only` mode analog but no `safety-eval` mode.

**Closure plan:** Not mentioned as a standalone subcommand.  
**Roadmap:** Safety evaluation pipeline (Phase 9 in completed-phases.md) is part of the training flow, not a standalone command.

**Note:** The GGUF context (`forgelm safety-eval --model model.q4_k_m.gguf`) is particularly useful for post-deployment validation — a genuine use-case not served by the current pipeline.

---

### GH-006 — `forgelm trend`

**Severity:** Medium  
**References in usermanuals:** 6 occurrences across 2 files

| File | Lines | Context |
|---|---|---|
| `docs/usermanuals/en/evaluation/trend-tracking.md` | 80, 107 | Query metric trends: `--metric`, `--lookback`, `--filter config_hash` |
| `docs/usermanuals/en/reference/cli.md` | 30 | CLI reference table |
| `docs/usermanuals/tr/evaluation/trend-tracking.md` | 80, 107 | TR mirror |
| `docs/usermanuals/tr/reference/cli.md` | 30 | TR mirror |

**Documented behavior:** Show metric trend across recent runs from `.forgelm/eval-history.jsonl`. Flags: `--metric <path>`, `--lookback <n>`, `--filter config_hash`.

**Code reality:** Trend data is embedded in audit reports and the eval-history file is referenced in docs, but no `.forgelm/eval-history.jsonl` write path exists in `forgelm/trainer.py` or `forgelm/compliance.py`, and no `trend` subcommand exists.

**Closure plan:** Not mentioned.  
**Roadmap:** `docs/roadmap/completed-phases.md:563` mentions `"trend": "improving"` as a field in safety results (Phase 9), but this is an artifact field, not a CLI command. `phase-13-pro-cli.md` (Pro CLI, v0.6.0+) has `forgelm pro dashboard` for observability — trend visualization is a natural fit there but is not explicitly listed.

---

### GH-007 — `forgelm approvals`

**Severity:** Medium  
**References in usermanuals:** 6 occurrences across 2 files

| File | Lines | Context |
|---|---|---|
| `docs/usermanuals/en/compliance/human-oversight.md` | 131, 138 | `--pending` lists pending approvals; `--show <run_id>` shows detail |
| `docs/usermanuals/en/reference/cli.md` | 33 | CLI reference table |
| `docs/usermanuals/tr/compliance/human-oversight.md` | 131, 138 | TR mirror |
| `docs/usermanuals/tr/reference/cli.md` | 33 | TR mirror |

**Documented behavior:** List and inspect pending approval requests. `--pending` shows all runs in staging awaiting approval. `--show <run_id>` shows detail for a single run.

**Code reality:** `forgelm approve <run_id>` and `forgelm reject <run_id>` exist (Faz 9, `forgelm/cli/subcommands/_approve.py`). The listing command `forgelm approvals` does not. An operator cannot discover which runs are awaiting approval without manually inspecting the filesystem or audit log.

**Closure plan:** Not mentioned. Faz 9 delivered approve + reject but not the listing command.  
**Roadmap:** Not mentioned.

**Note:** Closely related to the implemented `forgelm approve`/`forgelm reject`. The listing command would scan `final_model.staging/` directories or audit log for unresolved `human_approval.required` events — the data is already there.

---

### GH-008 — `forgelm verify-log`

**Severity:** Medium (alias confusion with existing command)  
**References in usermanuals:** 4 occurrences across 2 files

| File | Lines | Context |
|---|---|---|
| `docs/usermanuals/en/compliance/audit-log.md` | 59, 65 | Verify audit chain integrity, check timestamps, prev_hash, seq numbers |
| `docs/usermanuals/en/reference/cli.md` | 26 | CLI reference table |
| `docs/usermanuals/tr/compliance/audit-log.md` | 59, 65 | TR mirror |
| `docs/usermanuals/tr/reference/cli.md` | 26 | TR mirror |

**Documented behavior:** Validate audit log chain — check monotonic timestamps, prev_hash chain validity, no gaps in seq numbers.

**Code reality:** `forgelm verify-audit <path>` (Faz 6, `forgelm/cli/subcommands/_verify_audit.py`) performs exactly this function. The documented command is `verify-log`; the implemented command is `verify-audit`. Same functionality, different name.

**Closure plan:** Faz 6 explicitly delivered `forgelm verify-audit`. The name `verify-log` never appears in the plan.  
**Roadmap:** Not mentioned.

**Note:** This is likely a naming inconsistency introduced during documentation authoring — the writer used `verify-log` while the implementation was named `verify-audit`. Resolution: rename the usermanual references to `verify-audit` (no code change needed).

---

### GH-009 — `forgelm verify-gguf`

**Severity:** Medium  
**References in usermanuals:** 4 occurrences across 2 files

| File | Lines | Context |
|---|---|---|
| `docs/usermanuals/en/deployment/gguf-export.md` | 80 | Post-export integrity check on `.gguf` file |
| `docs/usermanuals/en/reference/cli.md` | 27 | CLI reference table |
| `docs/usermanuals/tr/deployment/gguf-export.md` | 80 | TR mirror |
| `docs/usermanuals/tr/reference/cli.md` | 27 | TR mirror |

**Documented behavior:** Validate GGUF file integrity — check magic bytes, metadata block, tensor checksums.

**Code reality:** `forgelm/cli/subcommands/_export.py` handles GGUF conversion but no verification subcommand exists. `_export.py` does write a SHA-256 integrity record during export (per CONTRIBUTING), but no standalone verify command reads it back.

**Closure plan:** Not mentioned.  
**Roadmap:** Not mentioned.

---

### GH-010 — `forgelm compare-runs`

**Severity:** Low-Medium  
**References in usermanuals:** 4 occurrences across 2 files

| File | Lines | Context |
|---|---|---|
| `docs/usermanuals/en/operations/experiment-tracking.md` | 116 | Side-by-side comparison of run metrics: `compare-runs runs/v1.0 runs/v1.1 runs/v1.2` |
| `docs/usermanuals/en/evaluation/trend-tracking.md` | 116 | Positional args: list of run directories |
| `docs/usermanuals/tr/operations/experiment-tracking.md` | 116 | TR mirror |
| `docs/usermanuals/tr/evaluation/trend-tracking.md` | 116 | TR mirror |

**Documented behavior:** Side-by-side metric comparison across multiple run directories. Positional args: run directory paths.

**Code reality:** No `compare-runs` subcommand. Underlying data (per-run JSON artifacts) is available; the command to read and format it does not exist.

**Closure plan:** Not mentioned.  
**Roadmap:** `phase-13-pro-cli.md` has "experiment browser" as a Pro CLI feature (web dashboard) but `compare-runs` as a CLI command is not explicitly listed there.

---

### GH-011 — `forgelm benchmark` (wrong form)

**Severity:** Low-Medium (wrong interface documented)  
**References in usermanuals:** 4 occurrences across 2 files

| File | Lines | Context |
|---|---|---|
| `docs/usermanuals/en/evaluation/benchmarks.md` | 71 | `forgelm benchmark --model "..." --tasks hellaswag,...` |
| `docs/usermanuals/en/reference/cli.md` | 19 | CLI reference table: "Run lm-eval-harness against a model" |
| `docs/usermanuals/tr/evaluation/benchmarks.md` | 71 | TR mirror |
| `docs/usermanuals/tr/reference/cli.md` | 19 | TR mirror |

**Documented behavior:** Standalone benchmark run against an existing model (no training). Flags: `--model`, `--tasks`.

**Code reality:** The functionality exists but is exposed as a **flag on the main command**, not a subcommand. `forgelm/cli/_parser.py:598`:
```text
--benchmark-only   Run benchmark evaluation on an existing model without training.
                   Requires evaluation.benchmark config.
```
Usage: `forgelm --config my_config.yaml --benchmark-only /path/to/model`

The documented form `forgelm benchmark --model ... --tasks ...` does not work. A user following `benchmarks.md` will get an error.

**Closure plan:** Not mentioned as a subcommand. `--benchmark-only` flag exists in code but is not prominently documented.  
**Roadmap:** Not mentioned.

**Note:** Two options: (a) add `benchmark` as a proper subcommand that wraps `--benchmark-only` logic, or (b) correct the docs to show the `--benchmark-only` flag form.

---

### GH-012 — `forgelm batch-chat`

**Severity:** Low  
**References in usermanuals:** 4 occurrences across 2 files

| File | Lines | Context |
|---|---|---|
| `docs/usermanuals/en/deployment/chat.md` | 133 | "automated probing of many prompts" — `--prompts <jsonl>`, `--output <jsonl>` |
| `docs/usermanuals/en/reference/cli.md` | 22 | CLI reference table: "Non-interactive prompt → response" |
| `docs/usermanuals/tr/deployment/chat.md` | 133 | TR mirror |
| `docs/usermanuals/tr/reference/cli.md` | 22 | TR mirror |

**Documented behavior:** Non-interactive batch inference — read prompts from JSONL, write responses to JSONL. Alternative to interactive `forgelm chat`.

**Code reality:** `forgelm chat` subcommand exists (`forgelm/cli/subcommands/_chat.py`) but no `--batch` or `batch-chat` mode.

**Closure plan:** Not mentioned.  
**Roadmap:** Not mentioned.

---

### GH-013 — `forgelm purge` (planned, not yet implemented)

**Severity:** Informational (legitimate planned feature)  
**References in usermanuals:** 5 occurrences across 3 files (inferred from GDPR docs)

| File | Context |
|---|---|
| `docs/usermanuals/en/compliance/gdpr-erasure.md` | Linked from Faz 21 |
| `docs/usermanuals/tr/compliance/gdpr-erasure.md` | TR mirror |

**Documented behavior:** GDPR right-to-erasure. `--row-id`, `--corpus`, `--run-id`, `--kind`, `--check-policy` flags.

**Code reality:** No implementation yet.

**Closure plan:** ✅ Explicitly planned in **Faz 21** (GDPR right-to-erasure implementation). Tasks:
- `forgelm/cli/subcommands/_purge.py`
- `forgelm/compliance.py` `record_erasure_event()` helper
- Audit events: `data.erasure_requested`, `data.erasure_completed`, `data.erasure_failed`
- Tests: 7 acceptance tests
- Docs: `docs/guides/gdpr_erasure.md` + TR mirror

**Roadmap:** Not separately listed (embedded in closure plan as Wave 2+ phase).

**Status:** Not a documentation error — Faz 21 has not shipped yet. The docs will be accurate once Faz 21 is implemented.

---

### GH-014 — `forgelm reverse-pii`

**Severity:** Medium  
**References:** 2 occurrences

| File | Line | Context |
|---|---|---|
| `docs/usermanuals/en/compliance/gdpr.md` | 77 | GDPR Art. 15 right of access — `--query "ali@example.com" data/*.jsonl` |
| `docs/usermanuals/tr/compliance/gdpr.md` | 77 | TR mirror |

**Documented behavior:** Reverse-PII lookup — given an identifier (email, name), scan masked JSONL files to check if it appears in the training data. Supports glob patterns.

**Code reality:** No `reverse-pii` subcommand in parser or subcommands directory. The forward direction (masking with `forgelm ingest --pii-mask`) exists, but the reverse lookup does not.

**Closure plan:** Not mentioned.  
**Roadmap:** Not mentioned.

---

### GH-015 — `forgelm merge-sweep`

**Severity:** Low-Medium  
**References:** 2 occurrences

| File | Line | Context |
|---|---|---|
| `docs/usermanuals/en/deployment/model-merging.md` | 172 | "ForgeLM ships a `forgelm merge-sweep` helper that automates" grid search over merge algorithms |
| `docs/usermanuals/tr/deployment/model-merging.md` | 172 | TR mirror |

**Documented behavior:** Automated grid search over `(algorithm, parameters)` combinations for model merging, evaluating each variant.

**Code reality:** `forgelm/merging.py` exists (model merge logic). `--merge` flag exists on main command. No `merge-sweep` subcommand.

**Closure plan:** Not mentioned.  
**Roadmap:** Not mentioned. `phase-14-pipeline-chains.md` covers multi-stage pipelines but not merge sweeps.

---

### GH-016 — `--export-bundle` flag

**Severity:** High — appears in QMS SOPs used by compliance auditors  
**References:** 3 occurrences (non-analysis docs)

| File | Line | Context |
|---|---|---|
| `docs/qms/sop_model_training.md` | 66 | "Evidence bundle: `forgelm --config job.yaml --export-bundle ./archive/`" |
| `docs/qms/roles_responsibilities.md` | 66 | "Reviews evidence bundle (`--export-bundle`)" |
| `docs/roadmap/completed-phases.md` | 346 | Listed as a shipped Phase 6 deliverable |

**Documented behavior:** Export all compliance artifacts (audit trail, data provenance, Annex IV) as a bundle/ZIP.

**Code reality:** Parser has `--compliance-export OUTPUT_DIR` (not `--export-bundle`). These appear to be the same feature with a renamed flag — `completed-phases.md` shows the old name while the parser carries the current name. The QMS SOPs were not updated when the flag was renamed.

**Closure plan:** Not mentioned as a rename.  
**Roadmap:** `completed-phases.md` marks it as ✅ shipped under the old name.

---

### GH-017 — `--estimate-cost` flag

**Severity:** Low-Medium  
**References:** 1 occurrence in `docs/usermanuals/en/reference/cli.md` top-level flags table

**Documented behavior:** Pre-flight cost estimation (GPU cost) before training.

**Code reality:** Not registered in `forgelm/cli/_parser.py`. GPU cost estimation logic exists inside the training pipeline output (`_result.py`) but no standalone `--estimate-cost` flag. `--fit-check` (VRAM estimate) does exist.

**Closure plan:** Not mentioned.  
**Roadmap:** `phase-13-pro-cli.md` has "Cloud GPU cost estimation — real-time pricing" as a Pro CLI v0.6.0 feature.

---

### GH-018 — Deploy targets `kserve` and `triton`

**Severity:** Medium  
**References:** `docs/usermanuals/en/reference/cli.md` deploy section

**Documented form:** `forgelm deploy CHECKPOINT --target ollama|vllm|tgi|hf-endpoints|kserve|triton`

**Code reality:** Parser choices: `["ollama", "vllm", "tgi", "hf-endpoints"]`. No `kserve` or `triton`. Running `forgelm deploy ... --target kserve` exits with argparse error.

**Closure plan:** Not mentioned.  
**Roadmap:** Not mentioned.

---

### GH-019 — Ghost chat flags: `--base`, `--top-p`, `--safety`, `--load`

**Severity:** Medium  
**References:** `docs/usermanuals/en/reference/cli.md` chat section

**Documented form:**
```text
forgelm chat CHECKPOINT [--base BASE_MODEL] [--temperature 0.7] [--top-p 0.9]
    [--max-tokens 1024] [--system "..."] [--safety on|off] [--load PATH]
```

**Code reality:** Parser registered flags for `forgelm chat`:  
`model_path`, `--adapter`, `--system`, `--temperature`, `--max-new-tokens`, `--no-stream`, `--load-in-4bit`, `--load-in-8bit`, `--trust-remote-code`, `--backend`

Missing: `--base`, `--top-p`, `--safety`, `--load`, `--max-tokens` (actual flag is `--max-new-tokens`).

**Closure plan:** Not mentioned.  

---

### GH-020 — Ghost ingest flags: `--format`, `--language`, `--include`, `--exclude`, `--pii-locale`

**Severity:** Medium  
**References:** `docs/usermanuals/en/reference/cli.md` ingest section

**Documented form:**
```text
forgelm ingest INPUT_DIR --output PATH.jsonl
    [--strategy tokens|markdown|paragraph|sentence]
    [--max-tokens N] [--pii-mask] [--secrets-mask]
    [--pii-locale tr|de|fr|us] [--language LANG]
    [--include "*.pdf,*.md"] [--exclude "drafts/*"]
    [--format raw|instructions|qa]
```

**Code reality mismatches:**
- `--strategy` choices: `sliding|paragraph|markdown` (not `tokens` or `sentence`)
- `--max-tokens` → actual flag is `--chunk-tokens`
- `--pii-locale` → actual flag is `--pii-ml-language`
- `--language` → does not exist
- `--include` / `--exclude` → do not exist
- `--format raw|instructions|qa` → does not exist (ingest has no `--format`; export has `--format gguf`)

**Closure plan:** Not mentioned.

---

### GH-021 — Ghost chat slash commands: `/load`, `/top_p`, `/max_tokens`, `/safety`

**Severity:** Low  
**References:** `docs/usermanuals/en/reference/cli.md`

**Documented:** `/reset`, `/save`, `/load`, `/system`, `/temperature`, `/top_p`, `/max_tokens`, `/safety`, `/help`, `/quit`

**Code reality** (`forgelm/chat.py:151-157`): `/exit`, `/quit`, `/reset`, `/save`, `/temperature`, `/system`, `/help`

Missing: `/load`, `/top_p`, `/max_tokens`, `/safety`

---

### GH-022 — Export quant option `q6_k` not registered

**Severity:** Low  
**References:** `docs/usermanuals/en/reference/cli.md` export section

**Documented:** `--quant q4_k_m|q5_k_m|q6_k|q8_0|q3_k_m|q2_k|fp16`

**Code reality:** Parser choices: `["q2_k", "q3_k_m", "q4_k_m", "q5_k_m", "q8_0", "f16"]`  
- `q6_k` is documented but not registered
- Docs say `fp16`, parser says `f16` (different string — `forgelm export ... --quant fp16` would error)

---

### GH-023 — `ingestion.retention.raw_documents.ttl_days` config key

**Severity:** Medium — appears in GDPR compliance guide  
**References:** 2 occurrences

| File | Lines | Context |
|---|---|---|
| `docs/usermanuals/en/compliance/gdpr.md` | 57-60 | GDPR Art. 5 storage limitation — automated retention enforcement |
| `docs/usermanuals/tr/compliance/gdpr.md` | 57-60 | TR mirror |

**Documented form:**
```yaml
ingestion:
  retention:
    raw_documents:
      ttl_days: 90
    audit_reports:
      ttl_days: 365
```

**Code reality:** `forgelm/config.py` `ForgeConfig` top-level keys: `model`, `lora`, `training`, `data`, `auth`, `evaluation`, `webhook`, `distributed`, `merge`, `compliance`, `risk_assessment`, `monitoring`, `synthetic`. No `ingestion` key. `DataConfig` has no `retention` field. A config with this key would fail Pydantic validation (`extra="forbid"`).

**Closure plan:** Faz 21 mentions `RetentionConfig` Pydantic block (line 682: "forgelm/config.py — RetentionConfig Pydantic block"), but this has not shipped. The GDPR docs were written ahead of the implementation.

---

### GH-024 — `FORGELM_RESUME_TOKEN` env var

**Severity:** Low  
**References:** `docs/usermanuals/en/reference/cli.md` environment table

**Documented:** "Token for the API-based human approval flow"

**Code reality:** `grep -rn "FORGELM_RESUME_TOKEN" forgelm/` → no results. Not used anywhere in the codebase.

---

### GH-025 — `FORGELM_CACHE_DIR` env var

**Severity:** Low  
**References:** `docs/usermanuals/en/reference/cli.md` environment table

**Documented:** "ForgeLM-specific cache location"

**Code reality:** `grep -rn "FORGELM_CACHE_DIR" forgelm/` → no results. Not used anywhere in the codebase. `HF_HOME` exists (standard HF env var) and is documented correctly alongside this.

---

## Closure Plan Status Summary

| Ghost | In closure-plan-202604300906.md | Phase |
|---|---|---|
| `forgelm doctor` | ❌ not mentioned | — |
| `forgelm cache-models` | ❌ not mentioned | — |
| `forgelm cache-tasks` | ❌ not mentioned | — |
| `forgelm verify-annex-iv` | ❌ not mentioned | — |
| `forgelm safety-eval` | ❌ not mentioned | — |
| `forgelm trend` | ❌ not mentioned | — |
| `forgelm approvals` | ❌ not mentioned (`approve`+`reject` are, listing is not) | Faz 9 partial |
| `forgelm verify-log` | ❌ not mentioned (`verify-audit` is) | Faz 6 alias confusion |
| `forgelm verify-gguf` | ❌ not mentioned | — |
| `forgelm compare-runs` | ❌ not mentioned | — |
| `forgelm benchmark` | ⚠️ `--benchmark-only` flag exists, subcommand form not | — |
| `forgelm batch-chat` | ❌ not mentioned | — |
| `forgelm purge` | ✅ Faz 21 | Wave 2 |
| `forgelm reverse-pii` | ❌ not mentioned | — |
| `forgelm merge-sweep` | ❌ not mentioned | — |
| `--export-bundle` | ⚠️ renamed to `--compliance-export` — QMS docs not updated | — |
| `--estimate-cost` | ❌ not mentioned | Phase 13 Pro (v0.6.0) |
| Deploy `kserve`/`triton` | ❌ not mentioned | — |
| Chat `--base/--top-p/--safety/--load` | ❌ not mentioned | — |
| Ingest `--format/--language/--include/--exclude/--pii-locale` | ❌ not mentioned | — |
| Chat `/load /top_p /max_tokens /safety` | ❌ not mentioned | — |
| Export `q6_k` / `fp16` quant | ❌ not mentioned | — |
| `ingestion.retention` config | ⚠️ `RetentionConfig` planned in Faz 21 | Wave 2 |
| `FORGELM_RESUME_TOKEN` | ❌ not mentioned | — |
| `FORGELM_CACHE_DIR` | ❌ not mentioned | — |

---

## Roadmap Directory Status Summary

Searched all files in `docs/roadmap/` (`completed-phases.md`, `releases.md`, `risks-and-decisions.md`, `phase-10-5-quickstart.md`, `phase-10-post-training.md`, `phase-11-5-backlog.md`, `phase-11-data-ingestion.md`, `phase-12-5-backlog.md`, `phase-12-data-curation-maturity.md`, `phase-13-pro-cli.md`, `phase-14-pipeline-chains.md`).

**Findings:**
- `forgelm pro` subcommand group: ✅ explicitly in `phase-13-pro-cli.md` as v0.6.0 Pro CLI tier (gated on ≥1K PyPI installs + ≥2 paying contracts)
- `forgelm trend` + `forgelm compare-runs`: contextually belong to `phase-13-pro-cli.md` "Web dashboard — experiment browser" (task 2) but are NOT explicitly named there
- All others: not found in any roadmap file

---

## Prioritized Action Recommendations

### Tier 1 — No-code fixes (naming/alias corrections only)

| ID | Action | Effort | Files |
|---|---|---|---|
| GH-008 | Rename `verify-log` → `verify-audit` in docs (no code change needed) | XS | 4 files |
| GH-011 | Correct `benchmarks.md` — replace `forgelm benchmark ...` with `forgelm --config ... --benchmark-only PATH` | XS | 2 files |
| GH-016 | Rename `--export-bundle` → `--compliance-export` in QMS SOPs | XS | 2 files |
| GH-022 | Fix export quant in cli.md: `q6_k` → remove; `fp16` → `f16` | XS | 1 file |
| GH-019 | Fix chat flags in cli.md: remove `--base`, `--top-p`, `--safety`, `--load`; add `--max-new-tokens` | XS | 1 file |
| GH-020 | Fix ingest flags in cli.md: `--max-tokens` → `--chunk-tokens`; `--pii-locale` → `--pii-ml-language`; remove `--format`, `--language`, `--include`, `--exclude`; fix `--strategy` choices | S | 1 file |
| GH-021 | Fix chat slash commands in cli.md: remove `/load`, `/top_p`, `/max_tokens`, `/safety` | XS | 1 file |
| GH-018 | Fix deploy targets in cli.md: remove `kserve`, `triton` | XS | 1 file |
| GH-017 | Remove `--estimate-cost` from cli.md flags table (or add "planned v0.6.0" note) | XS | 1 file |
| GH-024, GH-025 | Remove `FORGELM_RESUME_TOKEN` and `FORGELM_CACHE_DIR` from env table in cli.md | XS | 1 file |

### Tier 2 — Implement or remove before v0.5.5 ships

Documenting non-existent commands violates the "documentation drift" principle from CLAUDE.md. For each, decide: implement or remove.

| ID | Command | Implement complexity | Remove complexity |
|---|---|---|---|
| GH-007 | `forgelm approvals` | XS — scan staging dirs + audit log for unresolved events; builds on Faz 9 plumbing | S — 6 files |
| GH-004 | `forgelm verify-annex-iv` | S — read JSON, check required Annex IV fields, re-hash | S — 4 files |
| GH-001 | `forgelm doctor` | M — Python/torch/CUDA/GPU/deps check; `--offline` variant | L — 38 refs across 10 files, re-write getting-started flow |
| GH-023 | `ingestion.retention` config | M — implement `RetentionConfig` Pydantic model + add `ingestion` top-level key to `ForgeConfig` (Faz 21 dependency) | S — 2 files |

### Tier 3 — Add to closure plan as named phases

These represent real user value but are clearly out of v0.5.5 scope. Until implemented, remove from usermanuals or add a "planned" callout.

| ID | Command | Natural home |
|---|---|---|
| GH-002, GH-003 | `cache-models`, `cache-tasks` | New phase — "Air-gap pre-cache commands" |
| GH-005 | `safety-eval` | New phase — "Standalone safety-eval subcommand" |
| GH-009 | `verify-gguf` | Add to Faz 28 or new minor phase |
| GH-006, GH-010 | `trend`, `compare-runs` | Phase 13 Pro CLI scope (already planned, add explicit names) |
| GH-012 | `batch-chat` | Add to `forgelm chat` as `--batch` flag or Phase 13 |
| GH-014 | `reverse-pii` | New phase (GDPR follow-up to Faz 21) |
| GH-015 | `merge-sweep` | Phase 14 pipeline chains or new phase |

**Until implemented:** Remove from usermanuals or add:
```markdown
> **Note:** This command is planned for a future release and not yet available in v0.5.5.
```

---

## Affected Files by Ghost

Quick reference for cleanup or implementation work:

```text
GH-001 (doctor):
  docs/usermanuals/en/getting-started/installation.md:100,103,111
  docs/usermanuals/en/getting-started/first-run.md:12,29,32,41
  docs/usermanuals/en/operations/troubleshooting.md:8,168,173,179
  docs/usermanuals/en/operations/air-gap.md:115,124,148
  docs/usermanuals/en/reference/cli.md:15
  docs/usermanuals/tr/* (mirrors of all above)

GH-002 (cache-models):
  docs/usermanuals/en/operations/air-gap.md:25,54
  docs/usermanuals/en/operations/docker.md:101,104
  docs/usermanuals/en/reference/cli.md:28
  docs/usermanuals/tr/* (mirrors)

GH-003 (cache-tasks):
  docs/usermanuals/en/operations/air-gap.md:30,101
  docs/usermanuals/en/operations/docker.md:107
  docs/usermanuals/en/reference/cli.md:29
  docs/usermanuals/en/reference/yaml-templates.md:315
  docs/usermanuals/tr/* (mirrors)

GH-004 (verify-annex-iv):
  docs/usermanuals/en/compliance/annex-iv.md:137,144
  docs/usermanuals/en/operations/troubleshooting.md:155
  docs/usermanuals/en/reference/cli.md:25
  docs/usermanuals/tr/* (mirrors)

GH-005 (safety-eval):
  docs/usermanuals/en/evaluation/safety.md:76,91
  docs/usermanuals/en/deployment/gguf-export.md:136
  docs/usermanuals/en/reference/cli.md:20
  docs/usermanuals/tr/* (mirrors)

GH-006 (trend):
  docs/usermanuals/en/evaluation/trend-tracking.md:80,107
  docs/usermanuals/en/reference/cli.md:30
  docs/usermanuals/tr/* (mirrors)

GH-007 (approvals):
  docs/usermanuals/en/compliance/human-oversight.md:131,138
  docs/usermanuals/en/reference/cli.md:33
  docs/usermanuals/tr/* (mirrors)

GH-008 (verify-log → verify-audit):
  docs/usermanuals/en/compliance/audit-log.md:59,65
  docs/usermanuals/en/reference/cli.md:26
  docs/usermanuals/tr/* (mirrors)

GH-009 (verify-gguf):
  docs/usermanuals/en/deployment/gguf-export.md:80
  docs/usermanuals/en/reference/cli.md:27
  docs/usermanuals/tr/* (mirrors)

GH-010 (compare-runs):
  docs/usermanuals/en/operations/experiment-tracking.md:116
  docs/usermanuals/en/evaluation/trend-tracking.md:116
  docs/usermanuals/tr/* (mirrors)

GH-011 (benchmark wrong form):
  docs/usermanuals/en/evaluation/benchmarks.md:71
  docs/usermanuals/en/reference/cli.md:19
  docs/usermanuals/tr/* (mirrors)

GH-012 (batch-chat):
  docs/usermanuals/en/deployment/chat.md:133
  docs/usermanuals/en/reference/cli.md:22
  docs/usermanuals/tr/* (mirrors)
```

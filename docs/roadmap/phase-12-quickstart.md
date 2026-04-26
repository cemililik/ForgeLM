# Phase 10.5: Quickstart Layer & Onboarding

> **Status:** ✅ **DONE** — shipped in `v0.4.5` (2026-04-26). Module: [`forgelm/quickstart.py`](../../forgelm/quickstart.py); five bundled templates under [`forgelm/templates/`](../../forgelm/templates/); CLI: `forgelm quickstart <template>`; tests: [`tests/test_quickstart.py`](../../tests/test_quickstart.py); CI smoke in [nightly.yml](../../.github/workflows/nightly.yml).

> **Note:** This file details a single phase. For a summary of all phases, see [../roadmap.md](../roadmap.md).
> **Filename:** `phase-12-quickstart.md` — name retained from the original Phase 12 ordering; content corresponds to Phase 10.5.

**Goal:** Make "my first fine-tune" a 10-minute experience. One command, one model in the end, zero YAML writing. Without sacrificing the CI/CD-native core — quickstart generates a YAML the user can later customize.
**Estimated Effort:** Medium (1-2 months) — **Actual: 1 week**
**Priority:** Critical — community flywheel; directly drives EU AI Act enterprise pipeline

> **Phase ordering rationale:** Reprioritized from Phase 12 to Phase 10.5. Quickstart is the primary community growth driver; stars → enterprise leads → compliance sales. EU AI Act enforcement (August 2, 2026) creates a closing window. This phase must ship before Data Ingestion (Phase 11).

> **Context:** Strategic decision documented in the [enterprise-vs-simple paradox analysis](../marketing/strategy/01-paradoks-enterprise-vs-sade.md): ForgeLM adds a "Layer 0" entry point without changing its CI/CD-native identity. The same YAML schema, the same trainer, the same outputs — just wrapped in pre-built templates and opinionated defaults. Depends on Phase 10 (`chat`) for end-of-training sanity loop.

### Tasks:

1. [x] **`forgelm/quickstart.py` + `forgelm quickstart <template>` CLI**
   Takes a template name, optional model override, optional dataset override. Generates a `my_run.yaml` under `./configs/` and immediately invokes `forgelm --config ./configs/my_run.yaml`. On completion, auto-invokes `forgelm chat` unless `--no-chat` flag. Transparent about what it did — prints generated YAML path.
   ```bash
   forgelm quickstart customer-support
   forgelm quickstart code-assistant --model Qwen/Qwen2.5-Coder-7B-Instruct
   forgelm quickstart --list
   ```

2. [x] **Template library: `forgelm/templates/` + bundled sample datasets**
   Initial five templates, each = YAML config + sample JSONL (100-500 examples, license-clean):
   - `customer-support` (Qwen/Qwen2.5-7B-Instruct primary, HuggingFaceTB/SmolLM2-1.7B-Instruct fallback, 58 examples, QLoRA r=8, ~15 min on RTX 3060)
   - `code-assistant` (Qwen/Qwen2.5-Coder-7B-Instruct primary, Qwen/Qwen2.5-Coder-1.5B-Instruct fallback, 59 examples, QLoRA, ~25 min)
   - `domain-expert` (Qwen/Qwen2.5-7B-Instruct primary, HuggingFaceTB/SmolLM2-1.7B-Instruct fallback, BYOD — no bundled dataset)
   - `medical-qa-tr` (Qwen/Qwen2.5-7B-Instruct primary, Qwen/Qwen2.5-1.5B-Instruct fallback, 49 TR examples; Turkish-language flagship)
   - `grpo-math` (Qwen/Qwen2.5-Math-7B-Instruct primary, Qwen/Qwen2.5-Math-1.5B-Instruct fallback, 40 prompts with gold_answer field, GRPO with built-in format+correctness reward, ~45 min)
   Each template must produce a working model on an 8-12 GB consumer GPU. `fit_check` integration: if GPU too small, quickstart auto-downsizes model choice.

3. [x] **Conservative default policy for quickstart**
   All templates ship with: QLoRA 4-bit NF4, rank=8, batch=1 with gradient accumulation, gradient checkpointing on, safety eval off (opt-in only), compliance artifacts off (opt-in only). Rationale: minimize "GPU OOM on first run" and "compliance scared me off" failure modes.

4. [x] **Wizard integration — template selector first**
   `forgelm --wizard` opens with "Start from a template?" question. If yes → pass to quickstart flow. If no → existing 10-question flow. Merges the two paths.

5. [x] **End-to-end smoke test in CI**
   Nightly CI runs: `forgelm quickstart customer-support --dry-run` for each template. Validates YAML generation + dataset parse + config validation. No GPU required (dry-run). Catches template drift early.

### Requirements:
- Sample datasets must be license-clean (CC-BY-SA 4.0 or similar permissive, documented in `forgelm/templates/LICENSES.md`).
- Each template has a companion YouTube video (scheduled in marketing roadmap, not this roadmap).
- Templates are a foundation for community contributions: `CONTRIBUTING.md` should document how to add new templates; each template is an atomic PR.
- Quickstart must not introduce a "quickstart vs real training" bifurcation — same underlying code paths, same YAML schema.

### Delivery:
- Target release: `v0.4.5` ("Quickstart Layer")
- Blocks on Phase 10 tasks 1 + 2 (`inference.py` and `chat.py`). Phase 10 tasks 3-5 (export, fit-check, deploy) can develop in parallel.

---

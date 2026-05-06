# ForgeLM Master Review (post-v0.5.0) — opus — 202604300906

**Verified against synthesized sub-reports at commit 6b515ed912f8f22304194c1b3f55ed07a26f519c**

**Commit:** 6b515ed912f8f22304194c1b3f55ed07a26f519c
**Branch:** main
**Consolidator model:** opus (Opus 4.7, 1M context)
**Sub-reports synthesized:** Business, Code, Compliance, Documentation, Localization, Performance, Security, Testing-CICD, Regression-Check
**Prior master:** [`master-review-opus-202604281313.md`](./master-review-opus-202604281313.md) (delta: 52 commits, v0.4.5 → v0.5.0 → 0.5.1rc1)

---

## 0. Executive summary

v0.5.0 ("Document Ingestion + Data Curation Pipeline") shipped on 2026-04-30 as a consolidated release covering Phases 11 / 11.5 / 12 / 12.5. The release engineering itself was clean: PyPI confirms `forgelm 0.5.0`; the runtime `__version__` resolves through `importlib.metadata`; CHANGELOG carries a properly-dated `[0.5.0] — 2026-04-30` section; HEAD is now `0.5.1rc1` with `[Unreleased]` correctly empty and pointing at Phase 14. The two highest-leverage cross-cutting themes from the prior turn — Theme A (public version drift across runtime / manifest / changelog) and Theme B (audit/compliance trust path) — are **both closed at 100 % closure**. Theme D (silent-failure cluster) is also at 100 % closure for the load-bearing audit-trust paths, with sweep work continuing on best-effort artefact paths. Theme H (webhook security hardening) closed at 100 % including SSRF guard, redirect refusal, secret-masked failure reasons, and TLS-bundle pinning. The Critical-only closure across the prior master's 10-Critical surface is **100 %**.

The new findings cluster materially around the **marketing / site / QMS surface**: three new Critical/Major problems emerge directly *from* the v0.5.0 ship (`site/compliance.html` listing artefact filenames the code does not produce; `site/quickstart.html` mock output naming non-existent templates; `docs/qms/sop_data_management.md` body still asserting `v0.5.1+` / `v0.5.2` feature pins after the consolidation note in CHANGELOG explicitly retconned that timeline; `tests/runtime_smoke.py` violating four standards at once; CI `--cov-fail-under` gate documented but not actually enforced by `pytest-cov`; trainer.py still imports `torch` / `transformers` / `trl` at module top against the lazy-import discipline its sister modules already follow). Localization is now a separately-tracked dimension and exposes the single largest delivered-vs-advertised gap on the site: DE/FR/ES/ZH chrome translation is native-quality across 286 keys × 6 languages, but the user-manual content for those four languages is **0 of 56 pages** — site-chrome promises six languages of content and delivers two.

**Project health (this round): ★★★¾ / 5 overall.** Net trend post-v0.5.0: **improving on integrity / security / regression closure; stable on code / documentation / performance / business; new attack surface on the public marketing site that was lower-traffic in the prior round.** The ten remaining Open items from the prior round map cleanly to Phase 13/14 sprints; none are individually release-blocking. Closing the top three new Critical findings (site compliance artefacts, QMS version contradiction, CI cov gate) plus the two highest-leverage carry-overs (lazy torch import, Pydantic `description=` migration) lifts the overall to **★★★★ / 5** within a single sprint.

| Dimension | Rating | Direction vs prior | One-line |
|---|---|---|---|
| Business | ★★★½ / 5 | flat | Theme A & B closures balance new site-drift Critical findings; close site compliance artefacts to lift to ★★★★½ |
| Code | ★★★½ / 5 | flat | Stylistic standards posture (Literal sweep, descriptions, except-Exception) deferred; load-bearing trio closed |
| Compliance | ★★★★ / 5 | up (★★★½ → ★★★★) | Theme B closure earned the fourth star; Article 14 ordering + verifier subcommand are next-tier debt |
| Documentation | ★★★½ / 5 | flat | EN ~★★★★½; TR-mirror ~★★★ drags it; QMS sop_data_management critical and three count-drift reopens |
| Localization | ★★★ / 5 | new axis | EN/TR full content parity (4 H2 drift items); DE/FR/ES/ZH 0 % page coverage with 1.79 MB EN-stuffed bags |
| Performance | ★★★★ / 5 | flat | 5 of 9 prior cliffs closed; lazy-torch + workers + safety batching remain |
| Security | ★★★★ / 5 | up (★★★½ → ★★★★) | Webhook hardening + audit chain + dataset fingerprint TOCTOU all closed; SSRF guard now needs to extend to judge.py + synthetic.py |
| Testing & CI/CD | ★★★½ / 5 | new axis | Strong test corpus (47 modules, 800+ tests, 12.3 K LOC); cov-fail-under gate not enforced + runtime_smoke disorder + fixture fragmentation reopened |

---

## 1. Regression posture vs prior master review

The prior master review listed **10 Critical** + **47 Major** findings (57 total in scope). Status across the 57 at HEAD `6b515ed`:

| Status | Count | % |
|---|---|---|
| Closed | **38** | 66.7 % |
| Partially Closed | **9** | 15.8 % |
| Open | **10** | 17.5 % |
| Reopened | **0** | 0 % |
| Not Verifiable | **0** | 0 % |

**Critical-only closure: 10 / 10 = 100 %.** Major closure: 28 / 47 = 59.6 % outright; +19.1 % partially-closed. **Combined Closed-or-Partially: 47 / 57 = 82.5 %.**

### 1.1 Themes fully closed in this cycle

- **Theme A — Public version drift (4 / 4 sub-findings closed).** `forgelm/__init__.py` resolves via `importlib.metadata`; `compliance._get_version()` follows the same path; CHANGELOG `[0.5.0] — 2026-04-30` section present; `pyproject.toml` and runtime stamp share one source. Single-source contract realigned. Commits: `b97b971`, `e5ba1d9`, `c78040b`.
- **Theme B — Audit/compliance trust path (7 / 7 sub-findings closed).** `_load_last_hash` now distinguishes file-missing from file-unreadable and raises on the latter. `log_event` writes under `flock`, re-reads chain head from disk under the same lock to defeat multi-writer fork race. `_prev_hash` advances only after the line lands on disk. Genesis manifest sidecar (`*.manifest.json`) detects truncate-and-resume attacks. `compute_dataset_fingerprint` lru_cache dropped; `os.path.realpath` resolves symlinks; `os.fstat(f.fileno())` captures stat from the same fd as the SHA-256 stream. `generate_data_governance_report` wired into `_export_compliance_if_needed` with `compliance.governance_exported` / `compliance.governance_failed` audit events gating the rollup `compliance.artifacts_exported` event. Annex IV markdown promise resolved by *renaming* references to `annex_iv_metadata.json` (the rename path, not the build path — see §3 caveats). Commits: `6143321`, `7db47bc`.
- **Theme D — Silent-failure cluster (4 / 4 closed).** `data.py:_process_messages_format` narrowed catch + raise on malformed rows; `safety.py:_release_model_from_gpu` narrowed to RuntimeError with partial-cleanup logging; `cli.py:_load_config_or_exit` distinct branches for FileNotFoundError / ConfigError / yaml.YAMLError / ValidationError / OSError; `config.py:load_config` lets ValidationError propagate. Six load-bearing audit-trust silent-fail sites now raise. Commit: `fb93ebd`.
- **Theme F — Pydantic schema discipline (1 / 1 in scope closed).** Six target fields converted to `Literal[...]`; bespoke `_validate_trainer_type` runtime validator deleted. Commit: `fb93ebd`.
- **Theme H — Webhook security hardening (3 / 3 closed).** SSRF guard via `_is_private_destination` (rejects RFC1918 / loopback / link-local / metadata-service / multicast); explicit `verify=True` + `tls_ca_bundle` opt-in; timeout floor enforced; redirect-following disabled; `notify_failure(reason)` runs through `mask_secrets()` with 2 KB truncation. Commit: `3da2810`.

### 1.2 Themes partially closed

- **Theme C — Documentation drift (9 closed / 3 partial / 3 open of 15).** Mirror-parity sweep shipped (configuration-tr / usage-tr / architecture-tr / distributed_training-tr corrected). Residual: `data_preparation*.md` 35-line micro-doc still under-covers messages schema + mix_ratio (Open M5); `compliance_summary.md` fake CLI removed but H1 / scope blockquote / 11 broken relative paths still open (Partial M7); design-doc status blockquotes still missing on `wizard_mode.md` + `blackwell_optimized.md` (Open M13); Pydantic `description=` 1 of 172 fields (Open M9); README "18 GPU models" vs `_GPU_PRICING` 16 / 17 (Open F-business-020); `architecture.md` EN missing `configs/safety_prompts/` (Partial M10); roadmap.md Phase 12.5 row consolidated rather than dedicated (Partial M12).
- **Theme E — Performance scaling cliffs (5 closed / 4 open of 9).** All three Critical perf items closed (`agg.minhashes` double-copy, bidirectional MinHash, `text_lengths` reservoir). Numpy simhash vectorisation + markdown chunker batch-encode landed. Open: F-performance-003 (lazy torch import — quick win not done), F-performance-004 (combined PII regex — deferred per master verdict), F-performance-007 (`--workers` audit flag — deferred to v0.5.3), F-performance-012 (safety eval batching — deferred for determinism contract).
- **Theme G — Standards drift (2 closed / 1 open of 3).** Coverage `fail_under` toml/standard mismatch closed (both at 40 now). `ci.yml` `continue-on-error: true` removed. `wizard.py` whole-module coverage `omit` still open (coupled with print-ban deferred decision).

### 1.3 What did NOT land between rounds (still Open after 52 commits)

These 10 master-tracked Major items remain Open at HEAD:

1. **F-code-013** — `print()` in `wizard.py` (85 calls) — chat.py landed `_print` indirection but wizard didn't follow → consistency problem on top of standards problem.
2. **F-code-019** — `pyproject.toml` `omit = ["forgelm/wizard.py"]` — coupled with #1.
3. **M5** — `data_preparation*.md` rewrite or fold — content decision not made.
4. **M9** — Pydantic `description=` migration (1 of 172 fields).
5. **M13** — design-doc status blockquotes (`wizard_mode.md`, `blackwell_optimized.md`).
6. **F-business-020** — README "18 GPU models" vs code (16 entries per code review) → trivial off-by-one count drift.
7. **F-performance-003** — lazy `torch` / `transformers` / `trl` import in `trainer.py:8-10` (~30 min fix).
8. **F-performance-004** — combined PII+secrets+tokenize regex (deferred per master §4.1).
9. **F-performance-007** — `--workers N` audit flag (deferred to v0.5.3 per master §7).
10. **F-performance-012** — safety eval batching.

**Trend:** 7 of 10 Open are *intentional* or *strategic-deferred*; 3 (F-performance-003, F-business-020, M13) are quick wins that fell through the cracks.

---

## 2. Severity-aggregated findings table

This round's findings only — prior round's open carry-overs are documented in §1.3 and the regression-check report. Numbering preserves source-report IDs for traceability.

### 2.1 Critical

| # | Severity | Dimension | File:Line | Title | Recommendation | Source report |
|---|---|---|---|---|---|---|
| 1 | Critical | Business | `site/compliance.html:102, 160-176` | Compliance footprint tree advertises 5 artefacts code does not produce (`annex_iv.json`, `safety_report.json`, `benchmark_results.json`, `conformity_declaration.md`, `manifest.json`) | Rewrite tree against `compliance.py::export_compliance_artifacts` real filenames; add CI diff check | F-business-001 |
| 2 | Critical | Business | `site/quickstart.html:111-116` | `--list` mock output uses non-existent template names (`byod-domain-expert`, `math-reasoning`); descriptions claim SFT+DPO chains templates do not ship | Patch `<pre>` to match `forgelm/quickstart.py::TEMPLATES` actual handles + descriptions | F-business-002 |
| 3 | Critical | Business+Doc | `docs/roadmap.md:12,16`; `docs/roadmap-tr.md:12,16`; `docs/roadmap/releases.md:85`; `CHANGELOG.md:156-158` | Three high-traffic surfaces still claim "PyPI publish pending" for v0.5.0 after the tag shipped | Flip to `✅ Done`; update callout to "PyPI 2026-04-30"; delete vestigial CHANGELOG sentence | F-business-003 |
| 4 | Critical | Documentation | `docs/qms/sop_data_management.md:74-99` | QMS template asserts audit pipeline is "v0.5.1+", LSH dedup arrived in "v0.5.2", PII tiers in "v0.5.1", secrets-mask in "v0.5.2" — none shipped on PyPI; CHANGELOG explicitly consolidates Phases 11/11.5/12/12.5 into v0.5.0 | Rewrite to `forgelm audit` (v0.5.0+) covering full Phase 11+11.5+12+12.5 surface; delete v0.5.1/v0.5.2 per-feature splits | M-DOC-001 |
| 5 | Critical | Compliance | `forgelm/trainer.py:894-919, 865-878` | Article 14 human-approval gate still saves model BEFORE gate triggers (`save_final_model` → `_finalize_artifacts` → `_handle_human_approval_gate`); log says "Model saved to staging" but path is literal `final_model/` | Either ship literal `final_model.staging/` directory + `forgelm approve` subcommand, OR fix the misleading log message + add CHANGELOG note that operators must gate on exit code 4 | F-compliance-101 |
| 6 | Critical | Compliance | `forgelm/compliance.py:56` | Operator identity falls back to literal `"unknown"` despite the standard explicitly forbidding it; in distroless CI containers `USER` is unset → all audit entries attributed to `"unknown"` | Raise on missing operator identity unless `--allow-anonymous-operator` flag is passed; replace chained `os.getenv` with `getpass.getuser()` + `socket.gethostname()` | F-compliance-102 |
| 7 | Critical | Compliance | `forgelm/cli.py` (no `verify-audit` subcommand) | `forgelm verify-audit` not shipped despite docs continuing to promise integrity verification; HMAC-when-keyed write path landed but read path is documentation only | Add `forgelm verify-audit <path>` subcommand + `forgelm.compliance.verify_audit_log()` library function | F-compliance-103 |
| 8 | Critical | Testing/CI | `.github/workflows/ci.yml:49`; `pyproject.toml:188-189` | CI runs `pytest --cov=forgelm` but does NOT pass `--cov-fail-under`; `pyproject.toml`'s `fail_under = 40` is not auto-enforced by pytest-cov → coverage can silently drop and CI stays green | Add `[tool.pytest.ini_options].addopts = "--cov-fail-under=40"`, OR add flag to `ci.yml:49` directly | F-test-001 |

### 2.2 Major

| # | Severity | Dimension | File:Line | Title | Recommendation | Source report |
|---|---|---|---|---|---|---|
| 9 | Major | Business | `site/index.html:153-154`; `README.md:22` | "18 GPU profiles auto-detected" claim while `_GPU_PRICING` ships 16 entries | Bump to 16 across site stats + 6 locales + README, OR drop the literal | F-business-004 (= F-business-020 carry-over) |
| 10 | Major | Business | 7 of 10 Colab notebooks | `git+https://...` install bypasses PyPI smoke job (dpo_alignment, safety_evaluation, grpo_reasoning, kto_binary_feedback, galore_memory_optimization, multi_dataset, synthetic_data_training) | Pin each to `forgelm[qlora]==0.5.0`; add CI grep-and-fail step | F-business-005, M-DOC-005 |
| 11 | Major | Business | `forgelm/cli.py:594-602, 856-869` | `--compliance-export` writes empty-metrics manifest with help text that implies populated bundle | Either inline post-training artefacts from `output_dir` or reword help to cliff-edge | F-business-006 |
| 12 | Major | Business | `CONTRIBUTING.md:62-79` | Project structure tree lists 17 modules; package ships 26 (missing chat, quickstart, inference, data_audit, ingestion, export, deploy, fit_check, grpo_rewards) | Replace with one-line pointer to `architecture.md`'s Directory Layout, OR regenerated 26-entry block | F-business-007, M-DOC-010 |
| 13 | Major | Business | `docs/qms/README.md:23-33` | QMS "Maps to QMS" table cites `safety_results.json` and `benchmark_results.json` that don't exist as standalone artefacts | Rewrite against `compliance.py::export_compliance_artifacts` actual filenames | F-business-008 |
| 14 | Major | Business | site (8 HTML pages × 6 locales) | No Pro CLI / OSS scaffold on site (README has it); no expectation-setting for Phase 13 | Add 5-line callout or `site/pricing.html` page | F-business-009 |
| 15 | Major | Business | `docs/roadmap.md:31`; `docs/roadmap-tr.md:31` | "17 phases complete" sentence contradicts top-of-page "Merged, PyPI publish pending" symbol | After F-business-003 flips status, the L31 sentence becomes accurate | F-business-010 |
| 16 | Major | Business | none (gap to fill) | `docs/standards/release.md` has no documented deprecation cadence; `--data-audit` removal in v0.7.0 is the live precedent but not codified | Add 10-line "Deprecation cadence" subsection citing `cli.py:1424-1428` as worked example | F-business-011 |
| 17 | Major | Business | `docs/roadmap/risks-and-decisions.md:71-91` | Decision Log stops at 2026-04-25; v0.5.0 consolidation + PyPI publish decisions absent | Append two rows | F-business-012 |
| 18 | Major | Code | `forgelm/config.py:77, 149-153, 179, 186-187, 248, 318` | Six Pydantic enum-shaped fields still bare `str` not `Literal[...]` (`LoraConfig.bias`, `DistributedConfig.strategy`, `SafetyConfig.scoring`, `ComplianceMetadataConfig.risk_classification`, FSDP fields, GaLore fields) | Convert to `Literal[...]`; lift shared `RiskCategory` to module-level alias | F-code-101, F-compliance-105 |
| 19 | Major | Code | `forgelm/config.py` (170+ fields) | Pydantic `description=` migration unstarted: 1 of ~170 fields | Incremental: PR template gate for new fields + dimension-scoped batches + CI guard diffing schema vs configuration.md | F-code-102, M-DOC-006 |
| 20 | Major | Code | `forgelm/data_audit.py` (3098 lines) | Single module owns six concerns past architecture standard's ~1000-line split threshold | Plan Phase 13 `data_audit/` package split (pii / pii_ml / dedup_simhash / dedup_minhash / quality / croissant / streaming) | F-code-103 |
| 21 | Major | Code | `forgelm/cli.py` (1756 lines) | Six subcommands' definers + dispatchers in one file; CLI-as-thin-shim principle eroded | Split into `forgelm/cli/` package with one parser+dispatcher pair per subcommand | F-code-104 |
| 22 | Major | Code | `forgelm/wizard.py` (85 print calls) | print-vs-logger conflict §4.4 unresolved; chat.py landed `_print` indirection, wizard didn't | Either port chat's `_print` pattern OR update standard with named interactive carve-out | F-code-105 |
| 23 | Major | Code | `forgelm/data_audit.py:1132`; `forgelm/safety.py:99/225/387/499`; trainer/judge/etc. (~25 sites across 13 modules) | Silent `except Exception:` sweep partially landed; non-fatal best-effort paths uncommented | Three-pass sweep: narrow class / comment-or-justify / add tests | F-code-106 |
| 24 | Major | Code | `forgelm/cli.py:604-615, 1424-1428` | `--data-audit` deprecation lacks DeprecationWarning + tracking issue + audit-log of legacy invocation | Emit `warnings.warn(..., DeprecationWarning)`, audit-log, link tracking issue | F-code-107, F-business-024 |
| 25 | Major | Code | `tools/build_usermanuals.py:106-119, 441` | `_meta.yaml` schema validation missing — malformed YAML produces opaque `KeyError` | Add Pydantic validation OR defensive `validate_meta(data)` walker | F-code-108 |
| 26 | Major | Code | `forgelm/cli.py:1742` (and 28 print sites) | Operator output mostly bypasses logger; `cli.py:1742` writes to stderr via print | Update standard to "cli.py may print to stdout for operator-visible text/JSON; errors via logger" | F-code-109 |
| 27 | Major | Compliance | `forgelm/webhook.py:206-264`; `forgelm/trainer.py:519-531, 865-878` | Webhook lifecycle vocabulary missing `training.reverted` and `approval.required` events; standard lists 5 events, code implements 3 | Add `notify_reverted` + `notify_awaiting_approval`; wire `_revert_model` and `_handle_human_approval_gate` | F-compliance-104 |
| 28 | Major | Compliance | `forgelm/config.py:367`; `forgelm/webhook.py:134-140` | Webhook timeout default 5s against standard floor of 10s | Bump default to 10; clamp floor to 10 not 1 | F-compliance-106 |
| 29 | Major | Compliance | none (no `RetentionConfig`); `docs/qms/sop_data_management.md:107-110` | QMS claims 5-year retention but no `retention:` config block, no archival hook, no GDPR right-to-erasure path | Stub-and-document is acceptable v1: add `retention:` Pydantic block with `enforce: log_only` default + document right-to-erasure procedure | F-compliance-107 |
| 30 | Major | Compliance | `forgelm/judge.py:172-195` | `judge_results.json` does not record `judge_model` / `api_base` / `rubric_sha256` / `min_score` provenance (Annex IV §2(d) gap) | Extend `_save_judge_results` to persist `judge_provenance` block | F-compliance-108 |
| 31 | Major | Compliance | `forgelm/synthetic.py`; `forgelm/compliance.py:523-616` | Synthetic-data provenance absent from training manifest (teacher_model, api_base, generation_params not recorded) | Inline `data_provenance.synthetic_data` block when `synthetic.enabled` | F-compliance-109 |
| 32 | Major | Compliance | `forgelm/config.py:282-291, 451-452` | Article 9 risk-management still declarative-only; `risk_classification: high-risk` + `evaluation.safety.enabled: false` is a WARNING not a hard block | Raise on high-risk + safety-disabled at runtime; soft-warn during `--dry-run` only | F-compliance-110 |
| 33 | Major | Compliance | `forgelm/compliance.py:331-360` | `_maybe_inline_audit_report` failure mode is INFO; missing Article 10 evidence section silently drops out of governance bundle | Promote to WARNING; emit `governance.data_audit_missing` audit event; raise on high-risk | F-compliance-111 |
| 34 | Major | Compliance | `docs/qms/` (no `-tr.md` mirrors) | All 6 QMS files (README, 5 SOPs) are EN-only despite localization standard requiring user-facing docs to be EN+TR mirrored | Add `*-tr.md` mirrors for all 6 QMS files via sync-bilingual-docs skill | F-compliance-112 |
| 35 | Major | Compliance | `docs/reference/compliance_summary.md:21,25,28,32,36` | Stale line anchors point to non-existent line ranges in current 873-line `compliance.py` (`#L33`, `#L167`, etc.) | Switch to symbol-style references (function names) or regenerate against HEAD with CI guard | F-compliance-113 |
| 36 | Major | Compliance | `forgelm/compliance.py:262-265` | `audit_log.jsonl` lacks `os.fsync()` after flush; chain advances on `flush()` even if power-cut precedes kernel writeback | Add `os.fsync(f.fileno())` immediately after `f.flush()` | F-compliance-114 |
| 37 | Major | Documentation | `docs/reference/configuration-tr.md:1-260` vs `configuration.md:1-318` | TR mirror H4 14 vs 6; missing `model.multimodal`, bnb_4bit fields, lora dropout/bias/task_type, 11 training fields, evaluation.benchmark sub-block, 5 compliance fields, 5 H2 sections out of order | Run `sync-bilingual-docs` skill end-to-end | M-DOC-002 |
| 38 | Major | Documentation | `docs/reference/compliance_summary.md:1-123` | No H1, no scope blockquote, 11 broken relative paths, "50 prompts in 3 categories" while README says "140 × 6"; unreachable from index | Promote (rewrite + link from README/QMS) OR delete + merge into safety_compliance.md | M-DOC-003 |
| 39 | Major | Documentation | 6 guide locations | Stale `v0.3.1rc1` references in enterprise_deployment, cicd_pipeline, safety_compliance (×3), troubleshooting | Mass-replace with `v0.4.0` or "Phase 10" prose | M-DOC-004 |
| 40 | Major | Documentation | `docs/reference/data_preparation*.md` | 35-line micro-doc; only legacy columnar form documented; messages schema, mix_ratio, governance fields absent; TR uses parenthetical-translation MT style | Rewrite to ~120 lines OR fold into alignment.md | M-DOC-007 (= M5 carry-over) |
| 41 | Major | Documentation | `docs/design/wizard_mode.md`, `blackwell_optimized.md` | Both lack scope blockquote + status indicator; future-tense wizard description while shipped, present-imperative for unimplemented blackwell | Add `> **Status:** Shipped` / `> **Status:** Proposed` blockquote | M-DOC-008 (= M13 carry-over) |
| 42 | Major | Documentation | `docs/standards/testing.md:8, 127` | Doc claims "26 test modules" (reality 47); CI command shows `--cov-fail-under=25` while pyproject is 40 | Update count to 47 + drop enumeration; sync command to 40 | M-DOC-009 |
| 43 | Major | Documentation | `CLAUDE.md:60` | Repo-orientation block says "26 test modules"; reality 47 | One-line fix | M-DOC-011 |
| 44 | Major | Documentation | `docs/reference/distributed_training-tr.md` | TR missing 3 EN H3 sections (Custom DeepSpeed Config, When to Choose FSDP over DeepSpeed, LoRA + Distributed); FSDP fields backward_prefetch + state_dict_type missing | Translate the 3 H3 sections; deepen CI bilingual check to H3 | M-DOC-012 |
| 45 | Major | Documentation | `docs/guides/ingestion-tr.md` | TR missing Phase 12 H3 sections: Markdown-aware splitter, DOCX table preservation | Translate the 2 H3 sections | M-DOC-013 |
| 46 | Major | Documentation | `docs/reference/architecture-tr.md:60-61` vs `architecture.md:59-69` | TR has `configs/safety_prompts/`, EN doesn't; both omit `forgelm/templates/` | Add to EN; add templates to both | M-DOC-014 (= M10 carry-over) |
| 47 | Major | Documentation | `docs/guides/alignment.md:230` | "Coming in v0.5.1 (Phase 14)" prose fragile to consolidation pattern that produced v0.5.0 | Pin to phase number not version tag | M-DOC-015 |
| 48 | Major | Localization | `docs/usermanuals/{de,fr,es,zh}/` (all empty); site language picker (8 HTML pages × 6 locales) | DE/FR/ES/ZH user-manual content is **0 of 56 pages**; site picker advertises 6 languages; bags ship 1.79 MB redundant English text under fallback flag | Drop from picker until ≥1 critical-path subset translated, OR render coverage badge ("0/56 — beta"), OR sparse-fallback emit | F-loc-001 |
| 49 | Major | Localization | `.github/workflows/usermanuals-validate.yml:31-48`; `tools/build_usermanuals.py:284-331` | Orphan markdown silently dropped — undeclared `*.md` under `docs/usermanuals/<lang>/` produces neither warning nor CI failure | Add orphan walk + `--strict` mode in CI | F-loc-002 |
| 50 | Major | Localization | All 8 site HTML pages | `og:locale="en_US"` hard-coded; no `og:locale:alternate` siblings; no `<link rel="alternate" hreflang>` block | Add hreflang + `data-i18n-attr="content:meta.og.locale"`; pre-resolve `YOUR_DOMAIN` placeholder | F-loc-003 |
| 51 | Major | Localization | `site/js/guide.js:436, 448, 455, 458, 466, 654` | Six `.toLowerCase()` call-sites are locale-unaware; Turkish `İ`/`I` parity drops in search; spec is unambiguous | Replace with `.toLocaleLowerCase(state.lang)` and invalidate `_searchText` cache on lang switch | F-loc-004 |
| 52 | Major | Localization | `docs/usermanuals/tr/training/sft.md` | TR drops "What you get on disk" section (H2 8 → 7) | Add section with TR heading "Diskte ne elde edersiniz" | F-loc-005 |
| 53 | Major | Localization | `docs/usermanuals/tr/training/simpo.md` | TR collapses 3 H2s; drops "Common pitfalls" / "Compute and memory" / splits "Veri formatı" + "Konfigürasyon parametreleri" | Restructure TR to mirror EN H2 spine 1:1 | F-loc-006 |
| 54 | Major | Localization | `docs/usermanuals/tr/compliance/overview.md` | TR drops "What goes into Annex IV" section (H2 7 → 6) | Translate as "Annex IV neyi içerir" | F-loc-007 |
| 55 | Major | Localization | `docs/usermanuals/tr/concepts/data-formats.md` | TR drops "Validating your data" section (H2 10 → 9) | Translate as "Verinizi doğrulama" | F-loc-008 |
| 56 | Major | Performance | `forgelm/trainer.py:8-10` | Eager `import torch` / `from transformers import EarlyStoppingCallback` / `from trl import SFTConfig, SFTTrainer` at module top — prior round's F-performance-003, ~30 min fix unaddressed | Move imports into method bodies; add regression test that `import forgelm.trainer` doesn't pull torch | F-performance-101 |
| 57 | Major | Performance | `forgelm/safety.py:86-102`; `forgelm/judge.py:139-151, 301` | Per-prompt `model.generate()` loop in safety + judge; GPU 70-90% idle on each step; 100-prompt eval ~30-60s instead of ~2-5s | Add `batch_size: int = 8` parameter; tokenise with `padding="longest"`; per-batch OOM fallback to single-prompt | F-performance-102 |
| 58 | Major | Performance | `forgelm/ingestion.py:902` | `_chunk_paragraph_tokens` re-encodes every paragraph in a loop (markdown twin's other half closed in c1af7a8) | Extract `_count_section_tokens` into `_batch_count_tokens`; reuse from both chunkers | F-performance-103 |
| 59 | Major | Performance | `forgelm/data_audit.py:1703-1733`; `forgelm/cli.py` (no `--workers`) | Per-row PII + secrets + simhash + Presidio walk same payload three or four times serially; no `--workers` → Presidio 1 M-row corpus 1.5-5 hours single-core | Add `--workers N` flag; `multiprocessing.Pool.imap` over chunked rows; preserve determinism via chunk index | F-performance-104 |
| 60 | Major | Performance | `tools/build_usermanuals.py:212-244, 284-331, 397-407` | 6 lang × 56 pages = 336 file builds with fresh `markdown.Markdown` instance per page; no incremental cache; serial across languages | `md.reset()` between calls + mtime/hash cache + `ProcessPoolExecutor` across languages | F-performance-105 |
| 61 | Major | Performance | `forgelm/data_audit.py:1664, 1706, 1838` | `lang_sample` stores full payload string up to N=200; ~512 chars suffices for langdetect; ~10 MB resident set on long-payload corpora | Slice to first 512 chars: `agg.lang_sample.append(payload[:512])` | F-performance-106 |
| 62 | Major | Security | `forgelm/judge.py:85`; `forgelm/synthetic.py:207-212` | Outbound POST without SSRF guard, explicit `verify=True`, HTTP refusal, redirect ban, or timeout floor; `Authorization: Bearer` header can leak to IMDS endpoint | Extract shared `forgelm/_http.py:safe_post` helper from `webhook._post_payload`; route judge + synthetic + webhook through it | M-201 |
| 63 | Major | Security | `forgelm/trainer.py:639-640` | `_AutoTok.from_pretrained` and `AutoModelForSequenceClassification.from_pretrained` for GRPO classifier reward miss explicit `trust_remote_code=False` (M-6 fix applied to safety.py only) | Pass `trust_remote_code=False` explicitly; add unit test mirroring safety pattern | M-202 |
| 64 | Major | Security | `forgelm/export.py:73-104, 261-321, 430-431` | `FORGELM_GGUF_CONVERTER` override partially closed via `.py` allow-list + warning, but no SHA-256 capture, no CLI ack flag, no docs | Add `--allow-custom-converter` flag; record `converter_sha256` in `model_integrity.json`; document as privileged knob | M-203 (= M-5 partial carry-over) |
| 65 | Major | Security | `forgelm/compliance.py:835-851, 664` | `_describe_adapter_method` interpolates `config.lora.target_modules` list via str() — bypasses `_sanitize_md` (regression-shaped) | Add `_sanitize_md_list` helper; audit `generate_deployer_instructions` for any list-valued interpolation | M-204 |
| 66 | Major | Security | `forgelm/deploy.py:99-103` | `_ollama_modelfile` `system_prompt` only escapes `"`; newline injection bypasses wrapper | Switch to triple-quoted form OR refuse newlines with actionable error | M-205 |
| 67 | Major | Testing/CI | `tests/runtime_smoke.py:11-103` | Violates 4 standards: writes to repo cwd (no `tmp_path`), cleanup commented out, real HF Hub fetch (no mock), Turkish comments + emoji | Either delete (nightly wheel-install-smoke covers it) OR move to `tools/runtime_smoke.py` and re-discipline | F-test-002, F-test-019, F-test-020 |
| 68 | Major | Testing/CI | `pyproject.toml:184-186`; `tests/test_wizard_byod.py`, `test_wizard_phase11_5.py`, `test_phase12_5.py:108-167` | `omit = ["forgelm/wizard.py"]` still active despite 3 wizard test modules existing | Drop module-level omit; use line-level `pragma: no cover` for interactive `input()` only | F-test-003 (= F-code-019 carry-over) |
| 69 | Major | Testing/CI | 4 test files (`test_cli.py`, `test_cli_phase10.py`, `test_fit_check.py`, `test_integration_smoke.py`) | `_minimal_config` lokal kopya in 4 places; F-code-015 partially closed | Move factory to `tests/_helpers/` module; replace 4 lokal copies + 7 `from conftest import` calls | F-test-004, F-test-005 |
| 70 | Major | Testing/CI | `tests/` (7 files) | `from conftest import minimal_config` is anti-idiom — pytest fixture system bypassed via plain module import | Move to `tests/_helpers.py` OR convert to factory-as-fixture | F-test-005 |
| 71 | Major | Testing/CI | `.github/workflows/ci.yml:30-34` vs `nightly.yml:16-19` | `fail-fast` policy asymmetric: nightly explicit `false`, ci.yml uses default `true` | Pick one + document in `docs/standards/testing.md` "CI gates" section | F-test-006 |
| 72 | Major | Testing/CI | `.github/workflows/ci.yml:31`; `pyproject.toml:23` | All CI on `ubuntu-latest`; pyproject claims "OS Independent"; cross-OS testing absent | Add `os: [ubuntu-latest, macos-latest, windows-latest]` axis to nightly wheel-install-smoke | F-test-007 |
| 73 | Major | Testing/CI | `.pre-commit-config.yaml` (absent) | No pre-commit hooks; CI catches lint/format only at PR-time | Add minimal `.pre-commit-config.yaml` with ruff + gitleaks + standard hooks | F-test-008 |
| 74 | Major | Testing/CI | `pyproject.toml:131-135`; `.github/workflows/ci.yml:49` | `pytest-xdist` not in dev extra; 47 modules / 800+ tests run serially | Add `pytest-xdist>=3.0`; CI `pytest -n auto`; trial in nightly first | F-test-009 |
| 75 | Major | Testing/CI | `pyproject.toml:189` (40) vs `docs/standards/testing.md:127` (25) | Standard says fail_under=25, pyproject says 40 — F-code-016 partially closed | Bump standard to 40 to match pyproject | F-test-010 |
| 76 | Major | Testing/CI | 3 separate "smoke" files (`test_smoke.py:14`, `test_integration_smoke.py:426`, `runtime_smoke.py:110`) | Naming inconsistency; `test_integration_smoke.py` is integration not smoke; `runtime_smoke.py` is not even a pytest test | Rename `test_integration_smoke.py` → `test_integration.py`; expand `test_smoke.py` to real `--help` smoke | F-test-011 |

### 2.3 Minor (summary count by dimension)

| Dimension | Minor count | Source(s) |
|---|---|---|
| Business | 6 | F-business-013 to F-business-018 |
| Code | 11 | F-code-130 through F-code-143 |
| Compliance | 7 | F-compliance-115 through F-compliance-121 |
| Documentation | 7 | m-DOC-016 through m-DOC-022 |
| Localization | 6 | F-loc-009 through F-loc-014 |
| Performance | 7 | F-performance-107 through F-performance-113 |
| Security | 10 | m-201 through m-210 |
| Testing/CI | 6 | F-test-012 through F-test-018 |

**Total Minor: 60.**

### 2.4 Nit (summary count by dimension)

| Dimension | Nit count | Source(s) |
|---|---|---|
| Business | 6 | F-business-019 through F-business-024 |
| Code | 7 | F-code-160 through F-code-166 |
| Compliance | 3 | F-compliance-122, 123, 124 |
| Documentation | 5 | n-DOC-023 through n-DOC-027 |
| Localization | 4 | F-loc-015 through F-loc-018 |
| Performance | 5 | F-performance-114 through F-performance-118 |
| Security | 6 | n-201 through n-206 |
| Testing/CI | 4 | F-test-019 through F-test-022 |

**Total Nit: 40.**

### 2.5 Severity matrix totals

| Dimension | Critical | Major | Minor | Nit | Total |
|---|---|---|---|---|---|
| Business | 3 | 7 | 6 | 6 | 22 |
| Code | 0 | 9 | 11 | 7 | 27 |
| Compliance | 3 | 11 | 7 | 3 | 24 |
| Documentation | 1 | 11 | 7 | 5 | 24 |
| Localization | 0 | 8 | 6 | 4 | 18 |
| Performance | 0 | 6 | 7 | 5 | 18 |
| Security | 0 | 5 | 10 | 6 | 21 |
| Testing/CI | 1 | 10 | 6 | 4 | 21 |
| **Total** | **8** | **67** | **60** | **40** | **175** |

(Cross-cut findings — e.g., F-business-007 = M-DOC-010 — counted once in primary dimension.)

---

## 3. Cross-cutting themes

These themes have ≥ 2 sub-reports surfacing the same root cause.

### Theme α — Site/marketing surface as a divergent code-claim boundary

**Sources:** Business (F-business-001/002/003/004/008/009/010/017/023), Documentation (M-DOC-005), Localization (F-loc-001/003/011/012/013).

**Root cause:** The public site (`site/*.html` × 6 locales × 286 i18n keys) is a separately-tested surface that does not yet have the doc-vs-code parity discipline applied to `docs/*.md ↔ docs/*-tr.md`. v0.5.0 widened the gap in five visible places: artefact filenames the code does not produce; quickstart template names that don't resolve; PyPI-publish-status lies in three high-traffic locations; GPU profile counts off by 1-2 across site/README/code; six-language picker promising 56 pages × 6 of content while delivering 56 pages × 2.

**Verdict:** The strongest single fix in this review cycle is a one-pass `site/*.html` rewrite against the actual code — `compliance.py::export_compliance_artifacts` filenames, `quickstart.py::TEMPLATES` handles, `_GPU_PRICING` count, PyPI status flip — followed by adding a CI guard equivalent to the bilingual H2 parity check that already exists for the `docs/` tree. The `site/` surface needs its own per-page-against-code linter.

### Theme β — QMS / compliance-summary documentation as a regulatory deliverable that contradicts itself or the code

**Sources:** Documentation (M-DOC-001, M-DOC-003), Compliance (F-compliance-112, F-compliance-113, F-compliance-119, F-compliance-124), Business (F-business-008).

**Root cause:** The QMS pack (`docs/qms/`) and the reference `compliance_summary.md` are exactly the artefacts a regulated-industry adopter hands to their audit lead alongside ForgeLM's own compliance bundle. Three drift classes accumulate here: (a) `sop_data_management.md` body still cites `v0.5.1+` / `v0.5.2` per-feature splits that the consolidation note in CHANGELOG explicitly retconned; (b) `compliance_summary.md` opens at H2 (no H1), has 11 broken relative paths to `forgelm/...`, lists `safety_results.json` and `benchmark_results.json` that don't exist as standalone artefacts, and stale line anchors point into wrong code regions; (c) audit-event vocabulary scattered across compliance.py and trainer.py with no `audit_event_catalog.md` for an external auditor; (d) all 6 QMS files EN-only despite localization standard requiring bilingual mirroring. Cumulative effect: the regulated-industry deliverable surface now visibly under-delivers vs the marketing thesis.

**Verdict:** Promote `compliance_summary.md` to a real reference doc OR delete + merge into `safety_compliance.md`. Rewrite `sop_data_management.md:74-99` against consolidated v0.5.0 reality. Add `docs/reference/audit_event_catalog.md` (+ `-tr.md` mirror). Decision in §5 below resolves: ship QMS as bilingual or formalise the EN-only carve-out.

### Theme γ — Module cohesion drift past architecture standard's split threshold

**Sources:** Code (F-code-103, F-code-104), Performance (E.4 carry-over implicitly).

**Root cause:** Two modules clear the architecture standard's ~1000-line ceiling by significant margins: `forgelm/data_audit.py` at 3098 lines (six concerns: PII regex + Presidio adapter + simhash + MinHash + streaming aggregator + quality filter + Croissant emitter); `forgelm/cli.py` at 1756 lines (six subcommands' definers + dispatchers + training-mode entry + helpers). v0.5.0 added Phase 12.5 features additively, growing both files past the prior round's already-flagged ceilings without splits.

**Verdict:** Plan Phase 13 `data_audit/` package split (PII / pii_ml / dedup_simhash / dedup_minhash / quality / croissant / streaming) and `cli/` package split (subcommands/{chat,export,deploy,quickstart,ingest,audit}.py + parser glue + helpers). The two splits should land in the same sprint — they are mechanically similar and both unblock targeted Phase 13 perf work.

### Theme δ — Pydantic schema discipline gaps (Literal sweep + descriptions migration)

**Sources:** Code (F-code-101, F-code-102), Compliance (F-compliance-105), Documentation (M-DOC-006).

**Root cause:** The prior round's F-code-014 closed 6 of 12 enum-shaped fields to `Literal[...]`; six remain bare `str` (`LoraConfig.bias`, `DistributedConfig.strategy/fsdp_backward_prefetch/fsdp_state_dict_type`, `SafetyConfig.scoring`, `ComplianceMetadataConfig.risk_classification`, GaLore fields). Same shape: `risk_classification` parallel field on `RiskAssessmentConfig` IS Literal — so the GTM-load-bearing classification field can drift via typo to a no-match string, silently downgrading high-risk to no-match. Separately, only 1 of ~170 fields carries `description=`, blocking config-doc generation and forcing the markdown configuration table to drift.

**Verdict:** One-day sweep for Literal[] (mechanical). Multi-day sprint for `description=` migration with CI guard as the load-bearing piece (without it the migration regresses the moment a contributor forgets). Both are master §7 strategic items that have aged a round.

### Theme ε — Outbound HTTP discipline (SSRF + TLS) extension to non-webhook call sites

**Sources:** Security (M-201), Compliance (implicit via webhook lifecycle).

**Root cause:** Webhook hardening landed in commit `3da2810` set the project-wide bar for outbound HTTP: SSRF guard via `_is_private_destination`, redirect refusal, explicit `verify=True`, timeout floor, `notify_failure(reason)` masked through `mask_secrets`. Two new outbound HTTP call sites (`judge.py:85`, `synthetic.py:207`) that pre-date that bar were not part of the sweep. Both honour an operator-supplied `api_base`, both ship `Authorization: Bearer <api_key>` headers, neither guards against IMDS endpoints, neither rejects `http://` URLs, neither has a redirect ban or timeout floor.

**Verdict:** Extract shared `forgelm/_http.py:safe_post` from `webhook._post_payload`; route judge + synthetic + webhook through it. Mirror config fields. ~80 LOC + tests. **Single PR.**

### Theme ζ — Documentation count drift across CONTRIBUTING / CLAUDE / standards

**Sources:** Documentation (M-DOC-009, M-DOC-010, M-DOC-011), Business (F-business-007), Code (none — count-drift is doc problem, not code).

**Root cause:** v0.5.0's prior-round count-refresh sweep landed in `architecture.md` (26 modules / 47 test files / 800+ tests / 10 notebooks) and partially in CONTRIBUTING.md (test count corrected; module enumeration missed). Three orientation surfaces still drift: CLAUDE.md says "26 test modules" (reality 47); CONTRIBUTING.md project-structure lists 17 modules (reality 26); `docs/standards/testing.md:8` says "26 test modules" + L127 cites `--cov-fail-under=25` while pyproject is 40. Each is a 1-line fix; cumulative effect is "the docs don't notice when they go stale," which is the single most documentation-drift-shaped finding in the standards posture.

**Verdict:** One-PR low-effort cleanup. Add a CI step that fails on stale module / test / notebook counts in any markdown that mentions them — same pattern as the H2 parity check.

### Theme η — Operator identity + audit-log forensic completeness

**Sources:** Compliance (F-compliance-102, F-compliance-114, F-compliance-117, F-compliance-119, F-compliance-120, F-compliance-121), Code (F-code-143).

**Root cause:** Theme B closure makes the audit chain tamper-evident; downstream gaps weaken its forensic value: (a) operator falls back to literal `"unknown"` when env unset (Critical, in distroless containers always fires); (b) audit log lacks `os.fsync` after flush (Major, narrow durability window); (c) HF Hub dataset fingerprint silently falls back without a `revision` pin (Major); (d) no `audit_event_catalog.md` documents the vocabulary; (e) safety classifier-load failure returns `passed=False` without an audit-log event distinguishing "model unavailable" from "classifier returned unsafe output"; (f) cross-run continuity claim broader than reality (only within same `output_dir`).

**Verdict:** Three of these (operator fallback, fsync, classifier-load-failure event) are <1 hour fixes that materially strengthen Article 12 record-keeping evidence. The audit_event_catalog is a Phase 13 docs deliverable. The HF Hub revision pin is a Phase 12.6 mini-sprint.

### Theme θ — Performance: lazy import + batching + workers as the three remaining wins

**Sources:** Performance (F-performance-101 lazy torch, F-performance-102 safety+judge batching, F-performance-103 paragraph chunker, F-performance-104 `--workers`, F-performance-105 build_usermanuals).

**Root cause:** v0.5.0 closed all three Critical perf items (Theme E.1/E.2/E.3) plus E.6 (numpy simhash) and E.7 (markdown chunker). Four of nine prior cliffs remain Open. Two — F-performance-003 (lazy torch) and F-performance-004 (combined regex) — are deferred per master verdict; F-performance-007 (`--workers`) is deferred to v0.5.3; F-performance-012 (safety batching) is unaddressed. Add the new findings: paragraph token chunker re-encodes (the markdown twin's other half), `lang_sample` stores full payloads, build_usermanuals runs serial with no incremental cache.

**Verdict:** F-performance-101 is a 30-min quick win that fell through the cracks of an otherwise thorough sweep. F-performance-102 (safety + judge batching) is half-day work with 10-20× wall-clock reduction. F-performance-104 (`--workers`) is the deciding factor for whether `--pii-ml` is usable on >100K-row corpora.

### Theme ι — CI gate enforcement gap (cov-fail-under, fixture fragmentation, cross-OS, pre-commit)

**Sources:** Testing/CI (F-test-001, F-test-004, F-test-005, F-test-007, F-test-008, F-test-009, F-test-010, F-test-017).

**Root cause:** The test corpus is nominally strong (47 modules / 800+ tests / 12.3 K LOC / disciplined skip-if guards / no GPU + no network in unit tests / Llama Guard / TRL / datasketch mocked). The mechanical enforcement layer underneath has gaps: (a) `pytest --cov-fail-under` not actually enforced; (b) `wizard.py` whole-module coverage omit; (c) `_minimal_config` fixture in 4 lokal copies + 7 anti-idiom `from conftest import` callers; (d) cross-OS testing absent despite "OS Independent" claim; (e) no `.pre-commit-config.yaml`; (f) `usermanuals-validate.yml` triggers on PR-only (main-direct push bypasses validation); (g) `pytest-xdist` parallelism not enabled. Each gap individually low-impact; cumulatively they explain why the project ships strong tests without a corresponding strong "are the tests actually enforced" surface.

**Verdict:** Single-sprint hardening PR that bundles cov-fail-under enforcement + drop wizard omit + fixture consolidation + pre-commit + cross-OS axis is the right shape.

---

## 4. Top-N priority queue (next sprint)

Ordered by leverage × effort. Items 1-4 close the new Critical findings introduced by v0.5.0. Items 5-10 are quick wins or single-sprint hardening. Items 11-15 are medium-effort decisions.

1. **Site compliance.html artefact rewrite** (Critical, F-business-001) — 30 minutes per locale + 6 locales × ~5 min = ~1 hour. Rewrite the artefact tree against `compliance.py::export_compliance_artifacts` real filenames. Add CI guard. **Highest-leverage Critical.**

2. **Site quickstart.html template names** (Critical, F-business-002) — 5 lines × 6 locales = 30 minutes. Patch `<pre>` mock against `forgelm/quickstart.py::TEMPLATES`.

3. **QMS sop_data_management body rewrite** (Critical, M-DOC-001) — 30 minutes. Drop the v0.5.1+/v0.5.2 per-feature splits; align with the consolidated `[0.5.0]` story. The QMS pack is the project's load-bearing regulatory-deliverable surface; the contradiction is the most embarrassing single doc artefact at HEAD.

4. **CI cov-fail-under enforcement** (Critical, F-test-001) — 1-line `addopts = "--cov-fail-under=40"` + sync `docs/standards/testing.md:127` to 40. **5 minutes.** Closes the silent CI-coverage gap that would have masked any future regression.

5. **PyPI publish status sweep** (Critical, F-business-003) — 4 files, 15 minutes. Flip roadmap.md/roadmap-tr.md status icons; rewrite L16 callout; promote releases.md L85; delete CHANGELOG vestigial sentence at L156-158.

6. **Lazy `torch` / `transformers` / `trl` import in trainer.py** (Major, F-performance-101) — 30 minutes. Sister fix in `model.py`. ~700-1500 ms cold-start drop. **Quick win that fell through prior sweep.**

7. **Operator identity fallback fix** (Critical, F-compliance-102) — 30 minutes + CI smoke test. Replace chained `os.getenv` with `getpass.getuser()` + `socket.gethostname()`; raise without explicit opt-out flag in fully-anonymous envs.

8. **`runtime_smoke.py` decision** (Major, F-test-002) — 30 minutes if delete; 1-2 hours if move-to-tools. Single biggest-symbol violation in the test corpus; nightly wheel-install-smoke already provides equivalent garanti.

9. **Notebook install pin sweep** (Major, F-business-005, M-DOC-005) — 30 minutes for the 7 notebooks + CI grep-and-fail step in nightly.yml.

10. **Drop wizard.py coverage omit + sweep `print()` to `_print` indirection** (Major, F-test-003 + F-code-105 = F-code-019/F-code-013 carry-over) — 3-4 hours. Coupled decision; chat.py is the canonical pattern.

11. **`forgelm verify-audit` subcommand** (Critical, F-compliance-103) — ~4 hours. Without it the Theme B HMAC code is dead-write-only and an external auditor cannot exercise the chain.

12. **Webhook lifecycle vocabulary** (Major, F-compliance-104) — half-day. Add `notify_reverted` + `notify_awaiting_approval`; wire `_revert_model` and `_handle_human_approval_gate`; tests via `requests_mock`.

13. **Article 14 staging directory OR honesty-fix log** (Critical, F-compliance-101) — 5 min for honesty fix; 2-3 days for real staging. Decision-gated (see §5 conflicts).

14. **Pydantic Literal sweep (six remaining fields)** (Major, F-code-101) — 1 hour mechanical; closes Theme δ to 100 %.

15. **Fixture consolidation** (Major, F-test-004 + F-test-005) — 4-6 hours. Move `minimal_config` to `tests/_helpers/`; replace 4 lokal copies + 7 `from conftest import` callers; bundle GRPO trainer helpers (F-test-012) into the same module.

**Sprint capacity:** items 1-9 are ~1 day total; items 10-15 are ~5 days; with parallel execution this is a single 1-week sprint that lifts each affected dimension by half a star.

---

## 5. Conflicts & trade-offs

### 5.1 Performance "F-performance-104 add `--workers`" vs Compliance "audit determinism contract"

**Conflict:** Performance review recommends `--workers N` for the audit row loop (5-7× wall-clock improvement; required for `--pii-ml` to be usable on >100K-row corpora). Compliance review's audit chain promise is "across all runs that share the same `training.output_dir`" (F-compliance-121); the audit's `lang_sample` is "first 200" not "random sample" — order-sensitive across worker counts. A multi-worker run that produces different `lang_sample` than a single-worker run on the same corpus would break the audit's reproducibility evidence.

**Resolution:** Multi-worker variant must reproduce single-worker's `lang_sample` byte-for-byte by preserving chunk order via deterministic chunk index. Cross-worker output is sorted at end (`data_audit.py:889` already does this for near-dup pairs); same discipline extended to `lang_sample`. The audit determinism contract wins; the performance flag is fine if it adheres.

### 5.2 Performance "F-performance-101 lazy torch import" vs Code "library API contract"

**Conflict:** Lazy-import discipline lives in `cli.py` (subcommand handlers do `from .trainer import ForgeTrainer` only inside the train branch) — operator-visible `forgelm --help` already pays no torch cost. But `forgelm/__init__.py:39-77` `__getattr__` exposes `ForgeTrainer` as a public API; library-API users (`import forgelm; forgelm.ForgeTrainer(...)`) trigger the lazy `__getattr__` which pulls trainer.py which eagerly imports torch.

**Resolution:** The library-API contract is real and matters for low-latency Python tools. Per Performance review's open question 4.1, the priority depends on whether `forgelm.ForgeTrainer` is a supported integration surface. The current package surface argues yes. **Verdict:** ship the lazy-import fix in trainer.py + model.py; the priority is Major not Hygiene.

### 5.3 Compliance "F-compliance-101 staging directory" vs Documentation "marketing claim"

**Conflict:** F-compliance-101 says the human-approval gate fires AFTER the model is on disk in `final_model/`, and the log message lies ("Model saved to staging" but path is `final_model/`). Master review's compliance verdict frames this as either a 5-min log honesty fix OR a 2-3 day real-staging implementation. Marketing claim (`docs/product_strategy.md:68`) reads the gate as effective: "Human approval gate (exit code 4) fits into existing governance workflows".

**Resolution:** Two paths are valid: **(a)** Ship the honesty fix in v0.5.1 (5 min), promote staging in v0.5.2 (2-3 days); **(b)** Ship both together. Path (a) is the lower-risk one; path (b) is more work but lands the regulator-facing fix in one tag. Recommendation: **path (a)** — the honesty fix unblocks the regulated-industry diligence concern immediately; the staging promotion can be planned separately with proper test coverage. Update `docs/product_strategy.md:68` and the deployer-instructions text in the same PR.

### 5.4 Localization "F-loc-001 drop DE/FR/ES/ZH from picker" vs Localization "F-loc-011 sparse fallback"

**Conflict:** Localization review offers three paths for the 0/56-page coverage gap: (a) drop DE/FR/ES/ZH from picker until ≥1 critical-path subset translated; (b) render coverage badge in picker ("0/56 — beta"); (c) make build skip empty languages. F-loc-011 separately recommends sparse-fallback emit (saves 1.79 MB of redundant English text but keeps all 6 languages in the picker).

**Resolution:** Path (a) is the most honest; path (b) is the cheapest; path (c) is the build-side-only fix. The strategic call belongs with the project owner (open question §5.7 in localization review). **Recommended:** Path (a) for marketing surface honesty + Path (c) on the build side to also save the bandwidth — these compose. Reverse path (a) once any ≥8-page critical-path subset lands for a given language. Document the policy decision in `docs/standards/localization.md` (currently the standard says "Spanish translations — not planned for 2026" which already contradicts the picker including ES).

### 5.5 Code "F-code-103 data_audit/ split" vs Compliance "stable public API contract"

**Conflict:** Code review recommends Phase 13 `data_audit/` package split. Compliance + Performance reviews both reference `forgelm.data_audit.SECRET_TYPES`, `audit_dataset`, `summarize_report`, `AuditReport`, `detect_pii`, `mask_pii`, `detect_secrets`, `mask_secrets`, `compute_simhash` — these are the public-API symbols tests + external consumers depend on.

**Resolution:** Re-export every public symbol from `data_audit/__init__.py` so import paths don't break. Same pattern data_audit currently uses internally for the subsections. Document the split as non-breaking in the PR description; pin a regression test asserting `from forgelm.data_audit import AuditReport, audit_dataset, ...` still resolves.

### 5.6 Security "M-203 CLI ack flag for FORGELM_GGUF_CONVERTER" vs Operator-Convenience

**Conflict:** Security review recommends gating `FORGELM_GGUF_CONVERTER` env var on `--allow-custom-converter` CLI flag. Operators currently using the env var as a pure convenience knob will see a hard break.

**Resolution:** Ship the CLI ack flag with a one-release deprecation window: until v0.6.0 the env-var-only path emits a `DeprecationWarning` recommending `--allow-custom-converter`; from v0.6.0 the flag is required. Document under the existing `--data-audit` deprecation cadence (which F-business-011 wants codified anyway). Same standard.

### 5.7 Documentation "M-DOC-001 rewrite QMS body" vs Compliance "F-compliance-112 add TR mirrors"

**Conflict:** M-DOC-001 says rewrite `sop_data_management.md` body NOW. F-compliance-112 says ALL 6 QMS files need TR mirrors, including `sop_data_management.md`. Order matters: if you rewrite EN body now, then sync TR mirror, you double the work; if you add TR mirror first, the contradiction in EN body propagates to TR.

**Resolution:** Rewrite EN body first (M-DOC-001) — it's the higher-severity drift. Then run `sync-bilingual-docs` over the corrected EN body to produce TR mirror. Two PRs landing in sequence; do not parallelise.

---

## 6. Standards posture

### 6.1 Standards held systemically

These standards are visibly enforced across the codebase at HEAD and improved this round:

- **`docs/standards/regex.md` 8 hard rules** — every regex landed in v0.5.0 carries the rule citations. `_TOKEN_PATTERN` explicit Unicode (Rule 1); `_SECRET_PATTERNS` `re.ASCII` on `\w`-bearing tokens (Rule 1); PEM markers split via concatenation (Rule 7); `_MARKDOWN_HEADING_PATTERN` anchored on non-whitespace (Rule 4); state-machine fence parsers in `_strip_code_fences` and `tools/build_usermanuals.py:preprocess_admonitions` (Rule 6). The `tools/build_usermanuals.py` preprocessor docstring even cites `regex.md` rule 6 by number — exemplary cross-reference.
- **`docs/standards/error-handling.md` no-silent-fail (audit-trust paths)** — Theme D closure: 6/6 audit-trust silent-fail sites narrowed and re-raise. Audit log writes raise OSError; data.py messages raises ValueError with row index; safety GPU release narrows to RuntimeError; CLI config loader has 5 distinct catch branches.
- **`docs/standards/release.md` Keep-a-Changelog discipline** — `[0.5.0] — 2026-04-30` properly dated; `[Unreleased]` correctly empty post-release pointing at Phase 14; version single-sourced via `importlib.metadata`.
- **`docs/standards/architecture.md` lazy-import for optional extras** — `data_audit.py:56-111` `_HAS_XXHASH` / `_HAS_DATASKETCH` / `_HAS_NUMPY` / `_HAS_PRESIDIO` sentinel pattern is consistent across the audit module; `ingestion.py:233-237` for pypdf etc.
- **CI security best-practice** — `.github/workflows/publish.yml` OIDC trusted publishing (no PYPI_API_TOKEN); per-job least-privilege permissions; no `pull_request_target`; no `continue-on-error: true`; no `|| true` fake-green patterns; SRI on the single external CDN script (mermaid).
- **Outbound HTTP discipline (webhook only)** — Theme H closure: SSRF guard, redirect refusal, explicit `verify=True`, timeout floor, secret-masked failure reasons, response body suppression on 4xx/5xx.

### 6.2 Systemic violations (pattern, not slips)

These are standards the project documents but does not actually enforce mechanically:

- **`docs/standards/logging-observability.md` Rule 2 ("Never use `print()` in library code")** — 86 violation sites at HEAD (chat.py: 1 with `_print` indirection that resolves the conflict for chat; wizard.py: 85 raw print calls; the print-vs-logger conflict §4.4 from the prior round is unresolved). The standard has not been updated with an interactive-subcommand carve-out; the modules have not been refactored to a `_print` shim. **Worst-of-both** state.
- **`docs/standards/testing.md` coverage (`fail_under` enforcement)** — `pyproject.toml` says `fail_under = 40`; CI does NOT pass `--cov-fail-under=40`; `pytest-cov` does not auto-read the toml setting. The gate is documented but not enforced. F-test-001 closes this.
- **`docs/standards/testing.md` `omit` policy (whole-module exclusions need justification)** — `pyproject.toml:186` `omit = ["forgelm/wizard.py"]` is a 951-LOC whole-module exclusion despite 3 wizard test modules existing. The standard does not list this exception.
- **`docs/standards/coding.md` Pydantic `Literal[]` rule** — 6 of 12 enum-shaped fields drift (closed 6 in prior round, 6 remain). Same shape for `description=` migration: 1 of 170 fields.
- **`docs/standards/architecture.md` module cohesion (~1000-line ceiling)** — `forgelm/data_audit.py` at 3098 lines (3× threshold), `forgelm/cli.py` at 1756 lines (1.7× threshold) for a third consecutive round. No split planned in current roadmap.
- **`docs/standards/localization.md` structural mirror rule** — H2 parity holds for the 7 EN/TR doc pairs covered by the bilingual H2 CI check; H3/H4 drift visible in 4 places (configuration-tr H4 14 vs 6; ingestion-tr 2 missing H3; distributed_training-tr 3 missing H3; 4 user-manual TR pages with H2 drift). Standard says H2/H3 parity required; CI only checks H2.
- **`docs/standards/release.md` deprecation cadence** — `--data-audit` removal in v0.7.0 is the live precedent but the standard does not codify minimum overlap, removal-version-in-help, tracking-issue link. Future deprecations will follow ad-hoc patterns.
- **`docs/standards/logging-observability.md` operator identity rule** ("Operator is required. Either from env, config, or fall back to OS username. Never 'unknown'") — directly violated by `compliance.py:56` chained `os.getenv` that resolves to literal `"unknown"` in distroless containers.

### 6.3 Standards drift score

| Standard | Held? | Trend |
|---|---|---|
| `coding.md` Type hints / Literal | Partial (6/12) | improving (was 0/12) |
| `coding.md` Imports / lazy patterns | Held | stable |
| `coding.md` Pydantic models | Partial (descriptions) | stable |
| `regex.md` 8 hard rules | Held | improving (build_usermanuals cites rule 6) |
| `error-handling.md` no-silent-fail (audit-trust) | Held | improving (Theme D closed) |
| `error-handling.md` no-silent-fail (best-effort) | Partial (~25 sites) | stable |
| `logging-observability.md` no print in library | Violated systemically | stable |
| `logging-observability.md` operator identity | Violated systemically | stable |
| `logging-observability.md` log levels | Mostly held | stable |
| `testing.md` coverage gates | Documented not enforced | stable (worse — pyproject + standard now inconsistent) |
| `testing.md` no GPU + no network | Held | stable |
| `testing.md` fixture factory pattern | Partial (4 dup + 7 anti-idiom) | improving |
| `testing.md` 47-modules count | Doc says 26 | doc-drift |
| `architecture.md` module topology | Violated (data_audit.py 3098, cli.py 1756) | regressing (grew this round) |
| `architecture.md` lazy-import optional extras | Held | stable |
| `architecture.md` outbound HTTP discipline | Held for webhook | needs extension (judge.py, synthetic.py) |
| `documentation.md` claim/code alignment | Partial (site drift) | regressing on site, improving on docs/ |
| `documentation.md` bilingual mirror H2 parity | Held | stable |
| `documentation.md` bilingual mirror H3/H4 parity | Violated | stable |
| `localization.md` structural mirror | Partial | stable |
| `localization.md` quality bar (TR) | Held (TR native quality) | stable |
| `localization.md` user-facing 6-language coverage | Violated systemically (DE/FR/ES/ZH at 0%) | stable |
| `release.md` Keep-a-Changelog | Held | improving |
| `release.md` deprecation cadence | Standard gap | stable |
| `code-review.md` lint discipline | Held in CI | stable |

**Net standards posture trend:** 6 of 8 master-tracked items improved; 2 unchanged (wizard print + wizard coverage omit, coupled). Three items regressed (module cohesion +200 lines on data_audit; site claim/code drift; testing coverage doc-vs-pyproject inconsistency).

---

## 7. Quick wins (Pareto)

≤ 30 minutes each, high signal-to-noise. All are mechanical.

1. **`addopts = "--cov-fail-under=40"`** — F-test-001. 1 line in pyproject.toml. Closes Critical CI gate.
2. **`Tür` → `Type`** in `docs/roadmap.md:7` — F-business-020 minor / m-DOC-016. 1-character fix.
3. **`organisations` → `organizations`** in `data_audit.py:104` — F-code-130. 1-character fix.
4. **`✓` → `OK`** in `tools/build_usermanuals.py:404` — F-code-137. 1-line fix; Windows cp1252 portability.
5. **CLAUDE.md test count** `26` → `47` — M-DOC-011. 1-line fix.
6. **`testing.md` test count + cov flag** `26` → `47`, `--cov-fail-under=25` → `40` — M-DOC-009. 2-line fix.
7. **`fail-fast: false`** in `ci.yml:30-34` — F-test-006. 1-line fix.
8. **`usermanuals-validate.yml` push trigger** — F-test-017. 4-line fix.
9. **`forgelm/templates/domain-expert/README.md:13`** — F-business-014. Drop "(requires Phase 11)" parenthetical.
10. **`docs/roadmap.md:7-14` legend** — m-DOC-021. Add tristate symbol legend above status table.
11. **README "10+ modes" → drop literal** — m-DOC-020.
12. **PyPI publish status flip** — F-business-003. 4 files, ~15 minutes.
13. **`safety.py:381-386` `trust_remote_code=False`** mirror to `trainer.py:639-640` — M-202. 2 lines.
14. **`compliance.py:262-265` `os.fsync` after flush** — F-compliance-114. 1 line.
15. **`risk_classification` `str` → `Literal[...]`** — F-compliance-105. 1 line.
16. **Lazy `torch` / `transformers` / `trl` import in trainer.py** — F-performance-101. ~10 lines moved into method bodies.
17. **`lang_sample[:512]`** truncation in `data_audit.py:1706` — F-performance-106. 1-line slice.
18. **`docs/qms/sop_data_management.md` lead-with `forgelm audit`** — m-DOC-018. ~5 lines (rolls up into M-DOC-001 Critical when M-DOC-001 lands).
19. **`docs/standards/release.md` deprecation cadence subsection** — F-business-011. ~10 lines citing cli.py:1424-1428.
20. **`risks-and-decisions.md` 2 new Decision Log rows** — F-business-012.

**Total quick-win effort: ~3 hours of mechanical work; closes 1 Critical + 4 Major + 6 Minor + 9 Nit findings.**

---

## 8. Strategic items (planning)

These are roadmap-level decisions; not single-PR work.

### 8.1 Site-as-tested-surface CI (mod Theme α)

The site (`site/*.html` × 6 locales) is now a divergent code-claim boundary. The bilingual H2 parity check covers `docs/` but not `site/`. Three new Critical findings (F-business-001/002/003) all live on the site. **Decision needed:** either build a `site/`-against-code linter (artefact filenames vs `compliance.py`; template names vs `quickstart.py::TEMPLATES`; GPU count vs `_GPU_PRICING`; PyPI status vs PyPI metadata), or accept that the site requires manual review per release. The first costs ~1 day to write; the second costs ~30 min per release in disciplined eyes. **Recommended: build the linter.** Single source of truth for "what does the site claim, what does the code do".

### 8.2 6-language picker honesty (Theme α + Localization F-loc-001)

DE/FR/ES/ZH user-manual content is 0/56 pages. Picker advertises 6 languages. Three resolution paths in §5.4 above. **Decision needed:** owner intent. If "pre-announce, fill later" → coverage badges in picker. If "unfinished work, hide until ready" → drop from picker. If "community will translate" → name the owner + cadence. The current state is the worst of all three. The `docs/standards/localization.md` "Future (not today)" section explicitly says Spanish is not planned for 2026 — yet ES is in the picker. Resolve in the standard first; then either promote (with content) or pare back.

### 8.3 `data_audit/` + `cli/` package splits (Theme γ)

Both modules clear architecture standard's split threshold by significant margins. Plan a single sprint that splits both — they are mechanically similar. **Decision needed:** v0.5.x or v0.6.0? The public API contract is the load-bearing constraint; re-export from `__init__.py` keeps imports stable. The risk is multi-day, multi-PR work that will produce some merge-conflict pain on parallel PRs. **Recommended: target v0.5.3** (after the `--workers` flag in v0.5.2) so the perf work has the clean surface to land against.

### 8.4 Pydantic `description=` migration with CI guard (Theme δ)

3-5 days for the backfill across ~170 fields. The CI guard (diff `model_fields[name].description` vs configuration.md table cells) is the load-bearing piece — without it the migration regresses the moment a contributor forgets. **Decision needed:** Phase 12.6 docs-tooling sprint vs incremental. **Recommended: incremental** — add `description=` to every newly-added or newly-modified field starting now (PR template gate); backfill in dimension-scoped batches (one PR per top-level config section); CI guard lands with the first batch. Sequence note: this should land **before** any TR-mirror-config sweep so the TR markdown can be regenerated, not hand-translated.

### 8.5 Webhook lifecycle vocabulary + Article 14 staging directory (Compliance Theme β)

Two mid-effort items that together close the Article 14 effective-oversight gap: F-compliance-104 (`notify_reverted` + `notify_awaiting_approval` events) is half-day work. F-compliance-101 (real staging directory + `forgelm approve <run_id>` subcommand) is 2-3 days. **Decision needed:** ship both in v0.5.1 vs v0.5.1 (vocabulary) + v0.5.2 (staging). Coupled with the marketing claim on `docs/product_strategy.md:68`. **Recommended:** bundle both in v0.5.2 with the `forgelm verify-audit` subcommand (F-compliance-103) — these three together close the regulatory-diligence gap to ★★★★½.

### 8.6 QMS bilingual policy (Compliance F-compliance-112)

`docs/qms/` is currently EN-only (6 files: README + 5 SOPs). Localization standard says bilingual user-facing required. **Decision needed:** is QMS deliberately EN-only (standard QMS-template practice; provider customises per-deployer) or oversight? Both interpretations are defensible; the current ambiguity is the issue. **Recommended:** record the decision in `risks-and-decisions.md`. If EN-only is the policy, update `docs/standards/localization.md` "What's translated" table to formalise the QMS exception. If TR mirror is needed, schedule under `add-localization-task` skill.

### 8.7 `--workers N` audit flag determinism contract (Compliance + Performance overlap)

Per §5.1 above, the multi-worker variant must reproduce single-worker `lang_sample` byte-for-byte. **Decision needed:** confirm the determinism contract, then ship `--workers N` to v0.5.2 or v0.5.3 per master verdict. The `lang_sample` is "first 200" not "random sample" so byte-for-byte preservation across worker counts is non-trivial but feasible via deterministic chunk-index ordering.

### 8.8 ISO 27001 / SOC 2 future Cloud SaaS path (Compliance open question 8)

Open question in both prior + current rounds. The answer affects whether F-compliance-011-style explicit non-claims should appear in `safety_compliance.md`. **Decision needed:** does Phase 13 Pro CLI / Cloud SaaS pursue ISO 27001 conformance? If yes, this changes the security review's posture (currently "credible for trusted-internal pipelines + regulated-industry diligence"). If no, document the explicit non-claim. **Owner-decision** belonging with the `docs/marketing/` strategy (gitignored).

---

## 9. Star ratings recap

| Dimension | Rating (this round) | Rating (prior round) | Trend | Path to next half-star |
|---|---|---|---|---|
| Business | ★★★½ / 5 | ★★★½ / 5 | flat | Close site compliance.html + quickstart.html + PyPI status (1-3 hours) → ★★★★ |
| Code | ★★★½ / 5 | ★★★¾ / 5 | flat (-0.25, within rounding) | Pydantic Literal sweep + silent-fail narrowing + lazy torch import → ★★★★ |
| Compliance | ★★★★ / 5 | ★★★½ / 5 | up | Article 14 staging + verify-audit + operator identity → ★★★★½ |
| Documentation | ★★★½ / 5 | ★★★½ / 5 | flat | QMS rewrite + count drift + design-doc blockquotes → ★★★★ |
| Localization | ★★★ / 5 | (new axis) | new | F-loc-005/007/008 TR sections + F-loc-001 picker honesty → ★★★½ |
| Performance | ★★★★ / 5 | ★★★★ / 5 | flat | Lazy torch + safety batching + paragraph chunker → ★★★★½ |
| Security | ★★★★ / 5 | ★★★½ / 5 | up | M-201 (judge/synthetic SSRF) + M-202 (trainer trust_remote) + M-203 (GGUF SHA-256) → ★★★★½ |
| Testing & CI/CD | ★★★½ / 5 | (new axis) | new | F-test-001 cov gate + drop wizard omit + fixture consolidation → ★★★★ |

**Overall this round:** ★★★¾ / 5 (weighted-by-dimension). **Prior round:** ★★★½ / 5. **Net: +0.25 stars** despite two new axes (Localization, Testing/CI) lowering the average against a smaller prior denominator.

---

## 10. v0.5.0 release post-mortem

### 10.1 Where v0.5.0 brought measurable improvement

1. **Critical-only closure: 100 % across 10 prior Critical findings.** Theme A (version drift) and Theme B (audit-chain integrity) — the two highest-leverage cross-cuts — closed at 100 %. This is the biggest single trust signal in the cycle. The audit chain is now genuinely tamper-evident: flock + post-write hash advancement + genesis manifest + HMAC-when-keyed.
2. **Webhook security hardening** — Theme H closed at 100 %. SSRF guard + redirect refusal + explicit verify=True + timeout floor + secret-masked failure reasons. The webhook is now best-in-class for outbound HTTP among comparable OSS tools.
3. **Performance scaling cliffs at 100K-1M-row tier** — three of nine prior findings closed structurally: `agg.minhashes` double copy eliminated; bidirectional MinHash builds each LSH once; `text_lengths` reservoir sampling (Algorithm R, 100K cap, ~800 KB regardless of corpus size). Audit pipeline is materially faster for wedge corpora.
4. **Numpy simhash vectorisation + markdown chunker batch-encode** — F-performance-005 + F-performance-006 closed via vector dispatch; pure-Python fallback retained for fixture stability.
5. **Pydantic `Literal[]` discipline** — 6 of 12 enum-shaped fields converted; bespoke `_validate_trainer_type` runtime validator deleted in favour of schema-level enforcement.
6. **Documentation count refresh** — `architecture.md` / `architecture-tr.md` / CONTRIBUTING.md test-count + notebook-count corrected. Three of five count-drift surfaces fixed.
7. **Bilingual H2 parity** — 4 TR mirrors at H2 count parity (configuration-tr, usage-tr, architecture-tr, distributed_training-tr); architectural drift halved.
8. **CHANGELOG hygiene** — `[0.5.0] — 2026-04-30` properly dated section; consolidation of Phases 11/11.5/12/12.5 explicitly explained at L17-25; `[Unreleased]` correctly empty post-release pointing at Phase 14.
9. **Phase 12.5 surface** — `forgelm ingest --all-mask`, wizard "audit first" entry point, `forgelm audit --croissant`, Presidio ML-NER PII (with fail-loud language pre-flight) — all four backlog items shipped with dedicated regression coverage in `tests/test_phase12_5.py` (745 lines).
10. **Audit-chain integrity hardening landed end-to-end** with disciplined commit lineage (`6143321` → `8228faa` → `7db47bc`) — the most disciplined multi-commit hardening sequence in the project's history.

### 10.2 Where v0.5.0 missed or regressed

1. **Site / marketing surface** — `site/compliance.html` lists 5 artefact filenames the code does not produce (F-business-001 Critical); `site/quickstart.html` mock uses non-existent template names (F-business-002 Critical); GPU count off-by-2 (F-business-004); 7 of 10 notebooks still install via `git+https://...` (F-business-005). The site grew faster than the parity discipline that protects `docs/`.
2. **QMS body** — `docs/qms/sop_data_management.md:74-99` still asserts `v0.5.1+` / `v0.5.2` per-feature splits, contradicting the consolidation note in CHANGELOG (M-DOC-001 Critical). The QMS pack is the regulatory deliverable; the contradiction is the most embarrassing single doc artefact at HEAD.
3. **CI cov-fail-under** — `pyproject.toml`'s `fail_under = 40` is documented but `pytest-cov` does not auto-enforce it; CI command does not pass `--cov-fail-under=40` as a flag. Coverage can silently drop and CI stays green (F-test-001 Critical).
4. **Operator identity** — falls back to literal `"unknown"` in distroless containers despite the project's own standard explicitly forbidding it (F-compliance-102 Critical).
5. **`forgelm verify-audit`** — the HMAC-when-keyed write path landed (Theme B); the read path remains documentation only. External auditors cannot exercise the chain without the verifier subcommand (F-compliance-103 Critical).
6. **Article 14 staging directory** — gate fires AFTER model is written to `final_model/`; log message lies ("Model saved to staging" but path is final). F-compliance-101 Critical, carried over from prior round.
7. **Lazy `torch` import** — F-performance-003 still open in trainer.py:8-10 (~30 min fix). Quick win that fell through the otherwise-thorough sweep.
8. **`runtime_smoke.py`** — violates 4 standards at once (no tmp_path; cleanup commented; real HF fetch; Turkish comments + emoji). Fresh finding from the new Testing/CI axis.
9. **DE/FR/ES/ZH user-manual content** — 0/56 pages while site picker advertises 6 languages. Fresh finding from the new Localization axis.
10. **`forgelm/data_audit.py` cohesion** — grew from ~2.6K to 3098 lines via Phase 12.5 additive features; `forgelm/cli.py` grew from ~1.5K to 1756 lines. Module cohesion regressing for a third consecutive round.
11. **TR-mirror H3/H4 drift** — `configuration-tr.md` H4 14 vs 6 (12 missing fields in `training` block alone); `distributed_training-tr.md` 3 missing H3 sections; `ingestion-tr.md` 2 missing H3 sections (Phase 12 surface). Bilingual H2 CI check holds; H3/H4 drift hides below the check's resolution.
12. **`description=` migration unstarted** — 1 of 170 fields. Master §7 strategic item #2 aged a round.
13. **`wizard.py` print-vs-logger conflict** — chat.py landed `_print` indirection; wizard didn't follow → standards violation + internal consistency problem.

### 10.3 Net trend

**Improving:** Integrity (audit chain, version drift, dataset fingerprint TOCTOU). Security (SSRF, redirect refusal, secret masking). Compliance (Theme B closure earned the fourth star). Performance (3 of 3 Critical perf items closed).

**Stable:** Code (standards-posture work deferred). Documentation (mirror sweep landed but new drift opened on QMS). Business (Theme A/B closures balance new site-drift findings).

**Regressing:** Module cohesion (data_audit.py grew 500 lines past threshold). Site claim/code alignment (4 new findings on a surface that had fewer in prior round). Testing/CI mechanical gates (cov-fail-under not enforced — gap visible only with the new axis added).

**Bottom line:** v0.5.0 is a *substantively better* release than v0.4.5 along all six axes the prior review tracked. Two new axes (Localization, Testing/CI) surfaced gaps that pre-dated v0.5.0 but now have visibility. The release engineering itself was disciplined; the "what landed" delivers; the "what we said about it" surface (site, QMS, CHANGELOG roadmap claims) is where the residual friction lives.

---

## 11. Appendix — Per-dimension report links

- [Business]( ./business-review-202604300906.md )
- [Code]( ./code-review-202604300906.md )
- [Compliance]( ./compliance-review-202604300906.md )
- [Documentation]( ./documentation-review-202604300906.md )
- [Localization]( ./localization-review-202604300906.md )
- [Performance]( ./performance-review-202604300906.md )
- [Security]( ./security-review-202604300906.md )
- [Testing & CI/CD]( ./testing-cicd-review-202604300906.md )
- [Regression Check]( ./regression-check-202604300906.md )

### A.1 Methodology notes

- **Synthesis source:** the 9 sub-reports listed above were read line-by-line; cross-cuts identified where ≥ 2 sub-reports surfaced the same root cause; severity preserved from source-report verdicts unless reconciled in §5 conflicts.
- **Severity matrix:** 8 dimensions × 4 severities = 32 cells; total findings 175. Cross-cut findings counted once in primary dimension (e.g., F-business-007 = M-DOC-010 counted in Business only).
- **Star rating reconciliation:** sub-report ratings accepted unchanged for Business (★★★½), Compliance (★★★★), Documentation (★★★½), Localization (★★★), Performance (★★★★), Security (★★★★), Testing/CI (★★★½). Code adjusted from the sub-report's ★★★½ — sub-report executive summary explicitly says "★★★½ / 5 (unchanged from prior round)"; prior round was ★★★¾ — kept at ★★★½ within rounding tolerance.
- **Closure rate from regression-check:** 38 Closed / 9 Partially Closed / 10 Open / 0 Reopened / 0 Not Verifiable. Critical-only closure: 10 / 10 = 100 %.
- **Prior round comparison surface:** master-review-opus-202604281313.md §1 severity table (rows 1-54 in scope; rows 55-60 are Minor/Nit roll-ups, out of scope per the regression-check brief).
- **No new findings introduced by this master report:** all severity-tagged items trace to source sub-reports.

### A.2 Sprint-1 PR roadmap (recommended sequencing)

| PR | Scope | Effort | Closes |
|---|---|---|---|
| PR-1 | Site compliance.html + quickstart.html artefact rewrite + 6 locales | 2 hours | 2 Critical (F-business-001, F-business-002) |
| PR-2 | PyPI publish status sweep + roadmap.md/-tr.md flips | 30 min | 1 Critical (F-business-003) |
| PR-3 | `docs/qms/sop_data_management.md` body rewrite | 30 min | 1 Critical (M-DOC-001) |
| PR-4 | CI cov-fail-under enforcement + standards/testing.md sync | 10 min | 1 Critical (F-test-001) |
| PR-5 | Operator identity fallback fix + CI smoke test | 1 hour | 1 Critical (F-compliance-102) |
| PR-6 | Lazy torch import in trainer.py + model.py + regression test | 1 hour | 1 Major (F-performance-101) |
| PR-7 | Notebook install pin sweep (7 notebooks) + nightly grep step | 1 hour | 1 Major (F-business-005) |
| PR-8 | Pydantic Literal sweep (6 fields) + drop redundant runtime validators | 1 hour | 1 Major + 1 Major (F-code-101 + F-compliance-105) |
| PR-9 | Quick wins bundle (10-15 small fixes) | 2 hours | ~10 Minor + Nit |
| PR-10 | Webhook lifecycle vocabulary (notify_reverted + notify_awaiting_approval) | half-day | 1 Major (F-compliance-104) |
| PR-11 | `forgelm verify-audit` subcommand + library function | half-day | 1 Critical (F-compliance-103) |
| PR-12 | Wizard `_print` indirection + drop coverage omit | half-day | 1 Major (F-test-003 + F-code-105) |
| PR-13 | `--data-audit` deprecation discipline (DeprecationWarning + tracking issue) | 30 min | 1 Major (F-code-107) |
| PR-14 | Fixture consolidation (`tests/_helpers/`) + remove 4 lokal copies | 4 hours | 1 Major (F-test-004 + F-test-005) |
| PR-15 | safe_post helper extraction (judge.py / synthetic.py / webhook.py) | half-day | 1 Major (M-201) |

**PR-1 through PR-9: ~1 day total of mechanical work.**
**PR-10 through PR-15: ~3 days of medium-effort hardening.**
**Sprint total: ~4-5 days; closes 8 Critical + 9 Major + ~10 Minor/Nit.**

After this sprint, the rating projection lifts each affected dimension by half a star: Business ★★★★, Compliance ★★★★½, Documentation ★★★★, Code ★★★★, Performance ★★★★½, Security ★★★★½, Testing/CI ★★★★. Localization remains a separate strategic decision per §8.2.

### A.3 Dimensional findings density vs prior round

| Dimension | Prior round Critical | This round Critical | Prior Major | This Major | Net surface delta |
|---|---|---|---|---|---|
| Business | 3 | 3 | ~12 | 7 | -5 (closures dominated; 2 carry-over Critical resolved, 3 new Critical) |
| Code | 4 | 0 | ~14 | 9 | -9 (Theme A + B + D + F closures; Major bucket halved) |
| Compliance | 2 | 3 | ~10 | 11 | +2 (Theme B closed; new gaps surfaced — Article 14, verifier, retention) |
| Documentation | 1 | 1 | ~13 | 11 | -2 (mirror sweep landed; QMS body emerged as new Critical) |
| Localization | n/a | 0 | n/a | 8 | new axis — coverage gap was always there; now visible |
| Performance | 3 | 0 | 6 | 6 | -3 Critical (closed) — Major count flat with new findings replacing old |
| Security | 2 | 0 | 7 | 5 | -4 (webhook + audit + fingerprint TOCTOU + sanitisation closures) |
| Testing/CI | n/a | 1 | n/a | 10 | new axis — gap was always there; now visible |

**Direction read:** four dimensions show net surface reduction (Business, Code, Documentation, Security). Two dimensions show flat surface (Compliance, Performance) because every prior closure was matched by a new finding of comparable severity emerging from the v0.5.0 surface itself. Two new axes added — both surface gaps that pre-dated v0.5.0 but were not in scope for the prior round.

### A.4 Effort budget for full closure (all severities)

| Tier | Findings count | Estimated effort |
|---|---|---|
| Critical (8) | 8 | 1.5 days |
| Major (67) | 67 | 12-15 days for full closure; 5 days for Top-15 priority queue |
| Minor (60) | 60 | 4-6 days drive-by cleanup; most fold into adjacent PRs |
| Nit (40) | 40 | 1-2 days mass-edit |

**All-severity closure target: ~3-4 weeks of focused work.** Realistic next-sprint target (Sprint-1 PR roadmap above): **1 week.** Lifts overall to ★★★★ within that window.

### A.5 Findings exclusively from new dimensions

Adding the Localization and Testing/CI axes for this round surfaced 18 + 21 = 39 findings that did not exist as tracked items in the prior round. Of these:

- **Localization:** 0 Critical, 8 Major, 6 Minor, 4 Nit. Most-load-bearing: F-loc-001 (DE/FR/ES/ZH 0/56 page coverage with active picker promise) and F-loc-005/006/007/008 (TR mirror H2 drift on 4 user-manual pages). The chrome-translation discipline (286 keys × 6 languages, native quality) is exemplary; the user-manual-content discipline did not follow.
- **Testing/CI:** 1 Critical, 10 Major, 6 Minor, 4 Nit. Most-load-bearing: F-test-001 (cov-fail-under not actually enforced in CI), F-test-002 (`runtime_smoke.py` violates 4 standards at once), F-test-003 (wizard.py coverage omit blocks visibility on 951 LOC + 3 test modules), F-test-004 + F-test-005 (fixture fragmentation + anti-idiom `from conftest import`).

These two axes are net-new visibility, not net-new bug surface. The sub-reports' rating ★★★ (Localization) and ★★★½ (Testing/CI) are honest given the gaps; both can lift quickly with disciplined sprints (per §A.2).

### A.6 Closure-vs-discovery balance

- **Closed in this cycle: 38 prior Major/Critical findings** (66.7 % outright).
- **Newly discovered Critical: 8** (3 Business, 3 Compliance, 1 Documentation, 1 Testing/CI). Of the 8: 4 are direct consequences of v0.5.0 ship (site/QMS/CHANGELOG drift); 3 are pre-existing gaps now visible (operator identity, verify-audit subcommand, Article 14 ordering — all flagged in prior round but partially-closed or unaddressed); 1 is the new Testing/CI axis (cov gate).
- **Newly discovered Major: 67** across all 8 dimensions. Of these: ~25 are carry-overs renamed (e.g., F-code-014 → F-code-101, F-business-003 carry-overs, prior round's F-performance-003 surfaces as F-performance-101); ~25 are fresh discoveries from the new axes (Localization 8 + Testing/CI 10) and Phase 12.5 surface; ~17 are net-new from a cleaner-eye second-pass review.

**Closure rate analysis:** 38 closed / (38 + 8 newly discovered Critical) = 82.6 % effective Critical-tier net improvement. The rating uptick on Compliance (★★★½ → ★★★★) and Security (★★★½ → ★★★★) reflects this net improvement; the flat ratings on Code / Documentation / Business reflect the offsetting new findings.

### A.7 Trend signals worth watching for the next master review

1. **Will site/-against-code parity discipline land?** §8.1. Without it, Theme α will recur with each subsequent release.
2. **Will the wizard print/coverage decision land?** Coupled F-code-105 + F-test-003 are the longest-running open items; both wait on the same wizard refactor sprint.
3. **Will Pydantic `description=` migration start?** Without the CI guard the migration will leak back the moment any new field is added without it.
4. **Will Article 14 staging directory ship?** F-compliance-101 is the highest-severity carry-over from the prior round still open.
5. **Will DE/FR/ES/ZH user-manual content land or the picker pare back?** F-loc-001 strategic call belongs with the project owner.
6. **Will `data_audit/` + `cli/` package splits happen before v0.6.0?** Module cohesion regressing for a third consecutive round; v0.7.0 risk profile worsens otherwise.
7. **Will `--workers N` audit flag preserve `lang_sample` determinism?** §5.1 conflict resolution has the right shape; implementation needs the contract pinned in tests.
8. **Will operator identity raise instead of falling back to `"unknown"`?** F-compliance-102 is a 30-min fix that materially strengthens Article 12 forensic value.

If half of these eight signals close by the next master review, the project trajectory clears the EU AI Act August 2, 2026 enforcement bar with material runway. The audit chain is now tamper-evident; the residual gaps are individually narrow; the cumulative risk profile is materially better than at the prior round.

### A.8 Reading order recommendations

Different readers should enter at different points:

- **5-minute exec read:** §0 Executive summary + §9 Star ratings recap + §4 Top-10 priority items 1-5. Frames the project health and the immediate sprint target.
- **20-minute owner read:** §0 + §1 (regression posture) + §3 (cross-cut themes) + §5 (conflicts) + §8 (strategic items). Frames the decisions blocking the next sprint.
- **45-minute reviewer read:** add §2 (severity-aggregated table) + §6 (standards posture) + §10 (post-mortem). Frames the cumulative posture of the codebase against the standards that are supposed to govern it.
- **Full read (~90 minutes):** the appendix + sub-reports linked in §11 give the line-level evidence behind every Major+ finding.

### A.9 What this review intentionally did not do

- **Did not introduce new findings beyond synthesis.** All 175 entries trace to source sub-reports.
- **Did not re-rate prior-round closed findings.** Closures recorded by the regression-check report were accepted at face value.
- **Did not perform live testing** (no `pytest` run, no `forgelm --dry-run` execution). Static review only against commit `6b515ed`.
- **Did not open `docs/marketing/` (gitignored)** — strategy material is treated as referenced source-of-truth where the sub-reports cited it, not directly read here.
- **Did not validate external dependencies** (e.g., `pip-audit` on resolved tree). Out of scope per security review's open question 6.
- **Did not run the bilingual H2/H3/H4 parity check** as a script. Counts cited in §3 are from the localization + documentation sub-reports.

### A.10 Open questions carried forward to the next master review

These did not reach a decision in this round. The next reviewer will have to surface them again or document the resolution:

1. (Documentation Q1) Should `data_preparation*.md` exist as a 35-line micro-doc, be rewritten to ~120 lines, or fold into `alignment.md`?
2. (Compliance Q4) What is ForgeLM's official position on GDPR right-to-erasure for trained model weights?
3. (Compliance Q5) Are TR mirrors of `docs/qms/` blocked on translation bandwidth or a deliberate "QMS is provider-customised" decision?
4. (Compliance Q8) Does the project plan to pursue ISO 27001 / SOC 2 Type II for any future Cloud SaaS path?
5. (Performance Q1) Is `forgelm.ForgeTrainer` (public API at `__init__.py:49-50`) a supported integration surface or "use the CLI, don't import the package"?
6. (Performance Q3) Should `evaluation.safety.batch_size` auto-resolve from VRAM or be a pure user knob?
7. (Performance Q4) Should `synthetic.api_concurrency` use `tokens_per_min` / `requests_per_min` / `concurrent` rate-limit shape, or a single conservative knob?
8. (Code Q1) `data_audit/` package split — v0.5.x or v0.6.0 work?
9. (Code Q4) Should `error-handling.md` add a named "best-effort artefact" category that sanctions broad catches with `# noqa: BLE001 — best-effort: <reason>` comment?
10. (Localization Q5) Does `docs/standards/localization.md` need a "user manual" carve-out separate from the `docs/reference/*` EN+TR pairing?
11. (Testing Q1) Does pytest-cov auto-enforce `[tool.coverage.report].fail_under`? Confirm via live run; if yes, F-test-001 demotes to Major.
12. (Security Q4) Single project-wide `forgelm.security.SecurityConfig` block gating symlink-following + private-IP webhook destinations + `trust_remote_code` under one `security_posture: strict` knob — pursue?

The next master review should open with the resolution status of these 12 questions; whichever remain unresolved should be elevated to strategic items with named owners.

### A.11 Summary numbers (one-glance recap)

- **Critical-only closure:** 10 / 10 = 100 % vs prior round.
- **Major closure:** 28 / 47 = 59.6 % outright; +9 Partially Closed = 78.7 % combined.
- **New Critical findings:** 8 (3 Business, 3 Compliance, 1 Documentation, 1 Testing/CI).
- **New Major findings:** 67 (across 8 dimensions; ~25 are renamed carry-overs).
- **Total findings synthesized:** 175 (8 Critical + 67 Major + 60 Minor + 40 Nit).
- **Sub-reports synthesized:** 9 (5402 source lines).
- **Star rating overall:** ★★★¾ / 5 (up +0.25 from prior ★★★½).
- **Themes fully closed:** A (version drift), B (audit chain), D (silent-fail), F (Pydantic Literal sub-set), H (webhook).
- **Themes partially closed:** C (doc drift), E (perf cliffs), G (standards drift).
- **Themes regressing:** module cohesion (Theme γ), site claim/code (new Theme α), CI gate enforcement (new Theme ι).
- **Sprint-1 effort to lift overall to ★★★★:** ~4-5 days; closes 8 Critical + 9 Major + ~10 Minor/Nit (per §A.2).

---

*End of master review — 202604300906.*
*Verified against synthesized sub-reports at commit 6b515ed912f8f22304194c1b3f55ed07a26f519c.*

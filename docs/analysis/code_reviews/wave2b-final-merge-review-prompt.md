# Wave 2b — Final Pre-Merge Review Prompt (PR #30)

> **Use this prompt verbatim** to launch the multi-agent review on the
> consolidated Wave 2b PR. The prompt is self-contained: each reviewer agent
> can pick it up cold without context from prior conversations.
>
> **This is the last review before merge.** Five absorption rounds (Round-1
> through Round-5 plus Sonar/CodeRabbit follow-ups) have already landed on
> this branch. After this review, surviving findings will be addressed and
> the branch will be merged to `development`. Treat the bar accordingly:
> ship-or-block, no more polish rounds.

---

## Repo & PR under review

- **Repo:** `cemililik/ForgeLM`
- **Branch under review:** `closure/wave2b-integration`
- **PR:** [#30](https://github.com/cemililik/ForgeLM/pull/30) → base `development`
- **HEAD SHA at prompt freeze:** `36afbc0`
- **Diff scope vs main:** 195 files, ~32 300 insertions, ~6 300 deletions.
  Five new CLI subcommands (`_purge.py`, `_cache.py`, `_safety_eval.py`,
  `_verify_annex_iv.py`, `_verify_gguf.py`), one new public-API facade
  rewrite (`forgelm/__init__.py`), one new CI guard (`tools/check_field_descriptions.py`).
- **What it consolidates:** Phases 16, 19, 21, 35, 36 — five
  dependency-free phases unblocked by the Wave 2a merge.

## What ForgeLM is (60 seconds)

A **config-driven, enterprise-grade LLM fine-tuning toolkit** — YAML in,
fine-tuned model + compliance artifacts out. Built for CI/CD pipelines,
not notebooks. Six alignment paradigms (SFT/DPO/SimPO/KTO/ORPO/GRPO),
integrated safety evaluation (Llama Guard), EU AI Act compliance
artefacts (Articles 9–17 + Annex IV), append-only audit log, opt-in
human approval gate, auto-revert on quality regression. Read
[docs/product_strategy.md](../../product_strategy.md) for fuller
background.

Project rulebook lives under [docs/standards/](../../standards/) — read
[coding.md](../../standards/coding.md),
[error-handling.md](../../standards/error-handling.md),
[testing.md](../../standards/testing.md),
[logging-observability.md](../../standards/logging-observability.md),
[regex.md](../../standards/regex.md), and
[code-review.md](../../standards/code-review.md) before commenting.
Project-wide guidance for AI agents is in the root `CLAUDE.md`.

## What this PR ships

| Phase | Type | Headline change |
|---|---|---|
| 16 | Implementation + CI guard | `tools/check_field_descriptions.py` AST-based Pydantic `description=` migration scanner; `--strict` mode wired into the lint job. All 174 fields across 19 Pydantic config classes carry a `description=`. |
| 19 | Implementation | `forgelm/__init__.py` rewritten as a strict PEP-562 lazy-import facade backed by `_LAZY_SYMBOLS`; `__dir__` lists the public surface; `forgelm/_version.py` exposes a separate `__api_version__`; `forgelm/py.typed` shipped via package-data. 25 stable symbols re-exported. |
| 21 | Implementation | `forgelm purge` three-mode dispatcher (`--row-id` / `--run-id` / `--check-policy`), `RetentionConfig` (4 horizons + `enforce` mode), 6 new `data.erasure_*` audit events, persistent per-output-dir salt for hashed `target_id`s, atomic JSONL row erasure with `os.fsync` before `os.replace`. |
| 35 | Implementation | `forgelm cache-models` + `forgelm cache-tasks` — air-gap blocker pair. `cache-models` uses `huggingface_hub.snapshot_download`; `cache-tasks` uses `lm_eval.tasks.get_task_dict` + `dataset.download_and_prepare()`. Hub vs. Datasets cache resolvers split (separate env-var chains). 6 new `cache.populate_*` audit events. |
| 36 | Implementation | `forgelm verify-annex-iv` + `forgelm verify-gguf` + `forgelm safety-eval` — deployment-integrity toolbelt. New bundled probe set `forgelm/safety_prompts/default_probes.jsonl` (50 prompts × 14 harm categories). Public `verify_annex_iv_artifact` / `verify_gguf` library functions; shared `compute_annex_iv_manifest_hash` so writer + verifier canonicalisation cannot drift. |

## What we want from this round

**Goal:** decide whether `closure/wave2b-integration` is mergeable to
`development`. Block on real defects; do not gate on style nits, hypothetical
futures, or anything previously addressed in Rounds 1–5.

Be concrete. Every finding must include:

1. **Severity tag** — `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` / `NIT`
2. **Finding ID** — `F-<phase>-<NN>` (e.g. `F-21-03`, `F-36-04`,
   `F-INFRA-01`); use `F-XPR-NN` for cross-phase observations.
3. **File:line citation** — `forgelm/cli/subcommands/_purge.py:912` or a
   short range `:912-960`. Cite the file even for design-doc findings
   (`docs/analysis/code_reviews/gdpr-erasure-design-202605021414.md:§4.4`).
4. **One-paragraph reasoning** — what is wrong, what is the user-visible
   consequence, and why it qualifies for that severity tier.
5. **Suggested fix** — a code or text snippet, not a vague direction.
6. **Test that would have caught it** — name the test file + a stub of
   the assertion. If the bug is in a design doc, name the doc section
   that should have called it out.

Severity bar:

- `CRITICAL` — would corrupt data, silently lose audit events, leak PII
  / secrets, break the public exit-code contract (`0/1/2/3/4`), break
  the `--offline` / air-gap promise, or invalidate the audit-log hash
  chain. Blocks merge.
- `HIGH` — runtime crash on a documented happy path, missing test for a
  documented contract, schema mismatch with `pyproject.toml` /
  `config.py`, documentation claim with no code backing, or a
  writer/verifier pair whose output cannot round-trip. Blocks merge.
- `MEDIUM` — logic bug in an off-the-happy-path branch, observability
  gap, or design-doc statement that contradicts shipped code. Should be
  fixed before merge but the call is the maintainer's.
- `LOW` — defensive-coding improvement, minor inconsistency, missing
  edge-case test that would not have changed PR direction.
- `NIT` — naming, line wrap, comment phrasing. Note in passing only;
  do not stack these.

## Areas to scrutinise

These are the surfaces most likely to harbour residual issues after five
rounds of absorption. Hit them specifically.

### Phase 21 — `forgelm purge` (largest surface, most absorption)

- **Atomic-rewrite ordering** ([_purge.py:`_atomic_rewrite_dropping_lines`]) —
  the helper now `flush() + os.fsync()` before `os.replace()`. Walk
  through a power-loss scenario: which states leave the audit log
  recoverable, which leave it corrupt? Verify the fsync is on the
  *temp file* descriptor, not the directory.
- **Per-artefact audit-age lookup**
  ([_purge.py:`_build_audit_age_lookup` + `_resolve_artefact_age`]) —
  Round-5 added a per-`run_id` age map; the genesis age is the
  fallback. Trace what happens when:
  - the audit log has no `run_id` field on its first event (older
    workspaces) — does the genesis slot still populate?
  - a staging dir's name `run_id` does not match any audit event
    (orphaned staging) — does it fall back to genesis or mtime?
  - two staging dirs share the same `run_id` (e.g. retried run) —
    which timestamp wins?
- **Compliance-artefact matching for run-id erasure**
  ([_purge.py:`_run_purge_run_id` artefact branch]) — does
  `if run_id in fname` substring-match correctly avoid false hits when
  one run_id is a *prefix* of another (`fg-abc123` vs `fg-abc1234`)?
  Round-1 absorption claimed this was tightened; verify.
- **`--check-policy` strict config-load** ([_purge.py:`_run_purge_check_policy`]) —
  Round-2 absorption added strict loading so an explicit `--config`
  with bad YAML exits `EXIT_CONFIG_ERROR`. Confirm the docs
  ([docs/guides/gdpr_erasure.md:69-71], [-tr.md:71]) match the
  shipped behaviour, and confirm the `--check-policy` happy path
  still returns 0 with no `--config` supplied.
- **`RetentionConfig` reconcile** ([forgelm/config.py:`_reconcile_staging_ttl_days`
  + `_apply_legacy_alias_forward` + `_emit_legacy_match_warning`]) —
  Round-5 added `model_fields_set` symmetry on both legacy and
  canonical sides, and Round-5-followup added `model_copy(update=...)`
  preservation. Walk through:
  - operator sets only `evaluation.staging_ttl_days: 14` →
    alias-forwards, `DeprecationWarning` at operator's call frame.
  - operator sets only `retention: {audit_log_retention_days: 1825}`
    + `evaluation.staging_ttl_days: 30` → alias-forwards, the
    `audit_log_retention_days` value is preserved (not overwritten by
    a fresh `RetentionConfig(staging_ttl_days=30)`).
  - operator sets both with identical values → `DeprecationWarning`,
    canonical wins, no `ConfigError`.
  - operator sets both with different values → `ConfigError`.
  - both legacy and canonical fields elided entirely → no warning,
    `cfg.retention` may be `None` (existing contract).
- **Salt resolution + target_id hashing** ([_purge.py:`_resolve_salt`,
  `_hash_target_id`]) — re-confirm that `FORGELM_AUDIT_SECRET`
  toggles the `salt_source` field and that the persistent salt file
  is mode 0600. What happens on Windows / containers where 0600 is
  not honoured?

### Phase 36 — verification toolbelt (writer/verifier round-trip is load-bearing)

- **Annex IV writer ↔ verifier round-trip**
  ([forgelm/compliance.py:`build_annex_iv_artifact`,
  `compute_annex_iv_manifest_hash`] + [forgelm/cli/subcommands/_verify_annex_iv.py]) —
  Round-4 absorption introduced the `build_annex_iv_artifact` writer
  + shared canonicalisation. Confirm that:
  - a freshly-exported artefact passes the verifier without manual
    edits (regression already in `tests/test_verification_toolbelt.py`;
    re-confirm coverage is real, not vacuous).
  - the verifier's tampering-detection path fires when *any* §1–9
    field is mutated after export — not just one specific field.
  - `metadata.manifest_hash` is stripped before hashing on both writer
    and verifier sides (chicken-and-egg avoidance).
- **`safety-eval` exit codes** ([forgelm/cli/subcommands/_safety_eval.py]) —
  Round-5 absorption switched the non-passing safety branch from
  `EXIT_CONFIG_ERROR` (1) to `EXIT_EVAL_FAILURE` (3). Confirm the
  header docstring lists all four codes (0/1/2/3) and that no other
  branch in the file accidentally still returns 1 when 3 is the
  semantically correct answer.
- **`safety-eval` ImportError message** ([_safety_eval.py:131-145]) —
  Round-5-followup made the `transformers` ImportError actionable.
  Confirm any *other* ImportError sites in the verification toolbelt
  use the same "verify your environment / reinstall" pattern, not
  the misleading "pip install forgelm" hint.
- **`verify-gguf` SHA-256 sidecar policy** ([_verify_gguf.py:108-145]) —
  Round-2 absorption made malformed sidecars (empty / non-hex /
  truncated) fail closed. Confirm a *missing* sidecar still passes
  (operator's explicit choice — no file → no check). Walk the regex
  guard for ReDoS exposure per [docs/standards/regex.md].

### Phase 35 — air-gap cache subcommands

- **Hub vs. Datasets cache resolvers**
  ([_cache.py:`_resolve_env_cache_dir` vs `_resolve_env_datasets_cache_dir`]) —
  Round-5-followup split these because HF treats them as separate
  caches. Verify:
  - `cache-models` uses the Hub chain (`HF_HUB_CACHE > HF_HOME/hub > ...hub`).
  - `cache-tasks` uses the Datasets chain (`HF_DATASETS_CACHE >
    HF_HOME/datasets > ...datasets`).
  - The `os.environ["HF_DATASETS_CACHE"] = cache_dir` stamp inside
    `_run_cache_tasks_cmd` does not leak into other tests via
    process-global state (look for `monkeypatch.setenv` discipline
    in `tests/test_cache_subcommands.py`).
  - The `_warn_on_cache_dir_divergence(..., kind="datasets")`
    warning names `HF_DATASETS_CACHE`, not `HF_HUB_CACHE`.
- **lm-eval optional-extra hint** ([_cache.py:`_run_cache_tasks_cmd`
  ImportError branch]) — `pip install 'forgelm[eval]'` matches the
  actual extra name in [pyproject.toml].

### Phase 19 — library API facade

- **Lazy-import discipline** ([forgelm/__init__.py]) — running
  `python -c "import sys; import forgelm; print(any('torch' in m or
  'huggingface_hub' in m for m in sys.modules))"` should print
  `False`. Confirm by reading the facade — no module-level
  `from .compliance import ...` etc.
- **`__dir__` completeness** — every entry in `__all__` is
  resolvable via `_LAZY_SYMBOLS`, and every key in `_LAZY_SYMBOLS`
  is in `__all__`. Mismatch = silent surface drift.
- **`__api_version__`** ([forgelm/_version.py]) — anchored at
  `1.0.0`; document the bump policy in the relevant standard or
  flag the gap.

### Phase 16 — Pydantic description guard

- **AST scanner correctness** ([tools/check_field_descriptions.py]) —
  recognises `Annotated[T, Field(..., description=...)]` (Pydantic
  v2 alt form), bare type annotations (no default), `Field(...)` on
  RHS, and literal-default RHS. Round-4 added the Annotated branch;
  re-confirm. Run the scanner against `forgelm/config.py` mentally —
  is anything in the file the scanner would false-flag or
  false-clear?
- **CI wiring** — confirm `.github/workflows/ci.yml` actually fails
  the lint job on a missing description (no `|| true` masking).

### Cross-phase (XPR) checks

- **XPR-01** Audit-event vocabulary stability — every event the
  CLI emits is in `docs/reference/audit_event_catalog.md` and its TR
  mirror, and every event in the catalogue is actually emitted by
  some shipped code path.
- **XPR-02** Exit-code contract — every `sys.exit(N)` in the new
  subcommands maps to the public `0/1/2/3/4` set per
  [docs/standards/error-handling.md]. Any other integer is a contract
  violation.
- **XPR-03** JSON envelope schema — every `--output-format json`
  path in `_purge.py`, `_cache.py`, `_safety_eval.py`,
  `_verify_annex_iv.py`, `_verify_gguf.py` uses the same
  `{"success": bool, ...}` shape. Mismatch = CI-pipeline parsing
  surprise.
- **XPR-04** Documentation drift — every CLI flag mentioned in
  EN docs is also in TR docs and vice versa; every flag in docs
  exists in `forgelm/cli/_parser.py`; every flag in `_parser.py`
  is documented somewhere.
- **XPR-05** Test rigor — scan
  `tests/test_purge.py`, `tests/test_cache_subcommands.py`,
  `tests/test_verification_toolbelt.py`,
  `tests/test_gdpr_erasure.py`, `tests/test_library_api.py`
  for vacuous tests (`assert True`, `assert result`, asserting
  only on a fixture's own shape). Round-3 and Round-4 caught a few;
  there may be more.
- **XPR-06** Webhook URL in compliance manifest — Round-5 fix
  redacts the literal `url` from `manifest["webhook_config"]`. Walk
  every `model_dump(...)` call site in `forgelm/compliance.py` to
  confirm no other path serialises a `WebhookConfig.url` to disk.
- **XPR-07** Sonar Quality Gate — the
  [SonarCloud project](https://sonarcloud.io/project/issues?id=cemililik_ForgeLM&pullRequest=30)
  may surface fresh issues against the latest commit. Confirm any
  remaining cognitive-complexity (S3776), null-narrowing (S2259),
  or unused-local (S1481) findings are real and not absorbed by
  Round-5-followup.
- **XPR-08** Backwards compatibility — does anything in this PR
  break a 0.5.x user's workflow? CLI flag rename, default change,
  exit-code shift, audit event-type rename, deprecation
  acceleration?
- **XPR-09** `model_copy` deprecation-forward — Round-5-followup
  changed the alias-forward to use `retention.model_copy(update=...)`.
  Confirm no other call site that *constructs* a `RetentionConfig`
  (test fixtures, doc examples) still discards operator-set fields.

## Ground rules

- **Read the relevant standard before commenting.** The project
  [docs/standards/](../../standards/) directory is the rulebook.
- **Cite line numbers.** If you cannot point at a line, the finding is
  not actionable.
- **Distinguish design docs from shipped code.** A bug in a design doc
  is a wrong roadmap; a bug in shipped code is a defect. Different
  fixes, different urgency.
- **No phantom severity inflation.** A doc typo is `NIT`. A
  user-visible CLI bug on the happy path is `HIGH` minimum.
- **Prior rounds are baseline.** If you find an issue Rounds 1–5
  already addressed, mark it `[Rounds-1-5 verified]` and move on; do
  not double-bill. The CHANGELOG entries under "Wave 2b Round-N"
  carry the absorption history.
- **No re-litigating closed scope.** "Should ForgeLM also do X" is
  not a finding. Stay in the diff.
- **No suggestions to add a Web UI / GUI / inference engine /
  pretraining pipeline.** See
  [docs/marketing/strategy/05-yapmayacaklarimiz.md] — these are out
  of scope by design (read root `CLAUDE.md` "What ForgeLM is not").
- **This is the final round.** Reserve `CRITICAL` / `HIGH` for
  things that genuinely should block merge. `LOW` / `NIT` items will
  be tracked as follow-up issues, not absorbed.

## Required deliverable structure

Each reviewing agent returns a single Markdown report with this
skeleton:

```markdown
# Wave 2b Final Pre-Merge — <agent-name> Review of PR #30

## Summary
- Verdict: [Block / Conditional / Approve]
- CRITICAL: N · HIGH: N · MEDIUM: N · LOW: N · NIT: N
- One-sentence headline of the highest-severity finding.

## Findings

### F-<phase>-<NN> · <SEVERITY> · <one-line headline>
- **File:** `path/to/file.py:LINE` (or `:LINE-RANGE`)
- **What's wrong:** <1-3 sentences — concrete defect, not vague concern>
- **User-visible consequence:** <what an operator sees / loses>
- **Suggested fix:** <code or text snippet>
- **Regression test:** <test file + assertion stub>

(repeat per finding, ordered: CRITICAL → HIGH → MEDIUM → LOW → NIT)

## Cross-phase observations
(F-XPR-NN entries, same structure)

## Prior-round carry-overs verified
- F-21-03 [Rounds-1-5 verified] — atomic rewrite now fsyncs before replace (`_purge.py:_atomic_rewrite_dropping_lines`)
- F-36-01 [Rounds-1-5 verified] — Annex IV writer/verifier share `compute_annex_iv_manifest_hash`
- (etc. — at minimum one entry per phase that was touched by absorption)

## What this report deliberately did not cover
(Out-of-scope items the agent looked at and declined to flag, with
one sentence each. This keeps the maintainer from re-treading the
same ground.)

## Merge recommendation
- One paragraph: "Ship as-is" / "Ship after addressing F-XX-NN
  (single blocker)" / "Block — see CRITICAL findings". This is the
  agent's call. The maintainer arbitrates between agents.
```

## How to launch

Spawn at minimum these agents in parallel:

1. **Code-correctness agent** — focuses on Phase 21 / 35 / 36
   implementation defects (the largest surfaces). Read
   `_purge.py`, `_cache.py`, the verification toolbelt
   (`_safety_eval.py`, `_verify_annex_iv.py`, `_verify_gguf.py`)
   end-to-end. Trace the writer/verifier round-trip and the per-run
   audit-age lookup with paper-and-pencil walk-throughs.
2. **Public-API agent** — focuses on Phase 19
   (`forgelm/__init__.py`) and Phase 16
   (`tools/check_field_descriptions.py`). Verify lazy-import
   discipline, `__dir__` completeness, `__api_version__` policy,
   AST-scanner false-positive / false-negative behaviour.
3. **Standards-compliance agent** — focuses on cross-phase checks
   (XPR-01 through XPR-09) against
   [docs/standards/](../../standards/). Audit-event vocabulary,
   exit codes, JSON envelope schema, regex / ReDoS exposure,
   error-handling discipline.
4. **Test-rigor agent** — focuses on whether the tests in
   `test_purge.py`, `test_cache_subcommands.py`,
   `test_verification_toolbelt.py`, `test_gdpr_erasure.py`,
   `test_library_api.py` actually verify what they claim to. Hunt
   for vacuous assertions and missing edge-case coverage on the
   contracts the absorption rounds tightened.

Each agent gets this prompt verbatim plus a one-line `Focus:`
directive naming its specialty. Agents must not coordinate; the
maintainer deduplicates after.

## Delivery

- Agents return their reports in
  `docs/analysis/code_reviews/wave2b-final-<agent>.md`.
- The maintainer (Cemil) merges findings, dedups, and posts the
  unified list on PR #30 as a top-level comment.
- Block / Conditional / Approve gating decision rests with the
  maintainer after consolidation, **not** with any individual agent.
- After this round, surviving findings will be addressed in a single
  final absorption commit (or skipped with a documented reason), and
  the branch will be merged to `main`. There is no Round-7.

---

*Prompt frozen 2026-05-05 against `closure/wave2b-integration` HEAD `36afbc0`.*

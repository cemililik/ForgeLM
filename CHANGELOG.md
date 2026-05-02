# Changelog

All notable changes to ForgeLM are documented here.

## [Unreleased]

> **Active cycle:** v0.5.5 closure — a single-release consolidation of
> the master review's 175 findings + 4 new feature tracks (Library API,
> ISO 27001 / SOC 2 alignment, GDPR right-to-erasure, Article 14 real
> staging directory). Detailed plan:
> [closure-plan-202604300906.md](docs/analysis/code_reviews/closure-plan-202604300906.md).
> No interim releases; v0.5.5 ships once Faz 1-33 are complete.
> Per-PR CHANGELOG entries below collapse into the v0.5.5 release
> notes at tag time.

### Added — Wave 1 closure (Faz 9, 11, 12, 13, 25, 31, 32 — see PR description)

- **Article 14 staging directory + `forgelm approve` / `forgelm reject` (Faz 9)** —
  When `evaluation.require_human_approval=true`, the trainer now saves the
  final adapters to `final_model.staging/` instead of writing to
  `final_model/` before review. Two new CLI subcommands manage the gate:
  `forgelm approve <run_id> --output-dir <dir>` atomically renames
  `final_model.staging/` → `final_model/` (with a `shutil.move` fallback on
  cross-device output mounts) and emits a `human_approval.granted` audit
  event plus a `notify_success` webhook; `forgelm reject <run_id>` records a
  `human_approval.rejected` event and leaves the staging directory in place
  for forensic review. Both commands resolve the approver identity via
  `FORGELM_OPERATOR` → `getpass.getuser()` → `"anonymous"`, mirroring
  `AuditLogger.operator`. The `human_approval.required` audit event payload
  now also carries `staging_path` and `run_id` so downstream tooling can
  cross-check the approval against the originating run.
- **`evaluation.staging_ttl_days` config field (Faz 9)** — documents the
  retention horizon for `final_model.staging/` after a `forgelm reject`;
  default 7 days. Auto-deletion enforcement is deferred to Phase 21
  (GDPR right-to-erasure); v0.5.5 surfaces the policy in the compliance
  manifest only.
- **`forgelm.wizard._print` indirection (Faz 11)** — 85 `print()` calls
  replaced with a testable `_print()` helper (mirrors the chat.py pattern).
  Coverage omit list emptied; wizard is now visible to coverage measurement.
  Closes F-code-105, F-test-003, F-code-019.
- **`tests/_helpers/factories.py` (Faz 12)** — single canonical
  `minimal_config(**overrides)` factory replaces 4 scattered local
  `_minimal_config` definitions and 7 `from conftest import` indirections.
  Closes F-test-004, F-test-005, F-code-015.
- **`forgelm --data-audit` deprecation (Faz 13)** — legacy flag emits
  `DeprecationWarning` + a `cli.legacy_flag_invoked` audit event;
  scheduled for removal in v0.7.0. Closes F-code-107, F-business-024.
- **6 enum-shaped config fields tightened to `Literal[...]` (Faz 10)** —
  `LoraConfig.bias`, `DistributedConfig.fsdp_backward_prefetch` /
  `fsdp_state_dict_type`, `SafetyConfig.scoring`,
  `ComplianceMetadataConfig.risk_classification`, `TrainingConfig.galore_optim` /
  `galore_proj_type`. Pydantic now validates whitelist at parse time;
  bespoke runtime validators removed. Closes F-code-101, F-compliance-105.
- **`tools/check_site_claims.py` (Faz 25)** — site-as-tested-surface CI
  guard; AST-parses `forgelm/compliance.py`, `forgelm/quickstart.py`,
  `forgelm/trainer.py`, `pyproject.toml` and diffs against site HTML to
  catch claim/code drift. Wired into `ci.yml` (`--strict` mode).
- **`docs/standards/localization.md` "Supported languages" section (Faz 25)**
  — codifies that EN+TR are authored at site AND user-manual levels, while
  DE/FR/ES/ZH are site-translated only and the user-manual side falls back
  to English via the i18n chain. Closes F-loc-001, F-loc-003, Theme α.
- **`.github/workflows/publish.yml` cross-OS release matrix (Faz 31)** —
  tag-driven `build → cross-os-tests → publish` chain over 3 OS × 4 Python
  = 12 combinations; packaged-wheel install (not editable); SBOM artifact
  upload per combo; OIDC trusted publishing. Closes F-test-007.
- **`tools/generate_sbom.py` (Faz 31)** — stdlib-only CycloneDX 1.5
  emitter; called from each `cross-os-tests` matrix combo to produce a
  per-OS-and-Python SBOM artifact.
- **`.pre-commit-config.yaml` (Faz 32; optional)** — opt-in local hooks
  (`ruff`, `ruff-format`, `gitleaks`, trailing-whitespace,
  end-of-file-fixer, check-yaml/-toml, check-merge-conflict). CI keeps
  enforcing the same checks; pre-commit is ergonomic optimization, not a
  duplicate enforcement boundary. Closes F-test-008.
- `tests/test_human_approval_gate.py` — 15 new tests covering the staging
  → approve / reject flow, stale-staging detection, atomic-rename race,
  cross-device move, audit chain integrity. Total suite: 951+ tests.

### Added — Foundation bundle (PR #19, Faz 1-8)

- `forgelm verify-audit` subcommand + library function
  `forgelm.compliance.verify_audit_log` (Faz 6 — closes F-compliance-103
  Critical).
- `forgelm._http.safe_post` — single boundary for outbound HTTP with
  SSRF guard, redirect refusal, scheme policy, timeout floor, TLS
  pinning, secret-mask error reasons (Faz 7 — closes M-201 Major).
  Migrated webhook + judge + synthetic call sites.
- `WebhookNotifier.notify_reverted` and `notify_awaiting_approval` —
  paired with `training.reverted` and `approval.required` events
  (Faz 8 — closes F-compliance-104 Major).
- `SafetyEvalThresholds` dataclass — bundles five Phase 9 knobs so
  `run_safety_evaluation` stays under the 13-param ceiling (Faz 4 v2
  + complexity refactor).
- `audit.classifier_load_failed` audit event with `audit_logger=`
  parameter on `run_safety_evaluation` (Faz 3 — closes F-compliance-120
  Minor).
- `tests/test_lazy_imports.py` — regression test pinning that
  `import forgelm.trainer` / `import forgelm.model` do not eagerly
  load torch (Faz 4 — closes F-performance-101 Major).
- `docs/reference/audit_event_catalog.md` + TR mirror — comprehensive
  event vocabulary with payload schemas (Faz 3 + Faz 8 union).
- `docs/standards/release.md` "Deprecation cadence" section (Faz 2
  — closes F-business-011 Major).

### Changed

- `AuditLogger` — operator identity raises `ConfigError` instead of
  falling back to literal `"unknown"` (Faz 3 — closes F-compliance-102
  Critical). `getpass.getuser()@socket.gethostname()` chain with
  `FORGELM_ALLOW_ANONYMOUS_OPERATOR=1` escape hatch.
- `AuditLogger.log_event` — `os.fsync(f.fileno())` after flush; chain
  durability across power-cut (Faz 3 — closes F-compliance-114 Major).
- `compute_dataset_fingerprint` — split into three helpers (local file
  / HF metadata / HF revision); HF Hub revision SHA pinned (Faz 3
  — closes F-compliance-117 Minor + complexity refactor).
- `_generate_safety_responses` and `_generate_responses_batched` —
  `batch_size=8` default with token-pad-longest + per-batch CUDA-OOM
  fallback to single-prompt (Faz 4 — closes F-performance-102 Major).
  Per-batch error handling extracted to `_generate_*_batch_with_oom_retry`
  helpers.
- `_chunk_paragraph_tokens` — single-encode + offset slicing (Faz 4
  — closes F-performance-103 Major).
- `_post_payload` — delegates to `safe_post` with `min_timeout=1.0`
  for back-compat (Faz 7).
- 7 notebooks — install from PyPI (`forgelm[qlora]==0.5.0`) instead
  of `git+https://...` (Faz 5 — closes F-business-005 Major).
- CI now enforces `pytest --cov-fail-under=40` via `pyproject.toml`
  `addopts` (Faz 2 — closes F-test-001 Critical).
- CI matrix `fail-fast: false`; `usermanuals-validate.yml` runs on
  push + PR (Faz 2 — closes F-test-006 + F-test-017 Major).
- Site honesty: `compliance.html` artefact tree, `quickstart.html`
  template names, GPU stat (16 vs claimed 18) — all refreshed against
  real code (Faz 1 — closes F-business-001/002/004 Critical+Major).
- QMS `sop_data_management.md` — single v0.5.0 story; v0.5.1+/v0.5.2
  splits removed (Faz 1 — closes M-DOC-001 Critical).
- Roadmap (`roadmap.md`, `roadmap-tr.md`, `releases.md`) — v0.5.0
  marked released; tristate status legend added (Faz 1 — closes
  F-business-003 Critical).
- `forgelm.webhook` exports `_is_private_destination` via `__all__`
  for back-compat (Faz 7).

### Documentation

- Full Faz 1-8 closure plan:
  [closure-plan-202604300906.md](docs/analysis/code_reviews/closure-plan-202604300906.md)
  (33 phases, ~47 PRs).
- Master review:
  [master-review-opus-202604300906.md](docs/analysis/code_reviews/master-review-opus-202604300906.md)
  (175 findings).
- `data_audit/` + `cli/` package split design:
  [split-design-data_audit-cli-202604300906.md](docs/analysis/code_reviews/split-design-data_audit-cli-202604300906.md)
  (Faz 14-15 forward-looking).

### Deprecated

- **`forgelm --data-audit PATH`** — the legacy flag now emits a
  `DeprecationWarning` and an `cli.legacy_flag_invoked` audit-log event
  on every invocation. Behaviour is unchanged; the flag is scheduled for
  removal in **v0.7.0**. Migrate to the `forgelm audit PATH` subcommand
  (same output, same exit codes). See
  [docs/standards/release.md](docs/standards/release.md#deprecation-cadence) for
  the removal timeline.

### Changed (Wave 1)

- `WebhookNotifier.notify_awaiting_approval(run_name, model_path)` is now
  wired into the human-approval gate so an operator-facing webhook fires the
  moment the model is staged. Receivers can opt out via
  `webhook.notify_on_awaiting_approval=false`.
- **`forgelm/data_audit.py` -> `forgelm/data_audit/` package (Faz 14)** —
  the 3098-line monolith was split into a 14-module package
  (`_optional`, `_types`, `_pii_regex`, `_pii_ml`, `_secrets`, `_simhash`,
  `_minhash`, `_quality`, `_streaming`, `_aggregator`, `_splits`,
  `_summary`, `_croissant`, `_orchestrator`) per the
  cohesion ceiling in `docs/standards/architecture.md`. The public
  `forgelm.data_audit.X` import surface — including the
  test-touched private helpers (`_HAS_PRESIDIO`, `_get_presidio_analyzer`,
  `_token_digest`, `_strip_code_fences`, `_row_quality_flags`,
  `_read_jsonl_split`, `_count_leaked_rows`, `_find_near_duplicates_brute`,
  `_is_credit_card`, `_is_tr_id`, `_require_presidio`,
  `_PRESIDIO_ENTITY_MAP`, etc.) — is preserved by `__init__.py` re-exports
  so external callers (`forgelm.ingestion`, `forgelm.wizard`) and the
  test suite keep working without code changes. Closes F-code-103 (Major).
  See
  [split-design-data_audit-cli-202604300906.md](docs/analysis/code_reviews/split-design-data_audit-cli-202604300906.md)
  §1 for the design.
- **`forgelm/cli.py` → `forgelm/cli/` package (Faz 15)** — the ~2300-line
  monolith was split into a 24-module package (subcommands/, `_dispatch`,
  `_training`, `_dry_run`, `_result`, `_resume`, `_logging`, `_exit_codes`,
  etc.). The `forgelm.cli:main` entry point and `python -m forgelm.cli` are
  preserved; dispatcher uses late-binding facade re-resolution so test
  monkeypatches (`forgelm.cli._run_chat_cmd` etc.) keep resolving correctly.
  Closes F-code-104. See split-design §2.
- **16 broad `except Exception` sites narrowed (Faz 27)** — `_streaming.py`,
  `trainer.py`, `safety.py`, `judge.py`, `compliance.py`, `ingestion.py`
  narrow to specific exception classes; 7 sites retained with `# noqa: BLE001`
  and rationale comments per `docs/standards/error-handling.md` carve-out.
  C-55 resolved: MoE expert-name resolver migrated from hardcoded substring
  match to regex-registry (`_EXPERT_NAME_PATTERNS`) covering Mixtral, Qwen 3
  MoE, DeepSeek-V3, Phi-MoE. Closes F-code-106.
- **Audit event catalog and CLI sample drift fixed (Faz 29)** — placeholder
  `<TBD>` entries in `audit_event_catalog.md` filled; trailing-whitespace
  cleaned; CLI help sample in `docs/reference/usage.md` brought in sync with
  current subcommand surface.

### Removed

- **`[ingestion-secrets]` extra (`detect-secrets>=1.5.0,<2.0.0`)** —
  reserved during Phase 12 for a follow-up integration that never landed.
  The `detect-secrets` scanner expects file paths while ForgeLM audits
  row-level JSONL streams, so the wire-up was rejected as architecturally
  incompatible. The prefix-anchored regex set in
  `forgelm/data_audit/_secrets.py` (9-family coverage: AWS, GitHub,
  Slack, OpenAI, Google API, JWT, OpenSSH, PGP, Azure storage) is the
  sole detection backend and stays the sole detection backend. Removed
  the dead extra from `pyproject.toml`, the install snippet from
  `README.md`, and the "fallback regex set" framing from the secrets
  module docstring. Closes C-53 (deferred from v0.5.0).

---

## [0.5.0] — 2026-04-30

**Theme:** "Document Ingestion + Data Curation Pipeline" — Phases 11,
11.5, 12, and 12.5 ship as one comprehensive release.

> **Note on consolidation.** Originally planned as four sequential
> PyPI tags (`v0.5.0` / `v0.5.1` / `v0.5.2` / `v0.5.3`) but consolidated
> into a single `v0.5.0` because the four phases form one coherent
> surface (ingest → polish → mature → polish) that's hard to use in
> parts. Git history retains the four phases as separate commit
> batches; this entry collapses them into the user-facing release
> notes. Section markers below preserve the phase boundary so
> reviewers can map back to [docs/roadmap/releases.md](docs/roadmap/releases.md).

The release adds:

- **Phase 11** — `forgelm ingest` (PDF / DOCX / EPUB / TXT / Markdown
  → SFT-ready JSONL) + `forgelm audit` (length / language /
  near-duplicate / cross-split leakage / PII) + EU AI Act Article 10
  governance integration.
- **Phase 11.5** — operational polish on the Phase 11 surface: LSH
  banding, streaming reader, token-aware chunking, PDF
  header/footer dedup, PII severity tiers, atomic audit writes.
- **Phase 12** — data curation maturity: MinHash LSH dedup option,
  markdown-aware splitter, code/secrets leakage tagger, heuristic
  quality filter, DOCX table preservation.
- **Phase 12.5** — small additive polish: `--all-mask` shorthand,
  Croissant 1.0 dataset card emission, optional Presidio ML-NER PII
  adapter, wizard "audit first" entry point.

CI / docs / standards bookkeeping accompanying every phase is folded
into "Cross-cutting review hardening" at the bottom (rounds 1–12 of
review-cycle fixes applied across the four phases above).

---

### Phase 12.5 — Data Curation Polish (backlog items #1–#4)

Four follow-up items from
[`docs/roadmap/phase-12-5-backlog.md`](docs/roadmap/phase-12-5-backlog.md)
ship together — none require new architecture; each is a small
additive surface on top of the Phase 12 ingestion + audit lineage.

- **`forgelm ingest --all-mask`** (item #3) — one-flag shorthand for
  `--secrets-mask --pii-mask` in the documented mask order (secrets
  first so combined detectors don't double-count overlapping spans).
  Composes additively with explicit flags (set-union, no error). Pure
  UX; no new behaviour.
- **`forgelm audit --croissant`** (item #2) — opt-in
  [Google Croissant 1.0](http://mlcommons.org/croissant/) dataset card
  emitted under a new `croissant` key in `data_audit_report.json`. The
  card carries dataset-level identity, one `cr:FileObject` per JSONL
  split, and a `cr:RecordSet` per split with `cr:Field` entries
  derived from the audit's column detection. Existing audit JSON keys
  are byte-equivalent — the block stays empty when the flag is off
  (same precedent as `secrets_summary` / `quality_summary`). Lets the
  same JSON file double as both the EU AI Act Article 10 governance
  artifact and a Croissant-consumer dataset card.
  - `url` and `contentUrl` use the as-typed input string and the
    relative split filename, never the resolved absolute filesystem
    path, so cards published to HuggingFace / MLCommons don't leak
    the auditor's local layout.
  - Croissant `version` (`sc:version`, dataset version) is omitted
    deliberately — the audit doesn't have first-class evidence for
    it; vocab conformance is declared via `conformsTo`. Operators
    that publish hand-edit `version` like they do `license` /
    `citeAs`.
  - The card is now also surfaced in the `--output-format json`
    stdout envelope alongside the on-disk report so CI consumers
    don't need a second file slurp.
- **`forgelm audit --pii-ml [--pii-ml-language LANG]`** + new
  `[ingestion-pii-ml]` extra (item #1) — opt-in
  [Presidio](https://github.com/microsoft/presidio) ML-NER PII detector
  layered on top of the existing regex detector. Adds the
  unstructured-identifier categories the regex inherently misses
  (`person`, `organization`, `location`) into the same `pii_summary` /
  `pii_severity` blocks under disjoint category names. Severity tiers
  in the new `PII_ML_SEVERITY` table: `person → medium`,
  `organization → low`, `location → low` (deliberately below the regex
  `critical`/`high` tiers because NER false-positive rates are
  materially higher than regex-anchored detection). The pre-flight
  check covers BOTH the missing-extra branch AND the missing-spaCy-model
  branch — `presidio-analyzer` does *not* transitively ship a spaCy
  NER model, so the install recipe is now two lines:
  ```bash
  pip install 'forgelm[ingestion-pii-ml]'
  python -m spacy download en_core_web_lg
  ```
  Without either, `forgelm audit --pii-ml` raises `ImportError` with
  the recipe before any rows are scanned. Per-row Presidio failures
  are scoped to `(ValueError, RuntimeError)` so a single malformed row
  never blocks the audit, but a deep `OSError` from a missing model
  surfaces loudly instead of silently scoring zero ML coverage.
  `--pii-ml-language` (default `"en"`) lets non-English corpora point
  at the matching spaCy model; Presidio raises a typed exception when
  no engine is registered for the requested language.
- **Wizard "audit first" entry point** (item #4) — when the wizard
  resolves a JSONL (either typed directly or produced by the
  Phase 11.5 `_offer_ingest_for_directory` ingest flow), it now offers
  to run `forgelm audit` on it inline and prints `summarize_report`'s
  verdict before continuing. Mirrors the
  `_offer_ingest_for_directory` shape exactly. Closes the BYOD audit
  loop end-to-end. Audit is informational, not a gate — failures fall
  through to the "continue without audit" path.

Touch points (so the next reviewer can audit blast radius quickly):

- `forgelm/ingestion.py` — no module changes (the flag composes at the
  CLI boundary into the existing `pii_mask` / `secrets_mask` booleans).
- `forgelm/cli.py` — three new flags on the existing subparsers
  (`--all-mask` on `forgelm ingest`; `--croissant` and `--pii-ml` on
  `forgelm audit`); dispatcher signatures threaded through.
- `forgelm/data_audit.py` — `_HAS_PRESIDIO` sentinel, `_require_presidio`,
  `_get_presidio_analyzer` (cached), `detect_pii_ml`,
  `PII_ML_SEVERITY`, `PII_ML_TYPES`, `_PRESIDIO_ENTITY_MAP`,
  `_build_croissant_metadata`, `_CROISSANT_CONTEXT`. New
  `enable_pii_ml` / `emit_croissant` parameters on `audit_dataset` /
  `_process_split` / `_audit_split`; new `enable_pii_ml` field on
  `_StreamingAggregator`; new `croissant` field on `AuditReport`.
  `_build_pii_severity` now consults the merged
  `PII_SEVERITY ∪ PII_ML_SEVERITY` table.
- `forgelm/wizard.py` — new `_offer_audit_for_jsonl(path)` helper;
  invoked from `_offer_ingest_for_directory` (after ingest produces
  a JSONL), `_validate_local_jsonl` (after a directly-provided JSONL
  passes validation), and `_prompt_dataset_path_with_ingest_offer`
  (after a non-directory JSONL is provided to the full wizard).
- `pyproject.toml` — new `[ingestion-pii-ml]` extra
  (`presidio-analyzer>=2.2.0,<3.0.0`).
- `tests/test_phase12_5.py` — 11 new tests, four classes (one per
  backlog row).
- `tests/test_wizard_byod.py` — three existing tests get an extra
  `"n"` answer to decline the new audit-first offer (the offer
  behaviour has its own coverage in `test_phase12_5.py`).
- Docs — `README.md` install matrix + Phase 12.5 feature line;
  `docs/standards/architecture.md` extras matrix; `docs/guides/ingestion{,-tr}.md`
  + `docs/guides/data_audit{,-tr}.md` get dedicated sections per
  feature; `notebooks/data_curation.ipynb` mentions `--all-mask` and
  the Phase 12.5 audit add-ons inline.

### Fixed — post-PR-#13 review-cycle batches (rounds 8-12)

Inline-comment batches landing on top of PR #13 (now merged to `main`).
Same review surface as rounds 4-7; further hardening on top of the
`v0.5.2` content.

- **Audit log hardening** (`forgelm/compliance.py`) — HMAC `_hmac` field is now
  emitted only when `FORGELM_AUDIT_SECRET` is set; without a secret, a key
  derived solely from the public `run_id` would be forgeable, so we no longer
  claim tamper-evidence we cannot deliver. `log_event` re-reads the chain head
  from disk under the same `flock` so two writers sharing the same log can no
  longer fork the chain. `_read_chain_head` refuses to derive a head from a
  tail that does not end with `\n` (truncated last record). The oversize-
  final-entry case is recovered by re-reading from `seek_start` without
  skipping the partial first line.
- **Deployer-instructions Markdown injection** (`forgelm/compliance.py::generate_deployer_instructions`) —
  config-derived strings (`system_name`, `model.name_or_path`, fine-tuning
  method, model location, foreseeable-misuse bullets, metric names) now go
  through `_sanitize_md` before template substitution; pipes / backticks /
  link syntax in any of those can no longer break out of table cells or
  bullets in the generated Article 13 document.
- **Quality-filter denominator** (`forgelm/data_audit.py::_build_quality_summary`) —
  `overall_quality_score` now divides by the number of rows the filter
  actually evaluated (text-bearing dict rows) instead of `total_samples`.
  A corpus that's 50 % null but 100 % clean on the rest now reads `1.0`
  instead of `0.5`.
- **NumPy-fast-path bits guard** (`forgelm/data_audit.py::compute_simhash`) —
  the `_compute_simhash_numpy` dispatch now also gates on `bits <= 64`;
  without it, `np.uint64` would silently truncate digests wider than 64
  bits.
- **Sliding-overlap clamp** (`forgelm/ingestion.py::ingest_path`) — when
  `--overlap` is not passed and the strategy is `sliding`, the implicit
  `DEFAULT_SLIDING_OVERLAP` (200) is now clamped to `chunk_size // 2`. A
  small `--chunk-size 300` used to trip `_chunk_sliding`'s
  "overlap > chunk_size // 2" guard with the default overlap — surfacing
  as a confusing error for a knob the user did not set.
- **Batch-tokenizer narrow except** (`forgelm/ingestion.py::_count_section_tokens`) —
  the bare `except Exception` around the batched `tokenizer(blocks)` call
  is now narrowed to `(TypeError, ValueError)` (the documented
  unsupported-batch signal); the returned `BatchEncoding` is shape-
  validated before its `input_ids` is consumed. Real bugs (corrupted
  input, OOM, etc.) no longer mask behind the slow per-block fallback.
- **Webhook secret-fallback safety** (`forgelm/webhook.py`) —
  `requests.post` now passes `allow_redirects=False` (an SSRF-pre-validated
  URL cannot be redirected to a private destination) and the
  `mask_secrets` `ImportError` fallback emits `[REDACTED — secrets
  masker unavailable]` instead of the raw 512-char reason prefix.
  See [#14](https://github.com/cemililik/ForgeLM/issues/14) for the
  remaining DNS-rebinding TOCTOU follow-up tracked for `v0.5.3`.
- **Trainer governance failure visibility** (`forgelm/trainer.py`) — the
  `data_governance_report.json` export try/except now catches the full
  `Exception` set (was `OSError` only) so non-IO failures (`TypeError`,
  `ValueError`, `AttributeError`) still surface as
  `compliance.governance_failed` audit events instead of crashing the
  surrounding compliance flow. The rollup `compliance.artifacts_exported`
  event is gated on a `governance_ok` flag so the audit chain truthfully
  reflects which artefacts are actually on disk.
- **Compliance manifest exception narrowing** (`forgelm/compliance.py`) —
  the broad `except Exception` around the HF Hub `load_dataset_builder`
  fingerprint fetch is now a tuple of realistic failure modes
  (`ImportError`, `FileNotFoundError`, `ValueError`, `AttributeError`,
  `ConnectionError`, `TimeoutError`).
- **Strict messages-format validation** (`forgelm/data.py`) —
  `_process_messages_format` now explicitly checks `isinstance(role, str)`
  and `isinstance(content, str)` before formatting; non-string content
  (dicts, ints) used to be silently coerced via f-string `__format__`
  and slip through into training.
- **Wizard ASCII regex flag** (`forgelm/wizard.py`) — `_HF_HUB_ID_RE`
  now compiles with `re.ASCII` so the `\w` class means
  `[A-Za-z0-9_]`. HF Hub IDs are ASCII-only, and Unicode-aware `\w`
  would otherwise accept characters the Hub itself rejects.
- **GGUF converter case-insensitive validation** (`forgelm/export.py`) —
  the `FORGELM_GGUF_CONVERTER` `.py` suffix check now uses
  `casefold()` (cross-platform: HFS+/NTFS), and `export_model()`'s
  catch widened from `(ImportError, FileNotFoundError)` to also
  include `ValueError` so a non-`.py` env override produces an
  `ExportResult` instead of crashing the caller.
- **Markdown chunker complexity refactor** (`forgelm/ingestion.py`) —
  `_chunk_markdown_tokens` split into `_build_markdown_section_blocks`
  (render breadcrumb + body), `_count_section_tokens` (batch tokenizer
  call with per-block fallback), and the main chunker (greedy packing).
  Cognitive complexity drops from 16 → ~8.
- **Bidirectional MinHash extraction** (`forgelm/data_audit.py`) — the
  two near-identical `a→lsh_b` / `b→lsh_a` query loops in
  `_count_leaked_rows_minhash_bidirectional` were extracted into one
  `_count_leaks_against_index` helper. Complexity drops from 24 → ~5;
  the SonarCloud duplication metric on this file goes away.
- **Streaming length digest** (`forgelm/data_audit.py`) — the per-split
  text-length distribution is now accumulated via a bounded
  `_LengthDigest` (Algorithm R reservoir, 100K cap) instead of an
  unbounded `List[int]`. Audit memory on multi-million-row splits is
  now O(1) instead of O(n).
- **Documentation drift sweep (round N)** — five compliance-summary
  links repointed to `../../forgelm/...`, two missing FSDP knobs
  (`fsdp_backward_prefetch`, `fsdp_state_dict_type`) and two webhook
  knobs (`allow_private_destinations`, `tls_ca_bundle`) added to both
  EN and TR `configuration` reference; Pro CLI section added to
  `README.md`; CI now runs a bilingual H2 parity check across seven
  EN/TR doc pairs (`configuration`, `usage`, `distributed_training`,
  `data_preparation`, `architecture`, `ingestion`, `data_audit`); test
  count refreshed to 47 in `CONTRIBUTING.md` to match
  `architecture.md`; secrets list aligned to the full nine families
  in `forgelm.data_audit.SECRET_TYPES` (was missing two private-key
  splits + Azure storage in some prose).
- **Phase 12 fenced log block** in both `usage.md` and `usage-tr.md`
  now uses ```` ```text ```` so markdownlint MD040 stops flagging it.

### Fixed — multi-agent master review (rounds 4-7)

Multi-dimension review (business, code, compliance, documentation, performance, security) surfaced a cluster of correctness, claim/evidence, and silent-failure issues that have been swept in batches.

- **Version drift** — `forgelm.__version__` was hard-coded to `0.5.0rc1` in [`forgelm/__init__.py`](forgelm/__init__.py) while `pyproject.toml` declared `0.5.2rc1`. The literal is now derived from the installed distribution via `importlib.metadata.version("forgelm")` (with a `0.0.0+dev` fallback for raw source checkouts), and `compliance._get_version()` follows the same resolution path so audit / Annex IV manifests stamp the correct producer version.
- **Audit log integrity** (`forgelm/compliance.py::AuditLogger`) — `_load_last_hash` previously re-rooted the chain to `"genesis"` on any read failure with only a `logger.debug` message; `log_event` advanced `_prev_hash` *before* the file write and swallowed write failures with `logger.warning`. Both paths now distinguish file-missing from file-unreadable, raise on real I/O errors, and only advance the hash chain after a successful write.
- **`compute_dataset_fingerprint` TOCTOU** — `@lru_cache(maxsize=32)` keyed on the path string only would return stale fingerprints when the file was rewritten in place. Cache dropped; symlinks resolved before hashing; `os.stat()` now captured atomically alongside the SHA-256 stream so size/mtime cannot drift between the two reads.
- **`generate_data_governance_report` wiring** — defined and tested but never called from production code. Now invoked by `_export_compliance_if_needed` so `data_governance_report.json` actually lands in the trainer's `output_dir` per EU AI Act Article 10.
- **Silent-failure sweep** — replaced `except Exception:` swallows with concrete-class catches + log + raise/sentinel: `data.py::_process_messages_format` (catches malformed message rows by exception class, raises an explicit `ValueError`), `safety.py::_release_model_from_gpu` (`RuntimeError`/`OOM` only), `cli.py::_load_config_or_exit` (split `yaml.YAMLError` + `pydantic.ValidationError` for clearer error messages), `config.py::ForgeConfig.load_config` (specific Pydantic / YAML branches).
- **Pydantic schema discipline** — six bare-`str` fields (`trainer_type`, `merge.method`, `model.backend`, `distributed.fsdp_strategy`, `risk_assessment.risk_category`, `monitoring.metrics_export`) converted to `Literal[...]` so JSON Schema / IDE auto-complete surfaces the allowed values; redundant runtime validators dropped.
- **Webhook hardening** — `forgelm/webhook.py` now refuses non-loopback private destinations without explicit opt-in (`webhook.allow_private_destinations`), runs the failure-reason payload through `mask_secrets`, passes `verify=True` explicitly to `requests.post`, and rejects `timeout < 1`.
- **Performance** — `forgelm/trainer.py` lazy-imports `torch` / `transformers` / `trl` into method bodies, dropping CLI cold-start cost by ~700-1500 ms on `forgelm audit` and `forgelm --help`. Audit's `agg.minhashes` is no longer copied via `list(...)` before LSH (saves ~1 GB on 1M-row splits).
- **Documentation** — refreshed module / test / notebook counts in `CONTRIBUTING.md` and `docs/reference/architecture.md`; added `forgelm/templates/` to the directory layout. Removed `forgelm chat --safety` from `usage.md` (flag does not exist in `cli.py`). `coverage.fail_under` in `docs/standards/testing.md` now matches `pyproject.toml` (40, not 25).

### Fixed — round 3.5 review (`_MARKDOWN_CODE_FENCE` regex → non-regex parser)

SonarCloud `python:S5852` flagged `_MARKDOWN_CODE_FENCE` (`forgelm/ingestion.py` L515) — the regex `^ {0,3}(?P<fence>` `` ` ``{3,}|~{3,})(?P<rest>[^\n]*)$` had **two unbounded greedy quantifiers in sequence over overlapping character classes** (the fence run is `` ` `` / `~`; the `rest` capture's `[^\n]` includes both fence chars), the textbook polynomial-runtime shape per regex.md rule 4.

- Empirically linear in CPython (50K-char pure-backtick run = 16 μs), but the static analyser can't prove that — and we already use non-regex line walkers everywhere else for markdown parsing (regex.md rule 6).
- Replaced with `_parse_md_fence(line)` — a non-regex parser that returns `(fence_char, run_length, rest_after_run)` or `None`. Provably O(n) per line; 100K-char pure-backtick run measures ~10 μs.
- `_markdown_sections` updated to use the helper directly (no behavioural change — the helper returns the same tuple shape the regex's named groups did).
- 2 new regression tests in `tests/test_phase12_review_fixes.py::TestRegexLinearity` — `test_parse_md_fence_linear_on_long_runs` (≤ 100 ms cap on N=100K) + `test_parse_md_fence_behaviour` (pinned outputs for opener with info string, 4-char fence, 2-space indent, 4-space indent → None, sub-3-char run → None, mismatched chars after run).

### Fixed — round 3 review (post-`69ee6ab`)

Round-3 review caught two real correctness bugs (Unicode `\w` in
secret regexes, fence-length rule violation in markdown / code-fence
tracking) plus a handful of doc / fixture parity issues. All applied.

- **`re.ASCII` flag on secret regexes** (`forgelm/data_audit.py`) —
  Last commit changed `[A-Za-z0-9_-]` → `[\w-]` in `github_token` /
  `openai_api_key` / `google_api_key` / `jwt`, but Python's default
  `\w` is **Unicode-aware** (matches `ünicode`, `türkçe`, …), which
  would broaden the match universe to include non-ASCII chars that
  real credentials never contain. Added `flags=re.ASCII` to all four
  patterns so `\w` is restricted to ASCII. Patterns that already use
  explicit ASCII character classes (`aws_access_key`, `slack_token`,
  the explicit `[A-Z0-9]` ones) are unchanged.
- **`regex.md` Rule 1 corrected** — Previous wording stated
  `[A-Za-z0-9_]` and `\w` are equivalent in Python. They are not.
  Rewrote the rule with a side-by-side example showing the Unicode /
  ASCII divergence, plus a decision table: ASCII-only inputs → `\w`
  with `re.ASCII` (or explicit class), natural-language inputs →
  bare `\w` (Unicode-aware), mixed → be explicit.
- **CommonMark fence-length rule enforced** (`forgelm/data_audit.py`
  + `forgelm/ingestion.py`) — CommonMark §4.5 requires the closing
  fence to use **at least as many** fence characters as the opener.
  Both `_strip_code_fences` and `_markdown_sections` previously
  tracked only the fence character, so a 4-backtick opener (` ```` `)
  was prematurely closed by a 3-backtick line. `_is_code_fence_open`
  now returns `(char, run_length)`; `_is_code_fence_close` accepts
  the minimum run-length and rejects shorter closes. The markdown
  splitter's `_MARKDOWN_CODE_FENCE` regex captures the fence run
  (`(?P<fence>...)`) and the rest of the line (`(?P<rest>...)`) so
  the splitter can also enforce "no info string on close" alongside
  the length rule. All three CommonMark §4.5 close-side rules
  (matching char + run length ≥ open + no info string) now hold.
- **`data_audit.md` reframes `[ingestion-secrets]`** — The doc
  previously implied installing the extra layered `detect-secrets`
  on top of the regex fallback. The current code does not invoke
  `detect-secrets` at all. Reworded as forward-compatibility:
  installing the extra is safe to pin in requirements files but
  doesn't change audit behaviour today.
- **`README` clarifies `semantic` chunking strategy** — Listed as
  reserved/planned: the implementation raises `NotImplementedError`
  and the CLI hides it from `--strategy` choices. Previous wording
  implied it was available at runtime.
- **`ingestion-tr.md` CLI synopsis adds Phase 12 flags** —
  `--strategy markdown` and `--secrets-mask` now appear in the
  options block; short Turkish description for each.
- **`review-pr` skill heading updated** — "The six-question review"
  → "The seven-question review" to match the regex-check question
  added in the previous commit.
- **`data_curation.ipynb` fixture credentials fragmented** —
  `deploy_runbook.txt` fixture now builds `AKIA…` / `ghp_…` strings
  at runtime from inert fragments (same convention as
  `tests/test_data_audit_phase12.py::FAKE_AWS_KEY`). Repo-wide
  secret scanners no longer flag the notebook source.
- **`data_curation.ipynb` MinHash install uses the project extra** —
  `pip install 'datasketch>=1.6.0,<2.0.0'` →
  `pip install 'forgelm[ingestion-scale]==0.5.2'` so the recipe
  matches the install hint baked into
  `forgelm.data_audit._require_datasketch`.
- **`TestMinHashDistinctSemantic` uses pytest's `tmp_path`** — Was
  creating a directory under `tests/` which mutated the repo and
  broke parallel pytest runs. Now uses the standard `tmp_path`
  fixture; no manual cleanup needed.
- **3 new fence-length regression tests** in
  `tests/test_phase12_review_fixes.py::TestFenceRunLengthRule`:
  4-backtick block not closed by 3 backticks; `_strip_code_fences`
  respects the length rule; close lines with info strings are
  treated as content (CommonMark §4.5 conformance).

### Added — Regex hygiene standard

- **New standard `docs/standards/regex.md`** — codifies 8 hard rules absorbed from Phase 11/11.5/12 review cycles (no `[A-Za-z0-9_]` shorthand, no single-char character classes, bound your quantifiers, no two competing quantifiers over the same class, no `\s` under MULTILINE, no `.*?` + back-reference + DOTALL, anchored `^` / `$`, no leading `^.*`). Each rule cites the concrete review finding that produced it. Includes a ReDoS-exposure budget (10K-char pathological-input benchmark must stay ≤ 10ms) and test fixture hygiene rules (build credential-shaped strings from inert fragments at runtime). Linked from `coding.md`, `code-review.md`, the `review-pr` skill, and `CLAUDE.md`'s "read before editing" entry point.
- **`code-review.md` checklist gains a regex section** — explicit `git diff` recipe to surface modified `re.compile` / `re.match` / `re.sub` calls + per-regex audit checklist.
- **`review-pr` skill gains a regex check** — same checklist, applied during self-review before opening a PR.

### Fixed — Phase 12 review cycle round 2.5 (post-`30ef590`)

Round-2.5 review surfaced two confirmed ReDoS shapes that the earlier rounds missed; the regex hygiene sweep above also caught a handful of style-only deviations across the codebase.

- **ReDoS confirmed in `_MARKDOWN_HEADING_PATTERN`** (`forgelm/ingestion.py`) — Old pattern `[ \t]+(.+?)[ \t]*$` had three quantifiers competing for trailing whitespace; pathological input `"# a" + " \t" * n + "x"` ran in O(n²) time (100ms at n=2000, 600ms at n=5000, 2.1s at n=10000 measured in CPython 3.11). Replaced with a non-whitespace anchor on the body capture: `[ \t]+(\S(?:[^\n]*\S)?)[ \t]*$`. Result: linear (10μs at n=10000 — 200000× speedup).
- **`_CODE_FENCE_BLOCK` regex replaced with state machine** (`forgelm/data_audit.py`) — Old form used `.*?` + back-reference + `re.DOTALL`, which SonarCloud `python:S5852` flags as a polynomial-runtime risk even though it benchmarks linearly in CPython. Replaced with a per-line state machine (`_strip_code_fences` + `_is_code_fence_open` + `_is_code_fence_close`) that is provably O(n) and matches the same line-walker pattern as `_markdown_sections`. Behaviour pinned bit-for-bit on 7 fixtures.
- **`[A-Za-z0-9_-]` → `[\w-]`** in `openai_api_key`, `google_api_key`, `jwt` (3 places) regexes per regex.md rule 1.
- **`\s*$` → `[ \t]*$`** in `_PUNCT_END_PATTERN` (callers pre-split into single lines, so the `\s` newline-overlap is dead weight) per regex.md rule 5.
- **Bounded `_HF_HUB_ID_RE`** (`forgelm/wizard.py`) — `[A-Za-z0-9._-]+` → `[\w.-]{1,96}` (HF Hub username + repo name max length) per regex.md rule 3 — defence-in-depth, no behaviour change for well-formed HF IDs.

### ReDoS regression tests

- **New `TestRegexLinearity` class in `tests/test_phase12_review_fixes.py`** — pinned 1-second wall-clock cap on N=10000 pathological inputs for both `_MARKDOWN_HEADING_PATTERN` and `_strip_code_fences`. A real ReDoS would blow far past the threshold; a slow CI host won't false-positive.
- **Empirical sweep over all 25 forgelm regexes** confirmed linear scaling under 50K-character adversarial input. Slowest pattern (`openssh_private_key`, full-block PEM) measures 0.5ms — ~10μs/KB. The sweep is reproducible via the snippet documented in regex.md.

### Fixed — Phase 12 review cycle round 2 (post-`bf8ca82`)

Second-round review of the Phase 12 commit surfaced 22 findings spanning correctness, regex coverage, code-smell hygiene, type widening, and documentation parity. All addressed.

- **Private-key blocks redacted in full** (`forgelm/data_audit.py`) — Old `openssh_private_key` / `pgp_private_key` regexes only matched the `BEGIN` header line, so `mask_secrets` left the entire base64 body + `END` line in clear text. Now both patterns match the full PEM/PGP envelope (BEGIN through matching END inclusive) under `re.DOTALL`. The literal block markers are split across `r"-----" + r"BEGIN " + r"..."` concatenations to keep repo-wide secret scanners (gitleaks / trufflehog) silent.
- **Fenced code blocks recognise tildes too** (`forgelm/data_audit.py` + `forgelm/ingestion.py`) — `_CODE_FENCE_BLOCK` (audit's quality-filter strip) and `_MARKDOWN_CODE_FENCE` (ingest's markdown splitter) only matched triple-backtick fences; CommonMark §4.5 also allows `~~~`. Both now recognise either fence character with up to 3 leading spaces. The markdown splitter additionally tracks the *opening* fence character so a stray `\`\`\`` inside a `~~~` block (or vice-versa) doesn't toggle state.
- **DOCX block order preserved** (`forgelm/ingestion.py`: `_iter_docx_blocks`) — `_extract_docx` previously appended every paragraph followed by every table, reordering content. New helper walks `doc.element.body` in source order, dispatches on `<w:p>` vs. `<w:tbl>`, and renders each block in place.
- **Markdown overlap rejected explicitly** — `_strategy_dispatch` and `_strategy_dispatch_tokens` raise `ValueError` when `--strategy markdown` is combined with a non-zero overlap, rather than silently dropping it. To keep the CLI's historical default `--overlap 200` from spuriously tripping the validator on a `--strategy markdown` invocation that didn't ask for overlap, `--overlap`'s argparse default is now `None`; `ingest_path` resolves that sentinel to `200` for the sliding strategy and `0` for paragraph / markdown.
- **`minhash_distinct` counts unique sketches** (`forgelm/data_audit.py`) — Previously returned the count of non-empty rows, breaking parity with `simhash_distinct` (which is *unique fingerprints*). Now hashes each MinHash via `m.hashvalues.tobytes()` and counts the distinct set, matching simhash semantics.
- **`_row_quality_flags` typed `Optional[str]`** — The function already accepted `None` at runtime; the signature now reflects that and the test's `# type: ignore[arg-type]` suppression is gone.
- **Cognitive-complexity refactors** — `_row_quality_flags` (CCN 22 → ≤ 10 via per-check helpers `_check_low_alpha_ratio` / `_check_low_punct_endings` / `_check_abnormal_mean_word_length` / `_check_short_paragraphs` / `_check_repeated_lines`); `find_near_duplicates_minhash` (CCN 21 → ≤ 10 via `_build_minhash_lsh` + `_emit_minhash_pair`); `audit_dataset` (CCN 21 → ≤ 12 via `_fold_outcome_into_summary` + `_build_quality_summary` + `_build_near_duplicate_summary`).
- **Regex / lint code-smells** — `[A-Za-z0-9_]` → `\w` in the GitHub PAT pattern; `[ ]{0,3}` → ` {0,3}` (single-char class collapsed) in markdown patterns; `\s` → `[ \t]` in heading pattern (mitigates the polynomial-backtracking concern SonarCloud flagged); duplicate `"chunk_tokens must be positive"` / `"max_chunk_size must be positive"` literal strings extracted to module constants `_CHUNK_TOKENS_POSITIVE_MSG` / `_CHUNK_SIZE_POSITIVE_MSG`; `_MARKDOWN_OVERLAP_UNSUPPORTED_MSG` constant for the new validator; comprehension `["| " + " | ".join(c for c in row) + " |"]` simplified to `["| " + " | ".join(row) + " |"]`.
- **Documentation parity** — `docs/guides/data_audit.md` quality-filter bullet list and JSON example now include `repeated_lines` and a note about code-fence stripping. `docs/guides/ingestion-tr.md` mirrors the EN guide's chunking-strategies table (markdown row added) and gains a new "secrets/credential masking (Faz 12)" section. `CHANGELOG`'s Phase 12 entry no longer overstates the `[ingestion-secrets]` extra: the regex set is the sole detection backend in v0.5.2, and the `detect-secrets` package is reserved for a follow-up release. `README` separates "From PyPI" and "From a local clone" install blocks so copy-paste users don't hit `-e .` confusion.
- **Test fixtures fragmented** — All hardcoded credential / JWT literals in `tests/test_data_audit_phase12.py`, `tests/test_ingestion_phase12.py`, and `tests/test_phase12_review_fixes.py` now built at runtime from inert string fragments (e.g. `"AKIA" + "IOSFODNN7" + "EXAMPLE"`). The regex still has to match the canonical shape, but no full literal credential lives in the source tree — silences gitleaks / trufflehog scans of the repo without changing behaviour.
- **5 new round-2 regression tests** (`tests/test_phase12_review_fixes.py`) — `TestTildeFenceRecognised` (~~~-fenced code blocks block heading splits), `TestPrivateKeyFullBlock` (full PEM body redaction), `TestMarkdownOverlapValidation` (rejection on explicit non-zero overlap; default-overlap pass-through), `TestMinHashDistinctSemantic` (unique-sketches semantic).
- **Notebook ruff format** — `notebooks/post_training_workflow.ipynb` reformatted to satisfy `ruff format --check` in CI; `notebooks/data_curation.ipynb` install line pinned to `forgelm[ingestion]==0.5.2` rather than the moving `main` branch.

### Fixed — Phase 12 review cycle (post-`2f5722a`)

Round-1 review of the Phase 12 commit surfaced four critical regressions / bugs and several lower-severity issues. All addressed before tagging `v0.5.2`. No new functionality; only correctness, honesty, and parity fixes.

- **JSON envelope back-compat** (`forgelm/cli.py`) — `_run_data_audit`'s stdout JSON envelope dropped the v0.5.1 `near_duplicate_pairs_per_split` top-level key when the richer `near_duplicate_summary` block was added. Pre-Phase-12 CI consumers (`jq '.near_duplicate_pairs_per_split.train'`) would have started getting `null`. Restored as an additive key alongside the new one. Plan / CHANGELOG language updated from *"byte-identical default report"* to *"schema-additive"* — older parsers keep working, but on-disk JSON is no longer byte-identical because `secrets_summary`, `near_duplicate_summary.method`, and `cross_split_overlap.method` are now always present.
- **Quality filter completes the planned check set** (`forgelm/data_audit.py`) — Plan promised five Gopher / C4 / RefinedWeb-style heuristics; v0.5.2 shipped four. Added the missing `repeated_lines` check (top-3 actually-repeating distinct lines covering > 30 % of non-empty lines flag the row — pinned on count ≥ 2 so short all-unique documents don't false-positive). Surfaces in `quality_summary.by_check.repeated_lines`.
- **Quality filter respects fenced markdown code** (`forgelm/data_audit.py`: `_strip_code_fences`) — Code blocks legitimately have low alpha ratio + missing end-of-line punctuation + short paragraphs and tripped every prose heuristic, polluting the `quality_summary` on legitimate code-instruct corpora. `_row_quality_flags` now strips fenced ``` … ``` blocks before applying the heuristics; pure-code rows return `[]` instead of being flagged on shape grounds.
- **DOCX table cells escape `|` and `\`** (`forgelm/ingestion.py`: `_escape_md_cell`) — `_docx_table_to_markdown` joined cell text directly into a markdown table row, so a cell containing `a|b` was parsed by downstream tokenisers as two extra columns. Now escapes `|` → `\|` and `\` → `\\` per CommonMark, and collapses embedded newlines to spaces (markdown tables can't carry multi-line cells).
- **JWT regex narrowed** (`forgelm/data_audit.py`) — Old pattern `\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b` false-positived on prose like `eyJfoo.eyJbar.baz`. Anchored on the canonical JWT header alphabet (`alg` / `typ` / `kid` / `cty` / `enc` / `api`'s base64url prefixes — `hbGc`, `0eXA`, `raWQ`, `jdHk`, `lbmM`, `hcGk`) plus minimum lengths on payload and signature. Real JWTs (including the original test fixture) still match; arbitrary `eyJ.eyJ.X`-shaped prose does not.
- **MinHash docstring honest about the metric** (`forgelm/data_audit.py`) — `compute_minhash` previously claimed it surfaces "the same class of near-duplicates" as simhash. The two use different similarity metrics (set-Jaccard over distinct tokens vs. frequency-weighted bit-cosine) and disagree on documents with high token-frequency variance. Docstring rewritten to make the divergence explicit. Roadmap "byte-identical" wording corrected in the same spirit.
- **CommonMark indented headings recognised** (`forgelm/ingestion.py`) — `_MARKDOWN_HEADING_PATTERN` and `_MARKDOWN_CODE_FENCE` allow up to 3 leading spaces per CommonMark §4.2; 4+ spaces still fall through as indented code blocks (correctly *not* split as headings).
- **Cog complexity restored to ≤ 15** — `_aggregator_to_info` (split into `_populate_schema_block` / `_populate_optional_findings` / `_within_split_pairs`) and `_markdown_sections` (split into `_push_heading_onto_path` / `_trim_blank_edges`) factored to stay under the Phase 11.5 ceiling.
- **Defensive lazy import in `compute_minhash`** — Empty input now returns `None` without paying the `_require_datasketch()` raise path. Same effect for `_count_leaked_rows_minhash` when the entire target list is empty (LSH-construction skipped).
- **Mask-order rationale honest** (`forgelm/ingestion.py`: `_emit_chunk`) — Old docstring claimed today's regex sets overlap; in practice the shipped fixtures show no overlap. Rewritten to describe the ordering as *defensive* (favour secrets when ordering matters at all; future-proof against new PII / secret regexes that may overlap, e.g. Azure connection strings vs. IBANs).
- **Markdown chunkers document the no-overlap contract** — `_chunk_markdown` and `_chunk_markdown_tokens` docstrings explicitly state that `--overlap` / `--overlap-tokens` are silently ignored when `--strategy markdown` is selected (sections are atomic; overlapping would slice mid-section and break the breadcrumb invariant).
- **Type hints tightened** — `IngestionResult.format_counts` / `pii_redaction_counts` / `secrets_redaction_counts` and the local counters in `ingest_path` typed as `Dict[str, int]` instead of bare `dict`.
- **Turkish documentation parity** (`docs/guides/data_audit-tr.md`) — Three Phase 12 H3 sections (MinHash LSH, Code/secret tagger, Heuristic quality filter) were missing from the TR mirror; added at the same detail level as the EN guide.
- **18 regression tests** (`tests/test_phase12_review_fixes.py`) — One class per finding, pinning the fixes against re-introduction. Covers the JSON envelope shape, `repeated_lines` detection on real boilerplate vs. all-unique short docs, DOCX `|` / `\` / newline escaping, JWT header-alphabet anchors with the prose-shape false-positive, code-fence stripping in the quality filter, the token-aware markdown chunker (previously untested), and CommonMark 0-3-space indented headings.

### Added — Phase 12 (Data Curation Maturity, targeting v0.5.2)

Direct continuation of the Phase 11 / 11.5 ingestion + audit lineage. Closes the four concrete gaps surfaced by the post-`v0.5.1` competitive review (LLaMA-Factory / Axolotl / Unsloth / NeMo Curator / Dolma / RedPajama / LlamaIndex / LangChain / Marker / Docling). Tier 1 (5 must-have tasks) shipped; Tier 2/3 (Presidio adapter, Croissant metadata, `--all-mask`, wizard "audit first") deferred to a [Phase 12.5 backlog](docs/roadmap/phase-12-5-backlog.md).

- **MinHash LSH dedup option** (`forgelm/data_audit.py`: `compute_minhash`, `find_near_duplicates_minhash`, `_count_leaked_rows_minhash`) — Opt-in `--dedup-method minhash --jaccard-threshold 0.85` route via the optional `[ingestion-scale]` extra (`datasketch>=1.6.0`). Default simhash + LSH banding from Phase 11.5 stays untouched and remains the only method that runs without an optional dependency. `audit_dataset(...)` API gains `dedup_method`, `minhash_jaccard`, `minhash_num_perm` parameters; `near_duplicate_summary.method` records which path ran. Cross-split overlap + within-split duplicate scan share the same method flag. MinHash is approximate (permutation noise; default `num_perm=128`) — pin `num_perm` for cross-run determinism.
- **Markdown-aware splitter** (`forgelm/ingestion.py`: `_chunk_markdown`, `_chunk_markdown_tokens`, `_markdown_sections`, `_heading_breadcrumb`) — New `--strategy markdown` parses heading hierarchy (`# H1` … `###### H6`), keeps code-fenced blocks atomic (heading-shaped lines inside ```` ``` ```` blocks are not interpreted as section boundaries), and inlines a heading **breadcrumb** at the top of each chunk so SFT loss sees the document context. Composes with the Phase 11.5 token-aware mode (`--chunk-tokens` + `--tokenizer`).
- **Code / secret leakage tagger** (`forgelm/data_audit.py`: `detect_secrets`, `mask_secrets`, `_SECRET_PATTERNS`) — Always-on audit-side scan with a **prefix-anchored regex set** (the sole detection backend in this release) covering AWS access keys (`AKIA…` / `ASIA…`), GitHub PATs (`ghp_`, `gho_`, `ghs_`, `ghu_`, `ghr_`, `github_pat_`), Slack tokens, OpenAI API keys (`sk-…` / `sk-proj-…`), Google API keys, JWTs anchored on canonical header alphabet, full OpenSSH / RSA / DSA / EC / PGP private-key blocks (BEGIN through END inclusive — `mask_secrets` redacts the entire block, not just the header line), and Azure storage connection strings. Adds a `secrets_summary` block alongside `pii_summary`. Ingest side: `forgelm ingest --secrets-mask` rewrites detected spans with `[REDACTED-SECRET]`; runs **before** PII masking as a defensive ordering so future overlapping detectors (PII vs secret regex) can't double-count. The optional `[ingestion-secrets]` extra (`detect-secrets>=1.5.0`) is reserved for a follow-up release — the current code does **not** invoke the `detect-secrets` package (its plugin model assumes file paths, not streaming chunks); install only as forward-compatibility for the eventual integration.
- **Heuristic quality filter** (`forgelm/data_audit.py`: `_row_quality_flags`, `_QUALITY_CHECKS`) — Opt-in `forgelm audit --quality-filter` runs Gopher / C4 / RefinedWeb-style checks per row: `low_alpha_ratio` (< 70 % letters among non-whitespace), `low_punct_endings` (< 50 % of non-empty lines end with punctuation), `abnormal_mean_word_length` (outside 3–12 chars), `short_paragraphs` (> 50 % of `\n\n`-blocks have < 5 words). Surfaces `quality_summary` with per-check counts, `samples_flagged`, and `overall_quality_score`. ML-based classifiers (fastText / DeBERTa) deliberately out of scope — keeps the audit deterministic for Annex IV reproducibility.
- **DOCX / Markdown table preservation** (`forgelm/ingestion.py`: `_docx_table_to_markdown`) — `_extract_docx` now renders tables as markdown table syntax (header row + `---` separator + body rows) instead of the previous `" | "`-joined flat line. Uneven rows are right-padded with empty cells; all-blank rows are dropped; the first non-empty row becomes the header (no heuristic — that's the convention DOCX authors use). Combined with `--strategy markdown` the table block stays intact across chunks.

### Public API additions

- `AuditReport` gains `secrets_summary: Dict[str, int]` and `quality_summary: Dict[str, Any]` fields (additive — Phase 11/11.5 consumers reading just `pii_summary` / `near_duplicate_summary` keep working).
- `IngestionResult` gains `secrets_redaction_counts: dict` field.
- `audit_dataset(...)` accepts `dedup_method`, `minhash_jaccard`, `minhash_num_perm`, `enable_quality_filter` keyword arguments.
- `ingest_path(...)` accepts `secrets_mask: bool` keyword argument.
- New constants: `DEDUP_METHODS`, `DEFAULT_MINHASH_JACCARD`, `DEFAULT_MINHASH_NUM_PERM`, `SECRET_TYPES`.

### CLI additions

- `forgelm ingest`: `--strategy markdown`, `--secrets-mask`.
- `forgelm audit`: `--dedup-method {simhash,minhash}`, `--jaccard-threshold X` (validated to `[0.0, 1.0]` at parse time), `--quality-filter`.
- New argparse type helper `_non_negative_float` (mirrors `_non_negative_int`'s pattern).
- `_run_data_audit` now distinguishes `EXIT_CONFIG_ERROR` (filesystem/path errors) from `EXIT_TRAINING_ERROR` (missing `[ingestion-scale]` extra when `--dedup-method=minhash` was requested).

### `pyproject.toml`

- New extras: `[ingestion-scale]` (`datasketch>=1.6.0,<2.0.0`), `[ingestion-secrets]` (`detect-secrets>=1.5.0,<2.0.0`).
- Version bump `0.5.1rc1 → 0.5.2rc1`.

### Tests

- `tests/test_data_audit_phase12.py` — 18 new tests across `TestSecretsDetection`, `TestSecretsMasking`, `TestAuditPicksUpSecrets`, `TestQualityFilterPerRow`, `TestQualityFilterEnabled`, `TestMinHashLshDedup` (skipped without `datasketch`), `TestMinHashMissingExtra`.
- `tests/test_ingestion_phase12.py` — 13 new tests across `TestMarkdownSections`, `TestChunkMarkdown`, `TestMarkdownStrategyExposed`, `TestDocxTableToMarkdown`, `TestSecretsMaskIngest`.
- `tests/test_cli_subcommands.py` — `test_audit_quality_filter_flag`, `test_audit_rejects_invalid_jaccard_threshold` added to `TestAuditSubcommand`.

### Changed (no behavioural delta unless noted)

- `_StreamingAggregator` gains `minhashes`, `secrets_counts`, `quality_flags_counts`, `quality_samples_flagged`, `dedup_method`, `minhash_num_perm`, `enable_quality_filter` fields. Field rename: `_SplitOutcome.fingerprints` → `_SplitOutcome.signatures` (the same field carries simhash ints OR MinHash instances, depending on method).
- `_audit_split(...)` now returns `(info, signatures, pii_split, parse_errors, decode_errors)` where `signatures` is method-dependent. `_process_split` and `audit_dataset` were updated in lockstep.
- `_pair_leak_payload` and `_cross_split_overlap` switched to keyword-only `dedup_method` parameter and dispatch on it (simhash → Hamming; minhash → Jaccard).
- `describe_strategies()` now lists `markdown` alongside `sliding` / `paragraph` / `semantic`.

### Added — Phase 11.5 (Ingestion / Audit Polish, targeting v0.5.1)

Operational polish on top of `v0.5.0`'s ingestion + audit surface — no new training capabilities, but materially better handling for large corpora and a cleaner CLI shape. All 12 follow-ups carved out of Phase 11's review backlog.

- **`forgelm audit PATH` subcommand** — Promotes the `--data-audit` top-level flag to a first-class subcommand with `--verbose`, `--near-dup-threshold`, and its own `--output` default (`./audit/`). The legacy `forgelm --data-audit PATH` flag keeps working as a deprecation alias and logs a one-line notice; existing CI pipelines need no changes. Removal targeted no earlier than `v0.7.0`.
- **LSH-banded near-duplicate detection** (`find_near_duplicates`, `_count_leaked_rows`) — Pigeonhole-banded LSH (default `bands = threshold + 1`) drops within-split + cross-split scans from `O(n²)` to ~`O(n × k)`. Recall stays exact at the default Hamming threshold; brute-force fallback remains for edge thresholds where bands shrink below 4 bits. Unblocks audits on 100K+ row corpora.
- **Streaming `_read_jsonl_split`** — The audit's JSONL reader is now a generator yielding `(row, parse_err, decode_err)`; `_audit_split` consumes it row-by-row via a `_StreamingAggregator` so RAM stays bounded on multi-million-row splits. Per-line tolerance semantics (parse errors, decode errors, non-dict rows) preserved.
- **Token-aware ingestion** (`--chunk-tokens`, `--tokenizer`, `--overlap-tokens`) — Optional flags on `forgelm ingest` size chunks against an HF `AutoTokenizer.encode` instead of raw character counts, so chunks line up with `model.max_length` exactly. `--tokenizer` is required with `--chunk-tokens` (we refuse to default to a hidden vocab because the chunk count would silently differ per-model). `trust_remote_code=False` is hard-pinned for safety.
- **PDF page-level header / footer dedup** (`_strip_repeating_page_lines`) — Lines that recur as the first or last non-empty line on ≥ 70 % of a PDF's pages (company watermarks, page numbers, copyright lines) are stripped automatically before chunking. Reduces audit `near_duplicate_pairs` noise on long policy / book PDFs. Skipped on documents shorter than 3 pages.
- **PII severity tiers** — Audit JSON now carries a `pii_severity` block (`total`, `by_tier`, `by_type`, `worst_tier`) alongside the flat `pii_summary`. Tiers map regulatory weighting: `credit_card` / `iban` → critical (PCI-DSS), national IDs → high (GDPR Art. 9), `email` → medium, `phone` → low. The aggregate notes line leads with the worst tier (`WORST tier: CRITICAL`) so reviewers cannot miss it.
- **`summarize_report` truncation policy** — Default `verbose=False` folds zero-finding splits into a single tail line so multi-split summaries stay short; `--verbose` on the new `audit` subcommand reverses this for full output. Has no effect on the on-disk JSON report.
- **Structured ingestion notes** — `IngestionResult.extra_notes` keeps the human-readable list; new `notes_structured: {key: value}` (and an explicit `pdf_header_footer_lines_stripped` field) carries machine-readable counts for CI/CD consumers. JSON output exposes both.
- **Wizard "ingest first" entry point** — `_offer_ingest_for_directory` + `_prompt_dataset_path_with_ingest_offer`: BYOD quickstart and the full 8-step wizard now offer to run `forgelm ingest` inline when the typed dataset path is a directory of raw documents, then feed the produced JSONL straight back into the BYOD path. Closes the onboarding loop end-to-end.
- **xxhash backend for simhash + token-level memo** — Optional `xxhash.xxh3_64` digest path (added to `forgelm[ingestion]`); BLAKE2b stays as the fallback. The Python-level speedup is modest (~1.3× raw, ~1.05× end-to-end after the cache below absorbs Zipfian repeats — xxhash's "4-10×" figure refers to C-level pure-hash microbenchmarks, not the Python wrapping path). The bigger wall-clock win is the new module-scope `lru_cache(maxsize=10_000)` that memoises the per-token digest — most corpora's token traffic is dominated by a few thousand frequent tokens, so the cache hit rate is very high.
- **Atomic audit-report write** — `data_audit_report.json` is now written via `tempfile.NamedTemporaryFile` + `os.replace` so a crashed audit can never leave a half-written report on disk. `newline="\n"` pinned for byte-exact reproducibility across Windows / Linux / macOS.

### Tests

- `tests/test_data_audit.py` — `TestLshBandedNearDuplicates` (LSH parity vs. brute force + high-threshold fallback), `TestPiiSeverity` (critical-tier verdict + neutral case), `TestSummarizeVerbosePolicy` (clean splits folded vs. expanded), `TestAtomicWrite` (no `.tmp` leftovers), `TestStreamingReader` (per-line tuple yields), `TestTokenCachePerformance` (cross-text cache hits).
- `tests/test_ingestion.py` — `TestPdfHeaderFooterDedup` (multi-page header/footer collapse, short-doc skip, no-repeats pass-through), `TestStructuredIngestionNotes`, `TestTokenAwareCli` (validates the `--chunk-tokens` requires `--tokenizer` rule).
- `tests/test_cli_subcommands.py` — `TestAuditSubcommand` (subcommand happy path, JSON envelope, legacy `--data-audit` alias).
- `tests/test_wizard_byod.py` — refreshed for the new ingest-first wording (empty directory rejection, decline-the-ingest-offer path).

### Changed — Phase 11 (no behavioural delta unless noted)

- `AuditReport` gains a `pii_severity: Dict[str, Any]` field. JSON consumers reading only `pii_summary` continue to work; the new field is additive.
- `find_near_duplicates(fingerprints, *, threshold, bits=64)` accepts a `bits` keyword for adaptive banding (default 64 matches `compute_simhash`).
- `_read_jsonl_split` is now a generator. The legacy buffered tuple return is gone — callers that were materialising rows can wrap with `list(...)`.
- `_audit_split(split_name, path, ...)` now takes a path instead of an in-memory list; `_process_split` calls it directly. Returns `(info, fingerprints, pii_split, parse_errors, decode_errors)` so OSError handling stays in the orchestrator.

### Previously added — Phase 11

**Document Ingestion & Data Audit (Phase 11)** — bridges raw enterprise corpora (legal, medical, policy manuals) to ForgeLM's training data format and surfaces governance signals before training starts.

- **`forgelm/ingestion.py`** + **`forgelm ingest`** subcommand:
  - Multi-format extractors: PDF (`pypdf`), DOCX (`python-docx`), EPUB (`ebooklib` + `beautifulsoup4`), TXT, Markdown.
  - Two chunking strategies: `paragraph` (default; greedy, never splits a paragraph) and `sliding` (fixed window with `--overlap`). `semantic` raises `NotImplementedError` and is reserved for a follow-up phase.
  - Output is `{"text": "..."}` JSONL — recognized as pre-formatted SFT input by `forgelm/data.py` without further preprocessing.
  - `--recursive` walks directory trees; unsupported extensions are skipped silently, supported files with no extractable text skip with a warning.
  - `--pii-mask` redacts detected PII spans before chunks land in the JSONL (shared regex set with the audit module).
  - OCR is intentionally out of scope; scanned PDFs without a text layer warn and produce zero chunks.

- **`forgelm/data_audit.py`** + **`forgelm --data-audit`** top-level flag:
  - Per-split metrics: sample count, column schema, text length distribution (`min/max/mean/p50/p95`), null/empty rate, top-3 language detection (best-effort via `langdetect`).
  - 64-bit simhash near-duplicate detection within each split; Hamming-distance threshold 3 ≈ 95% similarity (canonical web-page-dedup setting).
  - Cross-split overlap report — guards against silent train-test leakage that destroys benchmark fidelity.
  - PII regex set (`email`, `phone`, `credit_card` Luhn-validated, `iban`, `tr_id` checksum-validated, `de_id`, `fr_ssn`, `us_ssn`); per-split + aggregate counts.
  - Layout: single `.jsonl` file → treated as `train`; directory containing `train.jsonl` / `validation.jsonl` / `test.jsonl` (any subset) auto-discovered.
  - Writes `data_audit_report.json` under `--output` (default `./audit/`); `--output-format json` mirrors the report on stdout for CI/CD pipelines.
  - CPU-only; no GPU, no network.

- **EU AI Act Article 10 integration** — `generate_data_governance_report` now inlines `data_audit_report.json` under the `data_audit` key when present in the trainer's `output_dir`. Compliance bundle becomes a single self-contained document instead of a pointer.

- **`pyproject.toml` `[ingestion]` extra** — `pypdf`, `python-docx`, `ebooklib`, `beautifulsoup4`, `langdetect`. Cross-platform, no native compilation.

- **Tests** — `tests/test_ingestion.py` (TXT path + chunking strategies; PDF round-trip skips when `pypdf` missing) and `tests/test_data_audit.py` (PII regex + Luhn / TC Kimlik validators, simhash properties, end-to-end audit on file + split-keyed directory layouts, governance integration). All GPU/network-free.

- **Documentation** — new guides at `docs/guides/ingestion.md` and `docs/guides/data_audit.md`; README feature section, CLI epilog, install matrix, and roadmap status updated.

---

## [0.4.5] — 2026-04-26

### Added

**Quickstart Layer (Phase 10.5)** — One-command bundled templates with opinionated defaults. Primary community-growth driver: closes the gap between "I just installed ForgeLM" and "I have a fine-tuned model running locally."

- **`forgelm/quickstart.py`** — Template registry + orchestrator:
  - `Template` (frozen dataclass) — `name`, `title`, `description`, `primary_model`, `fallback_model`, `trainer_type`, `estimated_minutes`, `min_vram_for_primary_gb`, `bundled_dataset`, `license_note`.
  - `TEMPLATES: Dict[str, Template]` — 5 entries: `customer-support`, `code-assistant`, `domain-expert`, `medical-qa-tr`, `grpo-math`.
  - `auto_select_model(template, available_vram_gb)` — picks primary model when VRAM ≥ threshold (10–12 GB), fallback otherwise; explicit `no-gpu-detected` reason when CUDA is absent.
  - `_detect_available_vram_gb()` — wraps `torch.cuda.mem_get_info()`; returns `None` when no GPU (test mock point).
  - `run_quickstart(template_name, *, model_override, dataset_override, output_path, dry_run, available_vram_gb)` → `QuickstartResult` — copies seed dataset, substitutes `model.name_or_path` and `data.dataset_name_or_path`, writes `configs/<template>-YYYYMMDDHHMMSS.yaml`. Generated YAML is identical in shape to a hand-written one — same trainer, same schema.
  - `format_template_list()`, `summarize_result(result)` — text/JSON renderers for CLI use.

- **`forgelm quickstart <template>` CLI subcommand** (in `forgelm/cli.py`):
  - `--list` — prints the registry; honors top-level `--output-format json` for CI.
  - `--model <id>` — override auto-selected model.
  - `--dataset <path>` — override the bundled seed dataset (required for `domain-expert`).
  - `--output <path>` — custom YAML output path (default: `./configs/<template>-<timestamp>.yaml`).
  - `--dry-run` — generate config only; skip training and chat.
  - `--no-chat` — train but skip the post-training chat REPL.
  - On a successful run, subprocess-invokes `forgelm --config <out>` and then `forgelm chat <output_dir>` (unless `--no-chat`).

- **Wizard integration** — `forgelm --wizard` now opens with "Start from a template?":
  - Yes → routes to the quickstart selector; the wizard becomes a thin shell over `run_quickstart()`.
  - No → falls through to the existing 8-step interactive flow.
  - No bifurcation: identical code paths and YAML schema downstream.

- **5 bundled templates** under `forgelm/templates/`:
  - `customer-support/` — Qwen2.5-7B-Instruct primary, SmolLM2-1.7B-Instruct fallback. SFT trainer. 58-example seed JSONL in `{"messages": [...]}` format.
  - `code-assistant/` — Qwen2.5-Coder-7B-Instruct primary, Qwen2.5-Coder-1.5B-Instruct fallback (code-tuned smaller variant, not generic SmolLM2). SFT. 59-example Python/programming Q&A.
  - `domain-expert/` — Qwen2.5-7B-Instruct primary, SmolLM2-1.7B-Instruct fallback. BYOD; empty data with a README explaining how to pair with `forgelm ingest` (Phase 11) or a custom JSONL.
  - `medical-qa-tr/` — Qwen2.5-7B-Instruct primary, Qwen2.5-1.5B-Instruct fallback (Turkish-capable, not English-only SmolLM2). SFT, 49 Turkish Q&A; every answer ends with "Tıbbi acil durumlarda 112'yi arayın..." (medical-disclaimer guardrail).
  - `grpo-math/` — Qwen2.5-Math-7B-Instruct primary, Qwen2.5-Math-1.5B-Instruct fallback. GRPO trainer (`grpo_num_generations: 4`). 40 grade-school math word problems in prompt-only format, each carrying a `gold_answer` field for the built-in regex correctness reward.

- **Conservative defaults** in every template config:
  - QLoRA 4-bit NF4, LoRA rank=8, `per_device_train_batch_size=1`, gradient checkpointing on, safety eval / compliance artifacts opt-in only.
  - Designed so the smallest fallback model + the bundled seed dataset run end-to-end on a 12 GB consumer GPU.

- **`forgelm/templates/LICENSES.md`** — Full attribution for bundled seed datasets (CC-BY-SA 4.0, author-original); contributing guide for new templates; medical-disclaimer note for `medical-qa-tr`.

- **`pyproject.toml` `[tool.setuptools.package-data]`** — bundles `*.yaml`, `*.jsonl`, `*.md` under `forgelm.templates` into the wheel so `pip install forgelm` users get the templates without a source checkout.

- **GRPO baseline reward** — `forgelm/grpo_rewards.py` ships a default reward bundle so prompt-only datasets don't crash inside `trl.GRPOTrainer`. When `grpo_reward_model` is unset the trainer wires `combined_format_length_reward` (0.8 × format-match + 0.2 × length-shaping); if the dataset additionally carries a `gold_answer` field (the bundled `grpo-math` seed does), `_math_reward_fn` is appended so TRL sums correctness on top of format teaching.

- **Tests** — All GPU-independent via TRL/torch FSDP-aware skip-if pattern:
  - `tests/test_quickstart.py` — registry consistency, bundled-asset shape, `auto_select_model` primary/fallback/no-gpu, end-to-end `run_quickstart`, CLI dispatch, regression test that loads every generated YAML through `load_config` (strongest guard against template drift).
  - `tests/test_quickstart_hardening.py` — PR review hardening (path validation, model override edges, dry-run wiring).
  - `tests/test_grpo_math_reward.py` — pure-Python unit tests for `_normalize_answer`, `_answers_match`, `_math_reward_fn`, `_dataset_has_gold_answers`.
  - `tests/test_grpo_format_reward.py` — `format_match_reward`, `length_shaping_reward`, `combined_format_length_reward`, plus trainer integration.
  - `tests/test_wizard_byod.py` — wizard BYOD dataset path validation (existence, directory, malformed JSONL, valid JSONL, HF Hub IDs, `~` expansion).
  - `tests/test_cli_quickstart_wiring.py` — `--offline` propagation, separate chat inheritance, chat exit-code 0/130 handling.
  - `tests/test_packaging.py` — wheel `package_data` smoke (catches editable-install-only template paths).
  - `tests/test_grpo_reward.py` — extended with no-reward-model + gold-answer wiring assertions.

- **CI** — `.github/workflows/nightly.yml`:
  - Per-template quickstart smoke (4 of 5 — `domain-expert` is BYOD and covered by pytest).
  - New `wheel-install-smoke` job: builds the wheel, installs it into a fresh venv from `/tmp` (so the source tree is off `sys.path`), and reruns `quickstart --list` + `quickstart --dry-run` to catch broken `package_data` globs that editable installs hide.

### Documentation

- New "Option 0: One-Command Quickstart Template" section at the top of `docs/guides/quickstart.md`.
- `docs/roadmap.md`, `docs/roadmap-tr.md`, `docs/roadmap/phase-10-5-quickstart.md`, `docs/roadmap/releases.md` updated to mark Phase 10.5 as Done.
- `README.md` quickstart section updated to lead with `forgelm quickstart`.

---

## [0.4.0] — 2026-04-26

### Added

**Post-Training Completion (Phase 10)**

- **`forgelm/inference.py`** — Shared generation primitives for all post-training features:
  - `load_model(path, adapter, backend, load_in_4bit, load_in_8bit, trust_remote_code)` — loads HF model + tokenizer; optional PEFT adapter merge via `merge_and_unload()`; unsloth backend support
  - `generate(model, tokenizer, prompt, *, messages, system_prompt, history, max_new_tokens, temperature, top_k, top_p, repetition_penalty)` — non-streaming text generation
  - `generate_stream(...)` — streaming via `TextIteratorStreamer` in daemon thread; yields token chunks
  - `logit_stats(logits)` — returns `{entropy, top1_prob, effective_vocab}` for token-level confidence inspection
  - `adaptive_sample(logits, temperature, top_k, top_p, entropy_threshold)` — greedy below entropy threshold, nucleus sampling above
  - `_build_prompt` — uses `tokenizer.apply_chat_template` when available; falls back to `"role: content\n"` join

- **`forgelm/chat.py`** — Interactive terminal REPL (`ChatSession` class + `run_chat()` entry point):
  - Streaming output by default; `--no-stream` flag for non-streaming
  - Slash commands: `/reset`, `/save [file]`, `/temperature N`, `/system [prompt]`, `/help`, `/exit`
  - History management with 50-turn cap (`_MAX_HISTORY_PAIRS`)
  - Optional `rich` rendering via `pip install forgelm[chat]`
  - Optional `--safety` flag routes each response through Llama Guard

- **`forgelm/fit_check.py`** — VRAM pre-flight advisor:
  - `estimate_vram(config)` → `FitCheckResult(verdict, estimated_gb, available_gb, breakdown, recommendations)`
  - Verdicts: `FITS` (< 85% GPU), `TIGHT` (85-95%), `OOM` (> 95%), `UNKNOWN` (no GPU)
  - Architecture loaded via `transformers.AutoConfig`; fallback size-hint dict for 7b/8b/13b/70b families
  - VRAM components: base weights + LoRA adapter + optimizer state (AdamW/8-bit/GaLore-aware) + activations (gradient-checkpointing divides by √layers)
  - `format_fit_check(result)` — human-readable summary; `--output-format json` for CI/CD
  - Hypothetical mode when no CUDA detected — still estimates based on architecture

- **`forgelm/export.py`** — GGUF model export:
  - `export_model(model_path, output_path, *, format, quant, adapter, update_integrity, extra_args)` → `ExportResult`
  - Wraps `llama-cpp-python`'s `convert_hf_to_gguf.py` — no reimplementation of conversion logic
  - Supported quantizations: `q2_k`, `q3_k_m`, `q4_k_m`, `q5_k_m`, `q8_0`, `f16`
  - **K-quant note**: `q2_k`/`q3_k_m`/`q4_k_m`/`q5_k_m` require a two-step flow.
    `forgelm export ... --quant q4_k_m model.gguf` produces an intermediate
    `model.f16.gguf`; run `llama-quantize model.f16.gguf model.gguf Q4_K_M`
    afterward to obtain the K-quant. The `ExportResult.quant` field reflects
    what was actually written (so `model_integrity.json` SHA-256 stays honest)
  - Adapter merge: loads base + PEFT, saves merged fp16 weights before conversion
  - `_sha256_file` — chunked 64 KB reads for large models
  - `_update_integrity_manifest` — appends export artifact (path, quant, sha256, size_bytes) to `model_integrity.json`
  - Optional dependency: `pip install forgelm[export]` (`llama-cpp-python>=0.2.90`)

- **`forgelm/deploy.py`** — Deployment config file generation:
  - `generate_deploy_config(model_path, target, output_path, *, system_prompt, max_length, temperature, top_k, top_p, ...)` → `DeployResult`
  - Target `ollama`: Modelfile with FROM, SYSTEM (double-quote escaped), PARAMETER directives
  - Target `vllm`: YAML engine config with GPU memory utilization, dtype, trust_remote_code
  - Target `tgi`: docker-compose.yaml with GPU resource reservation, port mapping, max-input/total-length
  - Target `hf-endpoints`: JSON spec with model repository, task, compute instance, region, framework
  - Case-insensitive target matching; default output filenames per target

- **CLI subcommands** (`forgelm/cli.py`):
  - `forgelm chat MODEL_PATH [--adapter] [--system] [--temperature] [--max-new-tokens] [--safety] [--no-stream] [--load-in-4bit] [--load-in-8bit] [--trust-remote-code] [--backend]`
  - `forgelm export MODEL_PATH --output FILE [--format gguf] [--quant q4_k_m] [--adapter] [--no-integrity-update]`
  - `forgelm deploy MODEL_PATH --target TARGET [--output FILE] [--system] [--max-length] [--temperature] [--top-k] [--top-p] [--trust-remote-code]`
  - `forgelm --config CONFIG --fit-check [--output-format json]`
  - All subcommands work without `--config`; backward-compatible with existing flat CLI

- **Optional extras** in `pyproject.toml`:
  - `forgelm[export]` — `llama-cpp-python>=0.2.90` (non-Windows)
  - `forgelm[chat]` — `rich>=13.0.0`

- **New test modules**:
  - `tests/test_inference.py` — 16 tests covering `_build_prompt`, `_to_messages`, `logit_stats`, `adaptive_sample`, `load_model`, `generate` with custom torch stub (no GPU required)
  - `tests/test_fit_check.py` — 18 tests covering parameter estimation, VRAM components, GPU scenarios (no CUDA, 4 GB, 80 GB), `format_fit_check`
  - `tests/test_export.py` — 12 tests covering SHA-256, integrity manifest, GGUF export flow with subprocess mock
  - `tests/test_deploy.py` — 21 tests covering all 4 target generators and `generate_deploy_config` integration
  - `tests/test_cli_phase10.py` — 22 tests covering `--fit-check`, all deploy targets, export subcommand, chat subcommand, subcommand routing

### Changed

- **`forgelm/__init__.py`** — version bumped to `0.4.0`
- **`forgelm/cli.py`** — added subparser architecture with `chat`, `export`, `deploy` subcommands; added `--fit-check` flag; `KeyboardInterrupt` caught in chat dispatch for graceful exit
- **`forgelm/wizard.py`** — (no changes needed; Phase 10 features are all CLI-driven, not wizard-driven)

### Breaking

- **`forgelm.compliance.export_compliance_artifacts`** signature changed from
  `(manifest, config, output_dir)` to `(manifest, output_dir)`. The `config`
  argument was unused (the manifest already contains all derived values).
  External callers must drop the second positional argument.
- **`forgelm.export.export_model`** keyword `format=` renamed to
  `output_format=` to avoid shadowing the `format` builtin. Update
  `export_model(..., format="gguf", ...)` → `export_model(...,
  output_format="gguf", ...)`.
- **`forgelm.deploy.generate_deploy_config`** parameter list collapsed from
  18 → 11 args. The HF Endpoints fields (task/instance_size/instance_type/
  region/framework/vendor) are now grouped as
  `hf_endpoints: HFEndpointsOptions = None`; sampling defaults
  (temperature/top_k/top_p) are grouped as
  `sampling: SamplingOptions = None`. Pass instances of those dataclasses
  instead of the individual kwargs.

---

## [0.3.1rc1] — 2026-03-28 (included in v0.4.0 branch)

### Added
- **Engineering standards** (`docs/standards/`) — 9 standard documents: coding, architecture, error-handling, logging-observability, testing, documentation, localization, code-review, release.
- **AI agent skills** (`.claude/skills/`) — 6 task-specific SKILL.md checklists: add-config-field, add-trainer-feature, add-test, sync-bilingual-docs, cut-release, review-pr.
- **CLAUDE.md** — Root-level AI agent guidance file with non-negotiable project principles, skill table, and repo structure map.
- **Phase 10-13 planning docs** (`docs/roadmap/phase-*.md`) — Detailed planning for Post-Training Completion, Data Ingestion, Quickstart Layer, and Pro CLI.

### Changed
- **docs/ reorganization** — Reference docs moved to `docs/reference/`, design specs to `docs/design/`. All internal links updated (29 link fixes).
- **Roadmap refactored** — `docs/roadmap.md` reduced from 910 to 78 lines; phase details moved to `docs/roadmap/` subdirectory.

### Fixed (Security & Config Hardening)
- Webhook URLs excluded from HuggingFace Hub model cards — prevents credential leaks
- User-supplied strings sanitized before Markdown template embedding (content injection prevention)
- All 19 Pydantic sub-models enforce `extra="forbid"` — YAML typos are errors, not silent bugs
- Deprecated `lora.use_dora` / `lora.use_rslora` booleans auto-normalize to `lora.method` with warnings
- Audit log hash chain restores continuity across process restarts
- Compliance manifests correctly report pre-OOM-recovery batch size
- GRPO reward model path correctly wrapped as callable
- Safety classifier receives full `[INST] prompt [/INST] response` context
- Extension-less files raise clear `ValueError` instead of silently loading wrong format
- TIES tie-breaking fixed; DARE now deterministic with `seed=42`

## [0.3.0] — 2026-03-28

### Added

**GaLore Optimizer Integration**
- Full-parameter training via gradient low-rank projection — alternative to LoRA
- 6 optimizer variants: `galore_adamw`, `galore_adamw_8bit`, `galore_adafactor`, + layerwise versions
- Configurable rank, update_proj_gap, scale, proj_type, target_modules
- Validation: layerwise + multi-GPU incompatibility detection, LoRA co-existence warning

**Long-Context Optimizations**
- RoPE scaling support: linear, dynamic, YaRN, LongRoPE with configurable factor
- NEFTune noise injection (`neftune_noise_alpha`) for improved training quality
- Sliding window attention override for Mistral-family models
- Sample packing for efficient short-sequence training

**Synthetic Data Pipeline**
- Teacher→student distillation with `--generate-data` CLI command
- Three teacher backends: API (OpenAI-compatible), local (HuggingFace model), file (pre-generated)
- Configurable system prompt, temperature, max_new_tokens, rate limiting
- Four output formats: messages (chat), instruction, chatml, prompt_response
- Seed prompts from JSONL file or inline config

**GPU Cost Estimation**
- Auto-detection for 18 GPU models (T4, A100, H100, RTX 4090, etc.)
- Per-run cost calculation based on training duration and GPU type
- Manual override via `training.gpu_cost_per_hour`

**CI/CD & Publishing**
- PyPI publishing workflow (`.github/workflows/publish.yml`) — `pip install forgelm`
- Nightly compatibility testing (`.github/workflows/nightly.yml`)
- Expanded adversarial prompt library: 140 prompts across 6 categories (was 50/3)

**Wizard Enhancements**
- GaLore strategy option with rank and optimizer selection
- Long-context auto-detection (max_length > 4096) with RoPE scaling prompt
- NEFTune noise injection option

### Fixed
- SFTConfig `max_length` → `max_seq_length` for TRL compatibility
- `device_map={"":0}` for single GPU without 4-bit (prevents model splitting)
- Gradient checkpointing disabled on CPU (requires CUDA)
- Pre-formatted `text` column datasets now properly handled
- Chat template applied during inference in notebooks

### Changed
- Version bump: 0.2.0 → 0.3.0
- All notebooks use SmolLM2-135M for faster Colab testing (was 1.7B)
- Notebooks include base vs fine-tuned model comparison
- 297 tests (up from 242), 0 lint errors

---

## [0.2.0] — 2026-03-26

Major release: ForgeLM goes from a basic SFT fine-tuning tool to a full-stack LLM training platform with alignment, distributed training, safety evaluation, and EU AI Act compliance.

### Added

**Alignment & Post-Training Stack**
- 6 trainer types: SFT, DPO, SimPO, KTO, ORPO, GRPO
- Per-trainer hyperparameters (`dpo_beta`, `kto_beta`, `grpo_num_generations`, etc.)
- Dataset format auto-detection with trainer_type mismatch suggestions

**Distributed Training**
- DeepSpeed ZeRO-2, ZeRO-3, ZeRO-3+Offload presets
- FSDP support with sharding strategies (FULL_SHARD, SHARD_GRAD_OP)
- Unsloth + distributed conflict detection

**Safety & Evaluation**
- Safety classifier gate (Llama Guard) with binary and confidence-weighted scoring
- S1-S14 harm category breakdown with severity levels (critical/high/medium/low)
- Low-confidence alert system for uncertain classifications
- Cross-run safety trend tracking (`safety_trend.jsonl`)
- LLM-as-Judge scoring (API and local model support)
- Automated benchmark evaluation via lm-evaluation-harness
- Built-in adversarial prompt library (50 prompts across 8 categories)
- Human approval gate (`require_human_approval`, exit code 4)

**EU AI Act Compliance (Articles 9-17)**
- Annex IV technical documentation generator
- Structured audit event log (`audit_log.jsonl`) with hash chaining
- Risk assessment declaration (risk level, domain, mitigations)
- Data governance reporting (source, quality, bias mitigation)
- Model integrity verification (SHA-256 checksums for all artifacts)
- Deployer instructions generator (Article 13)
- Evidence bundle export (ZIP archive for auditors)
- QMS SOP templates (5 documents: training, validation, monitoring, change, incident)
- Post-market monitoring configuration scaffold

**Model Capabilities**
- MoE fine-tuning support (expert quantization, selective training)
- Multimodal VLM pipeline detection
- Model merging: TIES, DARE, SLERP, linear interpolation
- Advanced PEFT methods: PiSSA, rsLoRA, DoRA
- Automatic model card generation (HuggingFace format)

**CLI & UX**
- `--wizard` interactive config generator with GPU detection
- `--dry-run` config validation (JSON and text output)
- `--benchmark-only` evaluate existing models without training
- `--merge` standalone model merging
- `--compliance-export` generate audit artifacts
- `--quiet` suppress INFO logs
- `--offline` air-gapped mode (HF_HUB_OFFLINE)
- `--resume` checkpoint resume (auto-detect or explicit path)
- `--output-format json` machine-readable output
- `--log-level` configurable logging
- Exit codes: 0 (success), 1 (config error), 2 (training error), 3 (eval failure), 4 (awaiting approval)

**Infrastructure**
- Docker multi-stage build + docker-compose (training + TensorBoard)
- CI pipeline: 3 parallel jobs (lint, test matrix 3.10/3.11/3.12, validate)
- Ruff linting + formatting enforced
- 242 unit tests across 20 test files
- Branch protection rules on main
- GitHub issue templates (bug report, feature request) + PR template
- Apache License 2.0
- CONTRIBUTING.md + CODE_OF_CONDUCT.md

**Documentation**
- 6 user guides (quickstart, alignment, CI/CD, enterprise, safety, troubleshooting)
- 5 Colab-ready notebooks (SFT, DPO, KTO, GRPO, multi-dataset)
- Full EN/TR documentation (architecture, configuration, usage, roadmap)

### Changed

- Structured logging (`logging` module) replaces all `print()` calls
- Config validation via Pydantic v2 with `extra="forbid"` (typos caught)
- `trust_remote_code` now configurable via YAML (default: false)
- `bf16`/`fp16` auto-detected based on GPU capability
- `no_cuda` replaced with `use_cpu` (HF deprecation)
- `device_map` uses `{"": 0}` on single GPU without 4-bit (prevents model splitting)
- `gradient_checkpointing` auto-disabled on CPU
- `num_proc` for dataset processing scales with CPU count
- `enable_input_require_grads` always called for LoRA compatibility
- Dependency upper bounds pinned to prevent breaking changes
- `max_length` → `max_seq_length` for TRL SFTConfig compatibility
- `text` column datasets supported without reformatting

### Fixed

- 54 code review findings resolved (4 critical, 12 high, 19 medium, 14 low)
- Silent exception handling eliminated across all modules
- MoE expert quantization no longer corrupts weights (was using int8 cast)
- SLERP merge saves/restores base state correctly
- Webhook sanitizes metrics to numeric values only
- DARE merge handles `drop_rate >= 1.0` without division by zero
- Early stopping callback only added when validation data exists
- Audit log uses hash chaining for tamper evidence
- Model integrity hashes all files recursively (not just top-level)
- Checkpoint cleanup only removes `checkpoint-*` dirs (not entire output_dir)

## [0.1.0] — 2026-01-15

### Added

- Initial release
- SFT fine-tuning with TRL SFTTrainer
- LoRA/QLoRA (4-bit NF4) via PEFT
- Unsloth backend support
- DoRA adapter support
- YAML-based configuration
- Webhook notifications (Slack/Teams)
- Model versioning
- Basic evaluation checks (max loss, baseline comparison)
- Auto-revert on quality degradation

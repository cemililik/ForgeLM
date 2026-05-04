# Wave 2a Round-2 — Multi-Agent Review Prompt (PR #28)

> **Use this prompt verbatim** to launch the multi-agent code review on the
> consolidated Wave 2a PR. The prompt is self-contained: each reviewer agent
> can pick it up cold without context from prior conversations.
> Round-1 review (the per-PR pass on #23-#27) is now history; this is the
> round that gates merge to `development`.

---

## Repo & PR under review

- **Repo:** `cemililik/ForgeLM`
- **Branch under review:** `closure/wave2a-integration`
- **PR:** [#28](https://github.com/cemililik/ForgeLM/pull/28) → base
  `development`
- **Diff scope:** 26 files, ~4 600 insertions, ~120 deletions. Three new
  modules (`_doctor.py`, `_approvals.py`, `_audit_log_reader.py`), one new
  argparse helper (`_argparse_types.py`), three new test files (~1 729 LOC
  of tests).
- **What it consolidates:** the previously-scattered Phase 17 / 18 / 20 / 34
  / 37 PRs (#23, #24, #25, #26, #27 — all closed as superseded) **plus the
  Wave-2a Round-1 review fixes** that landed on top of each.

## What ForgeLM is (60 seconds)

A **config-driven, enterprise-grade LLM fine-tuning toolkit** — YAML in,
fine-tuned model + compliance artifacts out. Built for CI/CD pipelines, not
notebooks. Six alignment paradigms (SFT/DPO/SimPO/KTO/ORPO/GRPO),
integrated safety evaluation (Llama Guard), EU AI Act compliance artefacts
(Articles 9-17 + Annex IV), append-only audit log, opt-in human approval
gate, auto-revert on quality regression. Read [docs/product_strategy.md](../../product_strategy.md)
for fuller background.

Project rulebook lives under [docs/standards/](../../standards/) — read
[coding.md](../../standards/coding.md), [error-handling.md](../../standards/error-handling.md),
[testing.md](../../standards/testing.md), [logging-observability.md](../../standards/logging-observability.md),
and [code-review.md](../../standards/code-review.md) before commenting.
Project-wide guidance for AI agents is in the root `CLAUDE.md`.

## What this PR ships

| Phase | Type | Headline change |
|---|---|---|
| 18 | **Design only** | `library-api-design-202605021414.md` — public Python surface contract (stable / experimental / internal tiers, lazy-import invariant, `py.typed` + `mypy --strict`) |
| 20 | **Design only** | `gdpr-erasure-design-202605021414.md` — Article 17 erasure design + 11-test plan + `RetentionConfig` schema + 6 new audit events |
| 17 | **Implementation** | `forgelm audit --workers N` — split-level multiprocessing.Pool with byte-identical determinism contract (SHA-256 file-hash equality across worker counts) |
| 37 | **Implementation** | `forgelm approvals --pending / --show RUN_ID` — list / inspect human-approval gates from the audit log; path-traversal guarded; latest-wins re-staging |
| 34 | **Implementation** | `forgelm doctor [--offline]` — env probes (Python / torch / CUDA / GPU / extras / HF Hub / disk / operator identity); honest pass / warn / fail; lazy heavy-dep imports |
| Infra | **Refactor** | `forgelm/cli/subcommands/_audit_log_reader.py` — single source of truth for the audit-log JSONL parser, used by `_approve.py`, `_approvals.py`, and (Phase 21) `forgelm purge` |

Round-1 fix commits ride on top of the original feat/docs commits — see
PR description for the per-phase summary of what Round-1 already addressed.

## What we want from Round-2

**Goal:** decide whether `closure/wave2a-integration` is mergeable to
`development`. Block on real defects; do not gate on style nits or
hypothetical futures.

Be concrete. Every finding must include:

1. **Severity tag** — `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` / `NIT`
2. **Finding ID** — `F-<phase>-<NN>` (e.g. `F-17-03`, `F-37-04`,
   `F-INFRA-01`); use `F-XPR-NN` for cross-phase observations.
3. **File:line citation** — `forgelm/cli/subcommands/_doctor.py:342` or a
   short range `:340-360`. Cite the file even for design-doc findings
   (`docs/analysis/code_reviews/library-api-design-202605021414.md:§4.2`).
4. **One-paragraph reasoning** — what is wrong, what is the user-visible
   consequence, and why it qualifies for that severity tier.
5. **Suggested fix** — a code or text snippet, not a vague direction.
6. **Test that would have caught it** — name the test file + a stub of
   the assertion. If the bug is in a design doc, name the doc section that
   should have called it out.

Severity bar:

- `CRITICAL` — would corrupt data, silently lose audit events, leak PII,
  break exit-code contract, or break the `--offline` / air-gap promise.
  Blocks merge.
- `HIGH` — runtime crash on a documented happy path, missing test for a
  documented contract, schema mismatch with `pyproject.toml` or
  `config.py`, or a documentation claim with no code backing. Blocks
  merge.
- `MEDIUM` — logic bug in an off-the-happy-path branch, observability gap,
  or design-doc statement that contradicts shipped code. Should be fixed
  before merge but the call is the maintainer's.
- `LOW` — defensive-coding improvement, minor inconsistency, missing
  edge-case test that would not have changed PR direction.
- `NIT` — naming, line wrap, comment phrasing. Note in passing only; do
  not stack these.

## Areas to scrutinise

Hit these specifically — they are where Round-1 found the most issues and
where regressions are most likely:

### Phase 17 — `forgelm audit --workers N`

- Determinism contract: do `tests/test_data_audit_workers.py`'s SHA-256
  byte-identity assertions actually exercise the merge path that produces
  `data_audit_report.json`, or do they short-circuit on the same input?
- Spawn-context pinning: confirm `multiprocessing.get_context("spawn")` is
  used unconditionally in `_orchestrator.py` and is not overridable by
  caller env / config (we *want* it pinned).
- Error propagation: the `try/except` around `pool.map` — does it
  preserve the original `Traceback` so the user can debug, or does it
  collapse to a generic message?
- Argparse `_positive_int`: rejects `0`, `-1`, `1.5`, `"abc"`, `True`?
- Library-side `audit_dataset(workers=...)`: what happens for `workers=0`,
  `workers=-1`, `workers=True`, `workers="2"` from a Python caller? The
  test class claims typed `ValueError` — verify.
- `generated_at` stripping in tests: does the regex / replacement cope
  with the actual JSON shape, or could a tweak to the report format
  silently invalidate the determinism test?

### Phase 37 — `forgelm approvals`

- Path-traversal guard: trace a `staging_path` of `/etc/passwd` through
  the code path. Does `_staging_path_inside_output_dir` actually short-
  circuit before `os.listdir`, or only after some metadata has leaked?
- Latest-wins semantics: walk through a worked example with two
  `human_approval.required` events and one `human_approval.granted` event
  in between. Does the result agree with the docstring?
- Output-dir resolution: what happens when `--output-dir` is omitted? Is
  the default the same as `forgelm approve`'s default? Mismatch would
  surprise operators.
- Shared-module delegation: confirm `_approve.py` and `_approvals.py`
  both call `iter_audit_events` / `find_latest_event_for_run` and do not
  carry their own JSONL-parsing copies.
- JSON envelope: `{"success": true, "pending": [...], "count": N}` —
  schema-stable across `--show` and `--pending`? Same key for the
  collection? Same exit-code mapping?

### Phase 34 — `forgelm doctor`

- Extras names match `pyproject.toml` exactly: `distributed`, `eval`,
  `tracking`, `merging`, `export`, `ingestion`, `ingestion-scale`. Any
  drift = doc lie.
- HF cache resolution order: `HF_HUB_CACHE` > `HF_HOME/hub` > default —
  test exercises the precedence, not just one path.
- HF endpoint: `HF_ENDPOINT` is honoured for the HEAD probe (so
  self-hosted mirrors work). Air-gap users especially care.
- Lazy imports: `import forgelm` does not pull `torch` / `huggingface_hub`
  at top level. Run `python -c "import sys; import forgelm; print('torch'
  in sys.modules)"` mentally; report if it would print `True`.
- Probe-crash isolation: a single crashing probe must not abort the rest
  of the report. Walk through what happens if `_check_torch` raises
  `OSError`.
- Exit-code mapping: 0 = all pass (warns OK), 1 = at least one fail, 2 =
  probe itself crashed. Verify against
  [docs/standards/error-handling.md](../../standards/error-handling.md).
- Secret-env masking: `_DOCTOR_SECRET_ENV_NAMES` covers `HF_TOKEN`,
  `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `WANDB_API_KEY`, etc.? The audit
  log must never ingest a real token.
- `FORGELM_ALLOW_ANONYMOUS_OPERATOR`: what gets recorded when this is set
  vs unset? Does it match the
  [docs/standards/logging-observability.md](../../standards/logging-observability.md)
  contract?
- Cap-walked HF cache: depth 4, 5K files. What happens at exactly 5K?
  At 5K + 1?

### Phase 18 — Library API design (doc only)

- Tier completeness audit table — every public symbol in `forgelm/__init__.py`
  is in the table, and the symbol still exists in current code.
- Lazy-import section §4.2 — pseudo-code uses `globals()[name] = value`
  caching. Does Python actually re-trigger `__getattr__` if the value is
  not cached? Verify the documented contract is correct.
- §6.1 integration test surface — claims that match the actual planned
  `tests/test_library_api.py` surface. No "tests for X" without naming
  the test.
- §5.2 CI trigger — `release-*` branch. Is that what the
  [docs/standards/release.md](../../standards/release.md) says?
- §2.1 real signatures of `audit_dataset` / `verify_audit_log` — match the
  shipped `forgelm/__init__.py` re-exports.

### Phase 20 — GDPR erasure design (doc only)

- §3.1 prior-state acknowledgement — does it actually resolve the
  `staging_ttl_days` collision? Search `forgelm/config.py` for the term
  and confirm.
- §3.3 mtime caveat — wording matches what file-system semantics can
  actually guarantee.
- §4.2 row-id refusal — line-number / directory / multi-row cases all
  return error, not silent success.
- §4.3 exit codes — aligned to the public 0/1/2/3/4 contract in
  [docs/standards/error-handling.md](../../standards/error-handling.md).
- §4.4 strict commit ordering: `request → rewrite → completed` —
  describes a recoverable failure mode for each step.
- §5.1 six new audit events: `data.erasure_requested`,
  `data.erasure_completed`, `data.erasure_failed`,
  `data.erasure_warning_memorisation`,
  `data.erasure_warning_synthetic_data`,
  `data.erasure_warning_external_copies`. Schemas non-overlapping with
  existing event types in `forgelm/audit_log.py` (or wherever that module
  lives).
- §6 scope-limitation — clearly states what `forgelm purge` does **not**
  do (does not erase from external copies — operator must do that
  themselves).
- Marketing copy replacement for `safety_compliance.md` — flag any line
  that goes beyond what the design says we will actually implement.

### Infrastructure — `_audit_log_reader.py`

- `iter_audit_events`: malformed line policy — skip + log warning, or
  raise? Both `_approve.py` and `_approvals.py` agree?
- `find_latest_event_for_run`: time complexity on a 10 000-event log.
- HMAC verification — is the parser the right place for it, or should
  callers verify separately? (Round-1 carved out an `hmac_secret` param
  on `verify_audit_log`; this module deliberately stays parsing-only —
  confirm.)

### Cross-phase (XPR) checks

- **XPR-01** Audit-log parser proliferation: any leftover ad-hoc JSONL
  iteration in `forgelm/cli/subcommands/_*.py` or `forgelm/audit_log*.py`
  that should delegate to the shared module?
- **XPR-02** HTTP discipline: every outbound call has a timeout, returns
  on `--offline`, masks secrets in error messages.
- **XPR-03** JSON envelope schema: `--output-format json` shapes are
  consistent across `forgelm doctor`, `forgelm approvals`, `forgelm
  audit`. Document the contract in one place if not yet documented.
- **XPR-04** Test rigor: no test that asserts only on its own fixture
  shape (vacuous test); no `assert True` / `assert result` without
  comparing to a known-good value.
- **XPR-05** Documentation drift: every CLI flag mentioned in EN docs is
  also in TR docs and vice versa; every flag in docs exists in
  `forgelm/cli/_parser.py`; every flag in `_parser.py` is documented
  somewhere.
- **XPR-06** Schema collisions: any `Pydantic` field added by Phase 20
  design that collides with an existing field name in `forgelm/config.py`
  on a different type? (Round-1 caught `staging_ttl_days`; recheck after
  consolidation.)
- **XPR-07** Backwards compatibility: any change in this PR that would
  break a 0.5.0 user's workflow? CLI flag rename, default change, exit-
  code shift, audit event-type rename?

## Ground rules

- **Read the relevant standard before commenting.** The project
  [docs/standards/](../../standards/) directory is the rulebook.
- **Cite line numbers.** If you cannot point at a line, the finding is
  not actionable.
- **Distinguish design docs from shipped code.** A bug in a design doc is
  a wrong roadmap; a bug in shipped code is a defect. Different fixes,
  different urgency.
- **No phantom severity inflation.** A doc typo is `NIT`. A user-visible
  CLI bug on the happy path is `HIGH` minimum.
- **Round-1 fixes are baseline.** If you find an issue Round-1 already
  addressed, mark it `[Round-1 verified]` and move on; do not double-bill.
- **No re-litigating closed scope.** "Should ForgeLM also do X" is not a
  finding. Stay in the diff.
- **No suggestions to add a Web UI / GUI / inference engine / pretraining
  pipeline.** See [docs/marketing/strategy/05-yapmayacaklarimiz.md] —
  these are out of scope by design (read root `CLAUDE.md` "What ForgeLM is
  not").

## Required deliverable structure

Each reviewing agent returns a single Markdown report with this skeleton:

```markdown
# Wave 2a Round-2 — <agent-name> Review of PR #28

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

## Round-1 carry-overs verified
- F-23-04 [Round-1 verified] — lazy-import caching now uses `globals()[...]`
- F-26-02 [Round-1 verified] — spawn context pinned in `_orchestrator.py:42`
- (etc.)

## What this report deliberately did not cover
(Out-of-scope items the agent looked at and declined to flag, with one
sentence each. This keeps later reviewers from re-treading the same
ground.)
```

## How to launch

Spawn at minimum these agents in parallel:

1. **Code-correctness agent** — focuses on Phase 17 / 34 / 37
   implementation defects.
2. **Design-doc agent** — focuses on Phase 18 / 20 doc consistency
   against shipped code.
3. **Standards-compliance agent** — focuses on cross-phase checks XPR-01
   through XPR-07 against [docs/standards/](../../standards/).
4. **Test-rigor agent** — focuses on whether the tests in
   `test_data_audit_workers.py`, `test_doctor.py`,
   `test_approvals_listing.py` actually verify what they claim to.

Each agent gets this prompt verbatim plus a one-line `Focus:` directive
naming its specialty. Agents must not coordinate; the maintainer
deduplicates after.

## Delivery

- Agents return their reports in `docs/analysis/code_reviews/wave2a-round2-<agent>.md`.
- The maintainer (Cemil) merges findings, dedups, and posts the unified
  list on PR #28 as a top-level comment.
- Block / Conditional / Approve gating decision rests with the maintainer
  after consolidation, **not** with any individual agent.

---

*Prompt frozen 2026-05-02 against `closure/wave2a-integration` HEAD `5a57286`.*

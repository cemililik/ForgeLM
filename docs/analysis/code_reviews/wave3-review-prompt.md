# Wave 3 — Multi-Agent Code Review Prompt (PR pending)

> **Use this prompt verbatim** to launch the multi-agent review on the
> consolidated Wave 3 PR.  The prompt is self-contained: each reviewing
> agent can pick it up cold without context from prior conversations.
>
> Wave 3 is a single integration branch consolidating three closure-plan
> phases (Faz 24 + 28 + 38).  No prior absorption rounds yet — this is
> the FIRST review pass.  Treat the bar accordingly: catch the issues
> now, before any operator-visible regressions land.

---

## Repo & branch under review

- **Repo:** `cemililik/ForgeLM`
- **Branch under review:** `closure/wave3-integration`
- **HEAD SHA at prompt freeze:** `61d74fa`
- **Diff scope vs `development`:** ~32 files, ~685 insertions, ~84 deletions.
  Two new modules (`forgelm/cli/subcommands/_reverse_pii.py`,
  `tools/check_bilingual_parity.py`), two new test modules
  (`tests/test_reverse_pii.py`, `tests/test_check_bilingual_parity.py`),
  one rename (`test_integration_smoke.py` → `test_integration.py`).
- **What it consolidates:** Faz 24 (bilingual TR mirror sweep + parity
  CI guard), Faz 28 (curated tier 1+2 cleanup, ~10 items), Faz 38
  (`forgelm reverse-pii` GDPR Article 15 right-of-access subcommand).

## What ForgeLM is (60 seconds)

A **config-driven, enterprise-grade LLM fine-tuning toolkit** — YAML
in, fine-tuned model + compliance artifacts out.  Built for CI/CD
pipelines, not notebooks.  Six alignment paradigms
(SFT/DPO/SimPO/KTO/ORPO/GRPO), integrated safety evaluation
(Llama Guard), EU AI Act compliance artefacts (Articles 9–17 + Annex
IV), append-only audit log, opt-in human approval gate, auto-revert
on quality regression, GDPR Article 15 + 17 subject rights tooling
(this wave adds Article 15).  Read [docs/product_strategy.md](../../product_strategy.md)
for the fuller background.

Project rulebook lives under [docs/standards/](../../standards/) — read
[coding.md](../../standards/coding.md),
[error-handling.md](../../standards/error-handling.md),
[testing.md](../../standards/testing.md),
[logging-observability.md](../../standards/logging-observability.md),
[regex.md](../../standards/regex.md),
[localization.md](../../standards/localization.md), and
[code-review.md](../../standards/code-review.md) before commenting.
Project-wide guidance for AI agents is in the root `CLAUDE.md`.

## What this PR ships

| Phase | Type | Headline change |
|---|---|---|
| 38 | New CLI subcommand | `forgelm reverse-pii --query VALUE [--type X] [--salt-source X] JSONL_GLOB...` — GDPR Article 15 right-of-access companion to `forgelm purge`.  Two scan modes (plaintext residual + hash-mask via the same per-output-dir salt as purge).  New audit event `data.access_request_query` with the identifier *hashed* (Article 15 access requests must not leak the subject's data into the audit log). 18 regression tests. |
| 24 | New CI guard tool | `tools/check_bilingual_parity.py` replaces the inline H2-only check at `ci.yml:197-222` with an extended H2 + H3 + H4 structural diff.  AST-free, runs in lint job, `--strict` mode for CI gate.  16 regression tests. 8 doc pairs registered.  4 doc-pair drift fixes + 4 user-manual H2 drift fixes + alignment.md phase-reference de-anchor. |
| 28 | Curated cleanup | 10 items absorbed.  **Behaviour change (F-compliance-110):** high-risk + safety.enabled=false now raises `ConfigError`.  **Defaults change (F-compliance-106):** webhook timeout 5s → 10s.  **Log level (F-compliance-111):** missing data_audit_report.json `INFO → WARNING`.  Plus M-204 `_sanitize_md_list` helper, M-205 ollama newline guard, C-54 webhook re-export drop, C-57 GRPO reward docstring honesty, F-test-011 rename. |

## What we want from this round

**Goal:** decide whether `closure/wave3-integration` is mergeable to
`development`.  Block on real defects; do not gate on style nits or
hypothetical futures.

Be concrete.  Every finding must include:

1. **Severity tag** — `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` / `NIT`.
2. **Finding ID** — `F-W3-NN` (e.g. `F-W3-01`, `F-W3-12`).
3. **File:line citation** — `forgelm/cli/subcommands/_reverse_pii.py:142`
   or a short range `:138-150`.
4. **One-paragraph reasoning** — what is wrong, what is the user-visible
   consequence, and why it qualifies for that severity tier.
5. **Suggested fix** — a code or text snippet, not a vague direction.
6. **Test that would have caught it** — name the test file + a stub
   of the assertion.

Severity bar:

- `CRITICAL` — would corrupt data, silently lose audit events, leak
  PII / secrets, break the public exit-code contract (`0/1/2/3/4`),
  break the `--offline` / air-gap promise, or invalidate the
  audit-log hash chain.  Blocks merge.
- `HIGH` — runtime crash on a documented happy path, missing test
  for a documented contract, schema mismatch with `pyproject.toml`
  / `config.py`, documentation claim with no code backing, or a
  behaviour change that breaks 0.5.x users without a clear migration
  path.  Blocks merge.
- `MEDIUM` — logic bug in an off-the-happy-path branch, observability
  gap, or design-doc statement that contradicts shipped code.
  Should be fixed before merge but the call is the maintainer's.
- `LOW` — defensive-coding improvement, minor inconsistency, missing
  edge-case test that would not have changed PR direction.
- `NIT` — naming, line wrap, comment phrasing.  Note in passing
  only; do not stack these.

## Areas to scrutinise

These are the surfaces most likely to harbour real issues.  Hit them
specifically.

### Phase 38 — `forgelm reverse-pii` (largest new code surface)

- **Audit-event identifier hashing.**  The contract is "Article 15
  access requests must not leak the subject's data into the audit
  log."  Walk every audit-event field — does the raw `--query` value
  ever appear in the event payload (`query_hash` only, no `query`,
  no `match_snippets`, etc.)?  Are mid-scan failure events also
  hashed?  See `_run_reverse_pii_cmd` + `_hash_for_audit`.
- **Hash-mask scan correctness.**  `_resolve_query_form` reuses
  `forgelm purge`'s `_resolve_salt` + `_hash_target_id`.  Trace a
  full purge → reverse-pii cycle: same identifier, same output_dir,
  default salt source — does the reverse-pii digest match the
  digest purge writes into hash-masked corpora?  If `--salt-source
  env_var` is requested but `FORGELM_AUDIT_SECRET` is unset, what
  happens?  (Should refuse with `EXIT_CONFIG_ERROR`, see test
  `TestHashMaskScan::test_env_var_salt_source_requires_secret_env`.)
- **Glob expansion edge cases.**  `_resolve_files` uses
  `glob.glob(recursive=True)`.  Walk:
  - Operator passes `data/*.jsonl` but the dir is empty → exit 1
    (config error).  Confirm.
  - Operator passes a literal path that doesn't exist → exit 1.
  - Operator passes a directory (not a file) → directories are
    silently skipped (the resolver filters via `os.path.isfile`).
    Is that the right policy or should it fail loudly?
  - Two glob patterns with overlap → does dedupe via `seen` work
    correctly (absolute path comparison)?
- **Snippet truncation.**  `_truncate_snippet` centre-truncates at
  `_SNIPPET_MAX_CHARS = 160`.  Is 160 enough?  Walk a real-world
  corpus row (~500 chars typical) — does the operator see enough
  context to verify the hit?  Could the truncation ellipsis (`…`)
  itself be an issue (UTF-8 byte count vs char count)?
- **Custom regex injection.**  `--type custom` interprets the
  `--query` as a Python regex.  An adversarial query could trigger
  a ReDoS (catastrophic backtracking).  Per
  [docs/standards/regex.md], compiled patterns should be reviewed
  for backtracking exposure.  The dispatcher does not enforce a
  timeout on `pattern.search(line)` — is that acceptable?
- **Audit dir resolution.**  When the operator does NOT pass
  `--audit-dir`, the dispatcher uses `--output-dir`, which itself
  defaults to the parent of the first resolved corpus file.  Walk:
  if the operator scans `/etc/passwd*.jsonl` (an absurd test case),
  the audit log lands at `/etc/audit_log.jsonl` — that's a permission
  failure or worse.  Is the default safe?  Should it require
  explicit `--output-dir`?
- **Facade re-exports.**  `forgelm.cli.__init__.py` re-exports 10
  names from `_reverse_pii`.  Is the underscore-prefix surface
  consistent with other subcommands?  Does any of the re-exports
  pull heavy deps at import time (lazy-import discipline per Phase
  19)?  See `tests/test_library_api.py::TestLazyImportDiscipline`
  for the pattern.

### Phase 24 — `tools/check_bilingual_parity.py` (new CI gate)

- **Heading recognition correctness.**  `extract_headings` skips
  fenced code blocks via a simple boolean toggle.  Walk:
  - Triple-tilde fences (`~~~`) — handled?
  - Nested fences (a `~~~` block containing ` ``` ` content) —
    does the toggle stay correct?
  - A code block opened but never closed — does the rest of the
    file get treated as code (false negatives) or does the parser
    recover?
  - Setext headings (`===` / `---` underlines) — explicitly NOT
    matched.  Confirm.
- **Pair registry maintenance.**  `_PAIRS` is an explicit tuple.
  When a new bilingual doc is added, the registry must be updated.
  Is there a CI check that catches a new `*-tr.md` file added without
  a registry entry?  (If not, the strict mode would silently miss
  drift on the new pair.)
- **Strict-mode exit code.**  Returns 0 on clean, 1 on drift.  Per
  [docs/standards/error-handling.md], CI gate tools may use exit 1
  for "violations found" — but the script lives in `tools/`, not
  the `forgelm` CLI, so the public 0/1/2/3/4 contract does not
  apply.  Confirm the script's exit-code contract is documented
  *somewhere* (e.g., the SKILL.md or release.md).
- **Live-repo smoke test.**  `tests/test_check_bilingual_parity.py::
  TestCanonicalRepoPasses::test_repository_pairs_pass_strict` runs
  the tool against the live filesystem.  Is that fragile (a future
  PR that drifts a mirror would fail this test in addition to the
  CI gate, as a redundancy)?  Or does the redundancy cause double-
  reporting that confuses operators?

### Phase 28 — Behaviour change (F-compliance-110)

- **Migration impact.**  Operators with `risk_classification:
  high-risk` + `safety.enabled: false` previously got a warning;
  now they get a hard `ConfigError`.  Walk:
  - Is there a clear migration path documented?  (CHANGELOG entry
    + release note + the error message itself.)
  - Could a sandboxed-test config legitimately need this combination?
    What's the documented escape hatch (lower the risk_classification?
    enable safety eval?)?
  - Are existing fixtures / templates (`config_template.yaml`,
    `forgelm/templates/*.yaml`) compatible with the new contract?
- **Test coverage.**  The new `test_high_risk_safety_disabled_raises_config_error`
  pins the breaking-change contract.  Does it also cover the
  `unacceptable` tier (Article 5 prohibited practices)?
- **Webhook timeout default change.**  5s → 10s could affect
  performance benchmarks or long-tail Slack/Teams gateway timing.
  Is the new default backward-compatible (operators who explicitly
  set `timeout: 5` continue to get 5s)?
- **Audit-report log level (F-compliance-111).**  INFO → WARNING.
  Could this generate noise in CI runs that don't actually need
  the data_audit_report (e.g. quickstart smoke tests)?  Is the
  warning suppressible via `--quiet`?

### Cross-phase (XPR) checks

- **XPR-01 Audit-event vocabulary.**  `data.access_request_query`
  is the new event.  Verify:
  - Catalogue entries (`docs/reference/audit_event_catalog.md` +
    `-tr.md`) match the actual emit payload.
  - Every emit site of the event uses the centralised
    `_EVT_ACCESS_REQUEST_QUERY` constant.
- **XPR-02 Exit-code contract.**  Every `sys.exit(N)` in
  `_reverse_pii.py` resolves to 0/1/2 per
  [docs/standards/error-handling.md].  Confirm no literal integer
  exits.
- **XPR-03 JSON envelope schema.**  The reverse-pii success envelope
  documented at
  `docs/usermanuals/{en,tr}/reference/json-output.md` matches the
  actual emitted shape (`{"success": true, "query_hash", ...}`).
- **XPR-04 Documentation drift.**  Every CLI flag of `reverse-pii`
  appears in:
  - `docs/usermanuals/{en,tr}/reference/cli.md` (top-level table).
  - `docs/usermanuals/{en,tr}/reference/json-output.md` (envelope schema).
  - `docs/guides/gdpr_erasure.md` + `-tr.md` (operator guide).
  - `forgelm/cli/_parser.py` epilog.
- **XPR-05 Test rigour.**  Scan the new test files for vacuous
  assertions (`assert True`, `assert payload`, asserting only on
  fixture's own shape).  None of the new tests should pass on a
  broken implementation.
- **XPR-06 Backwards compatibility.**  F-compliance-110 is a hard
  break.  Are there other accidental BC breaks?  Walk:
  - Removed `_is_private_destination` re-export from
    `forgelm.webhook` — confirm no test or downstream import was
    missed.
  - Renamed `test_integration_smoke.py` → `test_integration.py` —
    confirm no CI workflow matches against the old name.
- **XPR-07 Bilingual mirror parity.**  `tools/check_bilingual_parity.py
  --strict` passes against the live tree.  Does it report ALL drifts
  (no silent passes from a missing pair entry)?  Spot-check a known
  pair.

## Ground rules

- **Read the relevant standard before commenting.** The project
  [docs/standards/](../../standards/) directory is the rulebook.
- **Cite line numbers.**  If you cannot point at a line, the finding
  is not actionable.
- **Distinguish the tool from the contract.**  A bug in
  `check_bilingual_parity.py` is a tool defect.  A drift the tool
  caught is a doc defect.  Different fixes, different urgency.
- **No phantom severity inflation.**  A doc typo is `NIT`.  A
  user-visible CLI bug on the happy path is `HIGH` minimum.
- **No re-litigating closed scope.**  "Should ForgeLM also do X" is
  not a finding.  Stay in the diff.
- **No suggestions to add a Web UI / GUI / inference engine /
  pretraining pipeline.** See
  [docs/marketing/strategy/05-yapmayacaklarimiz.md] — these are out
  of scope by design (read root `CLAUDE.md` "What ForgeLM is not").
- **Behaviour changes need migration paths.**  F-compliance-110 is
  the only intentional break in this PR; if you flag another, name
  it explicitly.
- **Reverse-pii is a privacy-sensitive surface.**  The tool reads
  cleartext PII from disk and writes hashed identifiers to the
  audit chain.  Treat any path where the cleartext can leak into
  the audit log as `CRITICAL`.

## Required deliverable structure

Each reviewing agent returns a single Markdown report with this
skeleton:

```markdown
# Wave 3 — <agent-name> Review of `closure/wave3-integration`

## Summary
- Verdict: [Block / Conditional / Approve]
- CRITICAL: N · HIGH: N · MEDIUM: N · LOW: N · NIT: N
- One-sentence headline of the highest-severity finding.

## Findings

### F-W3-NN · <SEVERITY> · <one-line headline>
- **File:** `path/to/file.py:LINE` (or `:LINE-RANGE`)
- **What's wrong:** <1-3 sentences — concrete defect, not vague concern>
- **User-visible consequence:** <what an operator sees / loses>
- **Suggested fix:** <code or text snippet>
- **Regression test:** <test file + assertion stub>

(repeat per finding, ordered: CRITICAL → HIGH → MEDIUM → LOW → NIT)

## Cross-phase observations
(F-XPR-NN entries, same structure)

## Verified absorptions
List anything the PR claims to do that you confirmed is actually
done.  E.g.:
- F-W3-Audit [verified] — raw `--query` does not appear in any
  field of `data.access_request_query` payload (walked the emit
  site at `_run_reverse_pii_cmd:182-200`).
- F-W3-Glob [verified] — empty glob expansion exits 1 (regression
  at `tests/test_reverse_pii.py::TestFailurePaths::test_empty_glob_exits_config_error`).

## What this report deliberately did not cover
(Out-of-scope items the agent looked at and declined to flag, with
one sentence each.  This keeps later reviewers from re-treading the
same ground.)

## Merge recommendation
- One paragraph: "Ship as-is" / "Ship after addressing F-W3-NN" /
  "Block — see CRITICAL findings."  This is the agent's call.  The
  maintainer arbitrates between agents.
```

## How to launch

Spawn at minimum these agents in parallel:

1. **Code-correctness agent** — focuses on Phase 38 (`_reverse_pii.py`)
   defects.  Read the dispatcher end-to-end.  Trace the audit-event
   payload.  Walk every error path with paper-and-pencil.  Verify
   the hash-mask path round-trips against `forgelm purge`'s salt.
2. **Standards-compliance agent** — focuses on cross-phase checks
   XPR-01 through XPR-07 against
   [docs/standards/](../../standards/).  Audit-event vocabulary,
   exit codes, JSON envelope schema, regex / ReDoS exposure,
   error-handling discipline.  Bilingual parity (Faz 24) is the
   localisation standard's domain.
3. **Test-rigor agent** — focuses on whether the tests in
   `test_reverse_pii.py` (18 cases), `test_check_bilingual_parity.py`
   (16 cases), and the modified `test_eu_ai_act.py` /
   `test_compliance.py` actually verify what they claim to.  Hunt
   for vacuous assertions and missing edge-case coverage on the
   new contracts.
4. **Privacy / security agent** — focuses on the
   `forgelm reverse-pii` surface specifically.  This is a tool that
   reads cleartext PII from operator-supplied corpora.  Walk every
   code path where the raw query could leak to disk (audit log,
   stdout, stderr, JSON envelope, log records).  Walk the snippet
   truncation: could a malformed UTF-8 corpus + centre-truncation
   produce invalid output?  Walk the custom-regex path: ReDoS
   exposure?

Each agent gets this prompt verbatim plus a one-line `Focus:`
directive naming its specialty.  Agents must not coordinate; the
maintainer deduplicates after.

## Delivery

- Agents return their reports in
  `docs/analysis/code_reviews/wave3-<agent>.md`.
- The maintainer (Cemil) merges findings, dedups, and posts the
  unified list on the PR as a top-level comment.
- Block / Conditional / Approve gating decision rests with the
  maintainer after consolidation, **not** with any individual agent.
- After this round, surviving findings will be addressed in
  absorption commits, then the branch will be merged to
  `development`.

---

*Prompt frozen 2026-05-05 against `closure/wave3-integration` HEAD `61d74fa`.*

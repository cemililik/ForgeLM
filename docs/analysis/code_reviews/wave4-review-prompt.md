# Wave 4 — Multi-Agent Code Review Prompt (PR #33)

> **Use this prompt verbatim** to launch the multi-agent review on
> the consolidated Wave 4 PR.  The prompt is self-contained: each
> reviewing agent can pick it up cold without context from prior
> conversations.
>
> Wave 4 consolidates four closure-plan phases (Faz 22 + 23 + 26 +
> Faz 30 partial).  No prior absorption rounds yet — this is the
> FIRST review pass.  Treat the bar accordingly: catch the issues
> now, before any operator-visible regressions land.

---

## Repo & branch under review

- **Repo:** `cemililik/ForgeLM`
- **PR:** [#33](https://github.com/cemililik/ForgeLM/pull/33)
  (`closure/wave4-integration` → `development`)
- **Frozen HEAD:** `8f69cf1`
- **Diff vs `development`:** ~30 files, ~3500 insertions, ~50
  deletions.  Five new code/tool files
  (`tools/check_pip_audit.py`, `tools/check_bandit.py`,
  `tools/check_anchor_resolution.py`,
  `tests/test_supply_chain_security.py`,
  `tests/test_check_anchor_resolution.py`), one new design doc
  (~865 lines), four new QMS docs (EN), ten new QMS TR mirrors,
  one new guide pair (EN+TR), three new reference pairs (EN+TR),
  five modified usermanual EN+TR pairs (ghost-feature drift).
- **What it consolidates:** Faz 22 (ISO 27001 / SOC 2 alignment
  design), Faz 23 (implementation: pip-audit + bandit CI, 4 new
  QMS docs, deployer guide, 3 reference tables), Faz 26 (QMS
  bilingual mirror sweep + `compliance_summary.md` cleanup +
  `tools/check_anchor_resolution.py`), Faz 30 partial (Tier 1
  ghost-feature drift + stat blocks).

## What ForgeLM is (60 seconds)

A **config-driven, enterprise-grade LLM fine-tuning toolkit** —
YAML in, fine-tuned model + compliance artifacts out.  Built for
CI/CD pipelines, not notebooks.  Six alignment paradigms
(SFT/DPO/SimPO/KTO/ORPO/GRPO), integrated safety evaluation
(Llama Guard), EU AI Act compliance artefacts (Articles 9–17 +
Annex IV), append-only audit log, opt-in human approval gate,
auto-revert on quality regression, GDPR Article 15 + 17 subject
rights tooling.  Wave 4 adds the deployer-side ISO 27001 / SOC 2
Type II audit-evidence layer.  Read [docs/product_strategy.md](../../product_strategy.md)
for the fuller background.

Project rulebook lives under [docs/standards/](../../standards/) —
read [coding.md](../../standards/coding.md),
[error-handling.md](../../standards/error-handling.md),
[testing.md](../../standards/testing.md),
[logging-observability.md](../../standards/logging-observability.md),
[regex.md](../../standards/regex.md),
[localization.md](../../standards/localization.md),
[documentation.md](../../standards/documentation.md), and
[code-review.md](../../standards/code-review.md) before
commenting.  Project-wide guidance for AI agents is in the root
`CLAUDE.md`.

## Critical framing for this review (don't skip)

**Wave 4's headline claim is ALIGNMENT, not CERTIFICATION.**
Software (a Python library) cannot be ISO 27001 certified — only
**organisations** can.  Wave 4's design doc Decision D-22-01 makes
this explicit.  If you find any text in this PR that says
"compliant" or "certified" instead of "aligned" / "supports the
deployer's certification" — flag it CRITICAL.  This is the
single highest-impact regression a reviewer can catch.

Additionally:

- **Don't gate the auditor's deployer-side controls.**  ForgeLM
  contributes evidence; the deployer enforces.  Reject any PR text
  suggesting ForgeLM "enforces" things it merely records.
- **Salt + HMAC chain are tamper-evidence, not non-repudiation.**
  Reject any text saying ForgeLM provides cryptographic
  non-repudiation in a PKI sense.
- **No SPDX claim.**  The SBOM emitter is CycloneDX 1.5 (Wave 2
  era).  Decision D-22-02 commits to that.  Reject any text
  saying ForgeLM ships SPDX SBOMs.

## What we want from this round

**Goal:** decide whether `closure/wave4-integration` at `8f69cf1`
is mergeable to `development`.  Block on real defects; do not gate
on style nits or hypothetical futures.

Be concrete.  Every finding must include:

1. **Severity tag** — `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` / `NIT`.
2. **Finding ID** — `F-W4-NN` (e.g. `F-W4-01`, `F-W4-12`).
3. **File:line citation** — `tools/check_pip_audit.py:48` or a
   short range `:42-55`.
4. **One-paragraph reasoning** — what is wrong, what is the
   user-visible consequence, why it qualifies for that severity.
5. **Suggested fix** — a code or text snippet, not a vague
   direction.
6. **Test that would have caught it** — name the test file + a
   stub of the assertion.  For doc-only findings, name the
   anchor checker rule that should have caught it.

Severity bar:

- `CRITICAL` — would corrupt data, silently lose audit events,
  leak PII / secrets, break the public exit-code contract
  (`0/1/2/3/4`), break the `--offline` / air-gap promise,
  invalidate the audit-log hash chain, OR mislead the deployer
  into believing they are ISO/SOC 2 *certified* (vs. *aligned*).
  Blocks merge.
- `HIGH` — runtime crash on a documented happy path, missing test
  for a documented contract, schema mismatch with `pyproject.toml`
  / `config.py`, documentation claim with no code backing, or a
  behaviour change that breaks 0.5.x users without a clear
  migration path.  Blocks merge.
- `MEDIUM` — logic bug in an off-the-happy-path branch,
  observability gap, or design-doc statement that contradicts
  shipped code.  Should be fixed before merge but the call is
  the maintainer's.
- `LOW` — defensive-coding improvement, minor inconsistency,
  missing edge-case test.
- `NIT` — naming, line wrap, comment phrasing.  Note in passing
  only; do not stack these.

## Areas to scrutinise

These are the surfaces most likely to harbour real issues.  Hit
them specifically.

### Faz 22 design doc — `docs/analysis/code_reviews/iso27001-soc2-alignment-202605052315.md`

- **Citation accuracy.** Every cited symbol (`forgelm.compliance.AuditLogger`,
  `_purge._resolve_salt`, `_reverse_pii._scan_file_with_alarm`,
  etc.) must exist in the codebase at the cited file.  Grep each
  one. The doc claims to verify against HEAD — was it really?
- **Coverage tally honesty.**  §3 claims "FL 11 / FL-helps 50 / OOS
  32 = 93".  Walk the table and recount.  An off-by-one is a
  HIGH finding (deployer auditors trust the count).
- **Decision Log internal consistency.**  D-22-01 (alignment vs
  certified) must be reflected in every customer-facing artefact
  in the diff.  D-22-02 (CycloneDX not SPDX) must be reflected in
  the supply_chain_security reference doc + README + CHANGELOG.
  Cross-check.
- **FAQ accuracy.**  The 10 FAQ Q/A pairs must match the cited
  ForgeLM behaviour.  E.g. Q5 (GDPR Article 15 response) must use
  the actual `forgelm reverse-pii` flag set the parser exposes.
- **Length claim.**  Closure plan acceptance bar was ≥800 lines;
  the doc commits at 865.  Confirm `wc -l` matches.

### Faz 23 supply-chain tooling

- **`tools/check_pip_audit.py`.**  Walk the severity tier mapping
  (`HIGH` / `CRITICAL` / `MEDIUM` / `MODERATE` / `LOW` /
  `UNKNOWN`).  Are there real-world pip-audit JSON shapes the
  parser misses?  Walk the GHSA imports that put severity in
  `aliases[].severity[].type` (the 2.6.x shape) — is the fall-
  through correct?
- **`tools/check_bandit.py`.**  Same — walk the bandit JSON
  shape.  HIGH / MEDIUM / LOW + UNDEFINED tiering.  Does the
  parser handle bandit's confidence + severity orthogonally
  correctly?
- **`tests/test_supply_chain_security.py::TestGenerateSbomDeterministic`.**
  The test strips `serialNumber` + `metadata.timestamp` before
  comparing.  Are those the ONLY non-deterministic fields in
  CycloneDX 1.5?  Is the strip approach robust to future emitter
  changes?
- **`pyproject.toml [project.optional-dependencies] security`.**
  Pinning ranges (`pip-audit>=2.7.0,<3.0.0`,
  `bandit[toml]>=1.7.0,<2.0.0`) — are these the right
  upper-bounds?  Will pip-audit 3.x break the JSON shape the
  helper parses?
- **`.github/workflows/ci.yml` bandit step.**  The step pipes
  `|| true` to suppress bandit's exit code, then runs
  `tools/check_bandit.py` for the actual gate.  Confirm the
  failure path: if the JSON file is malformed, does the helper
  still exit 1 (preventing a green CI on a real bandit crash)?
- **`.github/workflows/nightly.yml supply-chain-security` job.**
  The job uploads `/tmp/pip-audit.json` + `/tmp/bandit.json` as
  artefacts.  Confirm the path is correct on macOS / Windows
  runners (the job is ubuntu-latest, so this is fine, but flag
  if any cross-OS port is intended later).

### Faz 23 QMS docs (EN-only, TR mirrors land in Faz 26)

- **`docs/qms/encryption_at_rest.md`.**  §3 threat model claims
  "kripto-algoritma break out of scope".  Is that a defensible
  framing for an ISO 27001 doc?  ISO A.8.24 explicitly addresses
  algorithm agility — should we flag a residual risk?
- **`docs/qms/access_control.md`.**  §3.4 claims `FORGELM_AUDIT_SECRET`
  rotation should NOT happen mid-output-dir.  Walk this against
  the actual `_resolve_salt` code path: does mid-output-dir env
  rotation actually break verify-audit, or does the salt-source
  recording (Wave 3 followup F-W3-PS-07) make this safer than the
  doc suggests?
- **`docs/qms/risk_treatment_plan.md`.**  12 risks documented.
  R-05 (memorisation residual) is HIGH→MED.  Is that an honest
  reduction given the only "treatment" is operator-side
  notification?  Should it be HIGH→HIGH with explicit risk
  acceptance?
- **`docs/qms/statement_of_applicability.md`.**  93-control SoA.
  Walk against the §3 design-doc table — are the same controls
  classified the same way?

### Faz 23 deployer guide + reference docs

- **`docs/guides/iso_soc2_deployer_guide.md` (+ TR).**  8 audit-
  floor questions answered.  Walk each: is the `jq` / `gh`
  command syntactically correct?  Will it work on macOS jq +
  Linux jq?
- **`docs/reference/iso27001_control_mapping.md` (+ TR).**  Is
  every cell filled?  Spot-check 5 random rows — does the
  ForgeLM-evidence claim hold?
- **`docs/reference/soc2_trust_criteria_mapping.md` (+ TR).**
  Same.
- **`docs/reference/supply_chain_security.md` (+ TR).**  The
  Dependency-Track ingestion command — verified against current
  Dependency-Track API?

### Faz 26 — QMS bilingual mirrors

- **Structural parity.**  10 QMS docs now have TR mirrors but
  QMS pairs are NOT in `tools/check_bilingual_parity.py::_PAIRS`
  yet.  Should they be?  If yes, file as a finding for Faz 30
  follow-up to register them.
- **Translation faithfulness.**  Spot-check 3 random TR mirrors
  against the EN.  Are technical terms (`audit chain`,
  `genesis manifest`, `salted hash`) translated consistently?
- **Code-block transcription.**  The shell snippets in the
  audit-log + GDPR sections must match between EN + TR.  Verify
  the 5+ shell snippets in `iso_soc2_deployer_guide.md` /
  `-tr.md` are byte-identical.

### Faz 26 — `compliance_summary.md` rewrite

- **Anchor-resolution claim.**  The new doc claims
  "module-path + symbol-name references that survive refactors"
  — are the new references ACTUALLY symbol references, or did
  some line-anchor sneak through?
- **Stat update.**  "140 prompts × 6 categories" — verify
  against `configs/safety_prompts/*.jsonl` count + the
  in-`forgelm/safety.py` category list.

### Faz 26 — `tools/check_anchor_resolution.py`

- **Slugify accuracy.**  GFM slug rules differ slightly from
  GitLab.  Does the helper produce the same slug GitHub renders
  for these edge cases?
  - "Section 1.2: Why?"
  - "What's New"
  - "Türkçe başlık"  (Unicode)
  - "Heading with `code`"
- **Skip patterns.**  The helper skips `https://`, `mailto:`,
  `tel:`, `javascript:`, `#/`.  Is the SPA hash-router skip
  comprehensive?  E.g. does `#/data/ingestion?param=foo` get
  skipped (it should — query strings on SPA paths)?
- **Advisory-mode default.**  The closure plan called for a CI
  gate.  The maintainer's commit message defends advisory-mode
  default with "36 broken links pre-Faz-26 baseline".  Is that
  acceptable?  Or should the tool ship with `--strict` enabled
  + the pre-existing breaks fixed in this commit?

### Faz 30 partial — ghost-feature drift fixes

- **GH-008 verify-log → verify-audit.**  Are there OTHER docs
  citing `verify-log`?  Grep the tree.
- **GH-021 chat slash commands.**  The fix removes
  `/load`, `/top_p`, `/max_tokens`, `/safety on|off`.  Confirm
  these don't exist by running `forgelm chat --help` against
  the parser.
- **GH-022 q6_k removal.**  Confirm parser only supports
  `q2_k|q3_k_m|q4_k_m|q5_k_m|q8_0|f16` at
  `forgelm/cli/_parser.py:75-76`.
- **GH-024 FORGELM_RESUME_TOKEN.**  Confirm there's NO real
  resume endpoint or env-var-driven approval API in the code.
  Grep `forgelm/`.
- **GH-025 FORGELM_CACHE_DIR.**  Same — confirm no env var of
  this name is consumed.

### Cross-cutting (XPR)

- **F-XPR-01 — alignment-vs-certified wording sweep.**  `grep
  -rni 'iso 27001 compliant\|iso 27001 certified\|soc 2 compliant\|soc 2 certified'
  docs/ README.md CHANGELOG.md` should return zero (or only
  "alignment with" / "deployer's certification" hits).
- **F-XPR-02 — bilingual parity strict.**  `python3 tools/check_bilingual_parity.py
  --strict` should exit 0 with 13 pairs.
- **F-XPR-03 — pytest count.**  `pytest --collect-only -q` should
  show ≥1397 tests.
- **F-XPR-04 — `forgelm --dry-run` green** on `config_template.yaml`.
- **F-XPR-05 — anchor-checker count.**  Run
  `tools/check_anchor_resolution.py` and confirm the broken-link
  count matches the maintainer's claim ("36 baseline").  An
  increase in broken links from this PR is a `MEDIUM` finding.
- **F-XPR-06 — closure-plan honesty.**  `docs/analysis/code_reviews/closure-plan-202604300906.md`
  Wave 4 kapanış özeti row enumerates the deliverables — every
  named file should exist in the diff.
- **F-XPR-07 — `[security]` extra resolves.**  `pip install -e
  .[security]` (or equivalent dry-resolve) should resolve to
  pip-audit + bandit pinned ranges without conflict.

## Ground rules

- **Read the relevant standard before commenting.** The project
  [docs/standards/](../../standards/) directory is the rulebook.
- **Cite line numbers.**  If you cannot point at a line, the
  finding is not actionable.
- **Distinguish design-doc claim from runtime contract.**  A
  Decision Log entry that the code doesn't honour is a
  CRITICAL — the maintainer commits to a specific design and
  the code must follow.  But "the design says X and the code
  does X but X could be Y" is at most a MEDIUM design-rationale
  question.
- **No phantom severity inflation.**  A doc typo is `NIT`.  A
  user-visible CLI bug on the happy path is `HIGH` minimum.  An
  auditor-misleading wording (alignment vs certified) is
  `CRITICAL`.
- **No re-litigating closed scope.**  "Should ForgeLM also do X"
  is not a finding.  Stay in the diff.
- **No suggestions to add a Web UI / GUI / inference engine /
  pretraining pipeline.** See
  [docs/marketing/strategy/05-yapmayacaklarimiz.md] — these are
  out of scope by design (read root `CLAUDE.md` "What ForgeLM is
  not").
- **Wave 4 explicitly defers some closure-plan Faz 30 items**
  (GH-016/018/019/020 cli.md cleanup, sample-audit user-facing
  doc completion, `tools/check_cli_help_consistency.py`,
  full-suite anchor-strict CI wire-up).  Don't flag those as
  Wave 4 omissions — they're explicit Faz 30 follow-up scope.
- **No ISO/SOC 2 audit-domain claims you can't back from the
  standards text.**  This is a compliance-sensitive surface; if
  you flag a control mapping as wrong, cite the ISO 27001:2022
  Annex A control description or the AICPA TSC clause that
  contradicts ForgeLM's claim.

## Required deliverable structure

Each reviewing agent returns a single Markdown report with this
skeleton, saved as
`docs/analysis/code_reviews/wave4-<agent-name>.md`:

```markdown
# Wave 4 — <agent-name> Review of `closure/wave4-integration`

> Branch: `closure/wave4-integration` · HEAD `8f69cf1` ·
> Reviewer focus: <one-sentence focus>.  Reviewing PR #33.

## Summary
- Verdict: [Block / Conditional / Approve]
- CRITICAL: N · HIGH: N · MEDIUM: N · LOW: N · NIT: N
- One-sentence headline of the highest-severity finding.

## Findings

### F-W4-NN · <SEVERITY> · <one-line title>
- **File:** path:line[-line]
- **What's wrong:** ...
- **User-visible consequence:** ...
- **Suggested fix:** ```code```
- **Regression test:** ```python ...```

(repeat per finding)

## Verified absorptions

For each closure-plan acceptance criterion (Faz 22 §13, Faz 23 §13,
Faz 26 task list, Faz 30 task O subset), state:

- **<acceptance item> [verified]** — confirmed at <file:line>;
  walked: <what you walked>.
- **<acceptance item> [partial]** — addressed at <file:line> but
  misses <Y>; new finding F-W4-NN tracks it.
- **<acceptance item> [missing]** — not in the diff.  Maintainer
  documented as deferred to Faz 30 follow-up.

## What this report deliberately did not cover

(scope notes, deferred items, out-of-PR areas)

## Merge recommendation

(Block / Conditional / Approve, with the headline reasons)
```

## How to launch

Spawn 4 parallel sub-agents (any harness with parallel workers; the
prior waves used Claude `Agent` calls in a single message).  Pass
each agent the SAME prompt with one extra line at the top stating
its agent name + focus:

1. **Code-correctness agent.** Focus areas: §A (Faz 22 design
   citation accuracy), §B (Faz 23 supply-chain tooling logic), §G
   (anchor-resolution checker correctness), §F (cross-cutting XPR-
   01/02/03/04/05/07).
2. **Privacy / security agent.** Focus areas: §C (Faz 23 QMS docs:
   encryption / access / RTP / SoA), §B again from a security
   posture lens (severity tiers correct?  CVE policy reasonable?),
   §F-XPR-01 (alignment-vs-certified wording — privacy bar).
3. **Standards / compliance agent.** Focus areas: §A (Faz 22
   coverage tally + decision-log internal consistency), §D
   (deployer guide + reference docs accuracy), §C (RTP / SoA /
   incident-response / change-mgmt SOP expansions).  Cite
   docs/standards/* extensively.
4. **Test-rigour agent.** Focus areas: §B
   (`tests/test_supply_chain_security.py`), §G
   (`tests/test_check_anchor_resolution.py`), §H ghost-feature
   drift verification (do the doc-only fixes match the actual
   parser output?).  Vacuous-test bar reigns.

Agents run independently.  Maintainer absorbs in a single round
(per the established Wave 2-3 cadence: report → multi-round
absorption → followup review prompt).

---

*Frozen at `8f69cf1` on 2026-05-06.*  *If any reviewer finds the
prompt itself ambiguous, surface it as a `F-W4-PROMPT-NN` finding
before merging — the prompt itself is part of the audit trail.*

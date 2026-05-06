# Wave 4 Follow-up — Multi-Agent Code Review Prompt (post-absorption)

> **Use this prompt verbatim** to launch the multi-agent review on the
> 2 absorption commits that landed on PR #33 after the original
> 4-agent review completed. The prompt is self-contained: each
> reviewing agent can pick it up cold without context from the prior
> round.
>
> The original Wave 4 review (per
> [`wave4-review-prompt.md`](wave4-review-prompt.md), HEAD `9a1738a`)
> produced 4 reports under `docs/analysis/code_reviews/wave4-*.md`.
> The maintainer absorbed those reports plus inline PR-comment
> findings (gemini-code-assist) plus SonarCloud quality gate failures
> across **2 commits**. This second-pass review asks: *did the
> absorption correctly address the original findings, and did the
> absorption itself introduce any new defects?*

---

## Repo & branch under review

- **Repo:** `cemililik/ForgeLM`
- **PR:** [#33](https://github.com/cemililik/ForgeLM/pull/33)
  (`closure/wave4-integration` → `development`)
- **HEAD SHA at prompt freeze:** `105285f`
- **Pre-absorption SHA (the snapshot the original 4-agent review
  read):** `9a1738a` (working tree was at `8f69cf1` for §B/§G focus
  agents; review prompt itself was `9a1738a`)
- **Absorption-only diff range:** `git diff 9a1738a..105285f`
  — 30 files changed, ~783 insertions, ~213 deletions.
- **2 absorption commits in scope** (oldest → newest):

  | SHA       | Title                                                                          | Findings absorbed |
  |-----------|--------------------------------------------------------------------------------|-------------------|
  | `ffceaf7` | absorb 4-agent + PR #33 + Sonar review findings                                | F-W4-01..13, F-W4-PS-01..08, F-W4-NIT-01..02, F-W4-TR-01..10 + 2 inline (gemini-code-assist) + 3 Sonar code-smells (python:S3776 ×3) + 1 Sonar hotspot (python:S5852, partial) |
  | `105285f` | drop `_HEADING_RE` to clear Sonar python:S5852 hotspot                          | python:S5852 (final — regex eliminated entirely) |

## What ForgeLM is (60 seconds)

A **config-driven, enterprise-grade LLM fine-tuning toolkit** — YAML
in, fine-tuned model + compliance artifacts out. Built for CI/CD
pipelines, not notebooks. Six alignment paradigms
(SFT/DPO/SimPO/KTO/ORPO/GRPO), integrated safety evaluation
(Llama Guard), EU AI Act compliance artefacts (Articles 9–17 + Annex
IV), append-only audit log, opt-in human approval gate, auto-revert
on quality regression, GDPR Article 15 + 17 subject rights tooling,
ISO 27001 / SOC 2 alignment evidence (Wave 4 / Faz 22 + 23).
Read [docs/product_strategy.md](../../product_strategy.md) for the
fuller background.

Project rulebook lives under [docs/standards/](../../standards/) — read
[coding.md](../../standards/coding.md),
[error-handling.md](../../standards/error-handling.md),
[testing.md](../../standards/testing.md),
[logging-observability.md](../../standards/logging-observability.md),
[regex.md](../../standards/regex.md),
[localization.md](../../standards/localization.md),
[documentation.md](../../standards/documentation.md), and
[code-review.md](../../standards/code-review.md) before commenting.
Project-wide guidance for AI agents is in the root `CLAUDE.md`.

The original 4 review reports under
[`docs/analysis/code_reviews/`](.) document the prior bar:

- [`wave4-code-correctness.md`](wave4-code-correctness.md) — F-W4-01..F-W4-13.
- [`wave4-privacy-security.md`](wave4-privacy-security.md) — F-W4-PS-01..F-W4-PS-08.
- [`wave4-standards.md`](wave4-standards.md) — F-W4-01..F-W4-13 (re-numbered locally).
- [`wave4-test-rigor.md`](wave4-test-rigor.md) — F-W4-TR-01..F-W4-TR-10.

The maintainer's absorption summary is at
[PR #33 the absorption commit message of `ffceaf7`](https://github.com/cemililik/ForgeLM/commit/ffceaf7).

## What this round is for

**Goal:** decide whether `closure/wave4-integration` at `105285f` is
mergeable to `development`, given the absorptions claim to have
addressed the original 4-agent review.

**Question shape:** the previous review framed defects in code shipped
*before* absorption. This review asks two complementary questions:

1. **Did the absorptions correctly fix the original findings?**
   Walk every CRITICAL / HIGH from the 4 prior reports. For each,
   verify the claimed fix lands at the cited file:line and actually
   addresses the original concern (not "a fix that compiles" but
   "the contract the original finding asked about now holds").
2. **Did the absorptions themselves introduce defects?** The diff
   touches 30 files; the largest absorption (`ffceaf7`) reframed
   substantial portions of `docs/qms/` (HMAC misdescription, rotation
   cadence) + rewrote the pip-audit / bandit / anchor-resolution
   tooling logic + grew `tests/test_supply_chain_security.py` and
   `tests/test_check_anchor_resolution.py`. The followup commit
   (`105285f`) eliminated the `_HEADING_RE` regex entirely in favour
   of a procedural ATX-heading parser. Treat both as new code —
   same severity bar as the original review.

Be concrete. Every finding must include:

1. **Severity tag** — `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` / `NIT`.
2. **Finding ID** — `F-W4FU-NN` (e.g. `F-W4FU-01`, `F-W4FU-12`).
3. **File:line citation** — `tools/check_pip_audit.py:62`
   or a short range `:62-86`.
4. **One-paragraph reasoning** — what is wrong, what is the user-visible
   consequence, and why it qualifies for that severity tier.
5. **Suggested fix** — a code or text snippet, not a vague direction.
6. **Test that would have caught it** — name the test file + a stub
   of the assertion.
7. **Trace-back to original finding (if any)** — when re-evaluating
   a claimed absorption, cite the original finding ID
   (e.g. F-W4-01, F-W4-PS-01, F-W4-TR-01) so the maintainer
   can compare against the pre-absorption code.

Severity bar (unchanged from the original prompt — same calibration):

- `CRITICAL` — would corrupt data, silently lose audit events, leak
  PII / secrets, break the public exit-code contract (`0/1/2/3/4`),
  break the `--offline` / air-gap promise, or invalidate the
  audit-log hash chain. Blocks merge.
- `HIGH` — runtime crash on a documented happy path, missing test
  for a documented contract, schema mismatch with `pyproject.toml`
  / `config.py`, documentation claim with no code backing, or a
  behaviour change that breaks 0.5.x users without a clear migration
  path. Blocks merge.
- `MEDIUM` — logic bug in an off-the-happy-path branch, observability
  gap, or design-doc statement that contradicts shipped code.
  Should be fixed before merge but the call is the maintainer's.
- `LOW` — defensive-coding improvement, minor inconsistency, missing
  edge-case test that would not have changed PR direction.
- `NIT` — naming, line wrap, comment phrasing. Note in passing
  only; do not stack these.

## Areas to scrutinise

These are the surfaces most likely to harbour real issues *post-absorption*.

### A. Coverage tally arithmetic (claims to absorb F-W4-01 / F-W4-02)

The single most-cited claim across the absorption is the recount
`FL 11 / FL-helps 48 / OOS 34` (replacing the original `11 / 50 /
32`). Per-theme split: A.5: 3 / 24 / 10 · A.6: 0 / 5 / 3 ·
A.7: 0 / 0 / 14 · A.8: 8 / 19 / 7. The recount is propagated to:

- `iso27001-soc2-alignment-202605052315.md:264-269` (design doc §3
  closing paragraph).
- `iso27001-soc2-alignment-202605052315.md:790-795` (FAQ Q1, "59
  of 93").
- `statement_of_applicability.md:148-152` + `-tr.md` (per-theme
  table + total row).
- `iso27001_control_mapping.md:16` + `-tr.md` (header tally).
- `CHANGELOG.md:20-22` (release-notes line).

#### A.1 — Per-theme arithmetic verifiability

- **F-W4FU-XX-A1** — Walk §3.1 (A.5 — 37 rows), §3.2 (A.6 — 8 rows),
  §3.3 (A.7 — 14 rows, prose only), §3.4 (A.8 — 34 rows) of the
  design doc. For each theme, count `FL` / `FL-helps` / `OOS`
  occurrences per row. The numbers must match the published
  per-theme split exactly. If any theme is off by even 1, the
  closing paragraph and SoA per-theme breakdown are both wrong
  again.
- A.5: spot the `FL` rows (must be A.5.28, A.5.33, A.5.34). Confirm
  3 not 4.
- A.6: spot the `FL-helps` rows (must be A.6.3, A.6.4, A.6.5,
  A.6.7, A.6.8). Confirm 5 not 4. `OOS` rows must be A.6.1,
  A.6.2, A.6.6 (3 not 4).
- A.8: spot the `FL` rows (must be A.8.3, A.8.9, A.8.10, A.8.11,
  A.8.12, A.8.15, A.8.24, A.8.32). Confirm 8 not 7.
- A.8.30 was OOS in the design doc and remains OOS — but the
  supply_chain_security.md "Related controls" mapping previously
  cited it; absorption dropped it. Confirm the design-doc OOS
  count still accounts for A.8.30.
- A.8.34: design doc + ISO mapping list it; SoA table is the
  contract auditor signs. Cross-check the SoA "Excluded" column
  shows A.8.34 as included (the table only excludes A.7 14 rows
  per the totals).

#### A.2 — FAQ Q1 arithmetic

- **F-W4FU-XX-A2** — `iso27001-soc2-alignment-202605052315.md:790-795`
  now says "59 of 93". The arithmetic is `11 + 48 = 59`. Confirm
  the surrounding prose ("The remaining 34 controls (mainly A.7
  physical, A.5 organisational governance, A.8 network / cloud)")
  reconciles with the per-theme OOS breakdown (A.5 = 10, A.6 = 3,
  A.7 = 14, A.8 = 7 → "mainly A.7 physical (14)" is honest;
  the qualifier "A.5 governance (10) + A.8 network / cloud (7)"
  must add to 17). Total OOS = 14 + 10 + 3 + 7 = 34. ✓

### B. HMAC chain key reframing (claims to absorb F-W4-PS-01 / F-W4-08)

The most consequential narrative change. Before absorption, four
docs claimed the chain key was the env secret XOR'd with the
per-output-dir salt (`_resolve_salt`). The real derivation is
`SHA-256(FORGELM_AUDIT_SECRET ‖ run_id)` per
[`forgelm/compliance.py:104-114`](../../../forgelm/compliance.py#L104-L114),
and the per-output-dir salt is purge / reverse-pii's identifier-hash
salt, a distinct concern. The reframing is propagated to:

- `access_control.md:78-100` + `-tr.md` (§3.4 expanded).
- `risk_treatment_plan.md:75-84` + `-tr.md` (R-04 row).
- `iso27001-soc2-alignment-202605052315.md:252` (A.8.24 row).
- `iso27001_control_mapping.md:122` + `-tr.md` (A.8.24 row).

#### B.1 — Code citation accuracy

- **F-W4FU-XX-B1** — Open `forgelm/compliance.py:104-114` and confirm:
  - Line 112: `raw_secret = os.getenv("FORGELM_AUDIT_SECRET", "")`.
  - Line 114: `self._hmac_key: Optional[bytes] = hashlib.sha256(raw_secret.encode() + self.run_id.encode()).digest()`.
  - There is no XOR with `_resolve_salt`'s output anywhere in the
    chain-key path. (`_resolve_salt` lives in
    `forgelm/cli/subcommands/_purge.py:155-183` and is invoked only
    by `forgelm purge` / `forgelm reverse-pii`, not the
    `AuditLogger`.)
- The verifier path at `forgelm/compliance.py:1252` uses the same
  derivation: `key = hashlib.sha256(hmac_secret.encode() + run_id.encode()).digest()`.
  Confirm the absorbed prose's claim of `forgelm/compliance.py:104-114`
  cite range covers the writer's derivation; cross-check the
  verifier cite at `:1252` is implicit.

#### B.2 — Per-output-dir-salt distinction

- **F-W4FU-XX-B2** — The reframed prose calls the per-output-dir
  salt "a distinct concern" that "salts purge / reverse-pii
  identifier hashes and does NOT participate in chain-key
  derivation." Walk:
  - Is that *strictly* true at every code path? Search the codebase
    for any usage of `_resolve_salt` outside `_purge.py` /
    `_reverse_pii.py`.
  - The audit event `salt_source` field (Wave 3 follow-up F-W3-PS-07)
    — is its meaning unchanged? It records `per_dir` vs `env_var`
    for the IDENTIFIER hash, not the chain key. Confirm the
    audit-event catalog reflects this.

#### B.3 — Rotation cadence reframing (claims to absorb F-W4-PS-02)

- **F-W4FU-XX-B3** — Before absorption, the docs said "quarterly".
  After: "between output-dir lifecycles". Walk:
  - `access_control.md:78-100` (EN) and `-tr.md` — does the new
    procedure correctly explain that rotating mid-output-dir would
    break `forgelm verify-audit --require-hmac`? Test the claim by
    writing a chain with secret A, rotating to secret B, appending
    one entry, and running `verify-audit --require-hmac`: does it
    actually fail? (If the verifier only checks line N's HMAC against
    the secret it was emitted with, mixed-secret chains might still
    verify.)
  - `iso_soc2_deployer_guide.md:51-57` checklist (EN+TR) — same
    question.
  - The §8 audit checklist's bullet "KMS audit log shows
    `FORGELM_AUDIT_SECRET` rotation aligned to output-dir lifecycle
    boundaries" — is "lifecycle boundary" defined operationally?
    A deployer auditor needs to be able to identify a boundary in
    their KMS log; what's the signal?
- The CHANGELOG was NOT updated to call out this reframing as a
  change in deployer guidance vs the prior `quarterly` advice.
  Should it be?

### C. CLI cookbook fixes (claims to absorb F-W4-01 / F-W4-02 / F-W4-PS-06)

Four files cited `forgelm verify-audit --output-dir ./outputs --json`
— neither flag exists. The absorption replaced the invocation with
`forgelm verify-audit ./outputs/audit_log.jsonl --require-hmac`
across:

- `iso_soc2_deployer_guide.md:92-98` + `-tr.md`.
- `access_control.md:178-198` + `-tr.md` (§6 jq pipeline rewritten
  with `--slurpfile`).

#### C.1 — Parser surface confirmation

- **F-W4FU-XX-C1** — Open `forgelm/cli/_parser.py:484-521` (the
  `verify-audit` subparser definition) and confirm:
  - Positional `log_path` exists.
  - `--require-hmac` is a flag (no value).
  - `--hmac-secret-env` exists with a default.
  - `--output-dir` is NOT defined.
  - `--json` is NOT defined.
  Run `python3 -m forgelm.cli verify-audit --help` and confirm the
  printed help matches the absorbed prose.

#### C.2 — jq pipeline correctness (claims to absorb gemini-code-assist
medium)

- **F-W4FU-XX-C2** — The new jq pipeline:

  ```bash
  jq -r 'select(.event == "training.started") |
         [.run_id, .operator] | @tsv' \
      ./outputs/audit_log.jsonl > /tmp/trainers.tsv

  jq -r --slurpfile t /tmp/trainers.tsv \
        'select(.event == "human_approval.granted") |
         . as $a |
         $t[] | split("\t") as $row |
         select($row[0] == $a.run_id and $row[1] == $a.operator) |
         [.run_id, .operator] | @tsv' \
      ./outputs/audit_log.jsonl
  ```

  Walk:
  - The first pass writes TSV to `/tmp/trainers.tsv`. Tab-separated
    `[.run_id, .operator]` — does jq's `@tsv` correctly emit the
    raw fields? If `.operator` contains a tab character (rare but
    possible for OIDC `oidc:gha:repo:...` strings), the second
    pass's `split("\t")` would break.
  - The second pass uses `--slurpfile t /tmp/trainers.tsv` — but
    `--slurpfile` reads JSON, not TSV. This should fail loudly.
    Test the pipeline against a synthetic audit log with one
    `training.started` + one matching `human_approval.granted` and
    confirm it actually finds the segregation violation. If the
    pipeline doesn't run, this is HIGH (ships broken cookbook
    again).
  - Mirror the test on the TR file.

#### C.3 — Reference doc consistency (claims to absorb F-W4-PS-06)

- **F-W4FU-XX-C3** — `access_control.md:122-130` (EN+TR) GitLab CI
  block — the absorption swapped from `script: - export
  FORGELM_OPERATOR=...` to `variables: FORGELM_OPERATOR: "..."` +
  inline comment about the secret manager. Walk:
  - Is the GitLab CI `variables:` form actually the right shape?
    GitLab supports both `variables:` block and `script: export`
    pattern; the new form is cleaner but does not show the
    `FORGELM_AUDIT_SECRET` injection. The comment says "inject
    from Settings → CI/CD → Variables" — is that operator-actionable
    without the YAML cue?
  - Compare to the GitHub Actions block (`access_control.md:101-117`)
    + Jenkins block (`:131-145`): both inject `FORGELM_AUDIT_SECRET`
    in the YAML / Groovy. Symmetric across the three CI platforms?

### D. `tools/check_pip_audit.py` — severity logic rewrite
(claims to absorb F-W4-04 / F-W4-PS-07 / F-W4-TR-02 / F-W4-TR-05)

The pre-absorption helper had three documented contracts but only
honoured one. Rewrite added: CVSS-score-to-tier derivation per
FIRST.org cut-points, 2.6.x `aliases[].severity[]` fallback, and
a single-line UNKNOWN summary annotation.

#### D.1 — Score-type label correctness

- **F-W4FU-XX-D1** —
  [`tools/check_pip_audit.py:46`](../../../tools/check_pip_audit.py#L46)
  defines `_SCORE_TYPE_LABELS` containing
  `{"CVSS", "CVSS_V2", "CVSS_V3", "CVSS_V4", "CVSS_V31", "CVSS_V40"}`.
  Walk:
  - Cross-reference against the OSV schema
    (https://ossf.github.io/osv-schema/#severity-field) and the
    GHSA documentation. Are these the canonical type labels?
    Missing any (e.g. `CVSS_V21` for CVSSv2.1)?
  - The `CVSS` standalone label (without version suffix) — does
    OSV ever emit it? If not, dead defensive code; if yes, what
    score format does it carry?

#### D.2 — CVSS score → tier mapping

- **F-W4FU-XX-D2** — `_tier_from_cvss_score` at `:62-86` uses
  FIRST.org cut-points: 9.0+ CRITICAL, 7.0–8.9 HIGH, 4.0–6.9
  MEDIUM, 0.1–3.9 LOW. Walk:
  - The cut-points apply to CVSS v3 / v4 base scores. CVSS v2
    has different cut-points (7.0–10.0 HIGH, 4.0–6.9 MEDIUM,
    0.0–3.9 LOW). The function does not distinguish. Should it?
    A CVSSv2 base score 7.0 would be classed HIGH today (correct
    by the FIRST.org table for v2 too — same cut-point), but
    CVSSv2 has no CRITICAL tier at all (anything ≥7.0 is HIGH).
    The current code maps CVSSv2 9.5 to CRITICAL — wrong per
    CVSSv2.
  - The score input format — `_tier_from_cvss_score` accepts
    `int / float / str`. OSV's severity entries typically carry
    `score` as either a CVSS vector string (e.g.
    `"CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"`) OR a
    plain numeric base score. The string fallback `float(score.strip())`
    only handles the latter. Verify: do any pip-audit reports
    emit the vector string in `score`? If yes, the function
    silently returns UNKNOWN for those.

#### D.3 — 2.6.x aliases nested fallback

- **F-W4FU-XX-D3** — `_vuln_severity` at `:127-143` falls through
  to `aliases[].severity[]` if the top-level `severity` field is
  empty. Walk:
  - Is the 2.6.x JSON shape actually
    `aliases: [{id: "...", severity: [{...}]}]`? Some OSV exports
    nest under `aliases: [{...}]` with severity as a sibling of
    each alias dict; others put severity at the vuln level.
    Confirm against pip-audit 2.6.x source.
  - The nested loop returns the FIRST non-UNKNOWN tier across all
    aliases. If two aliases carry conflicting tiers (one HIGH,
    one MEDIUM), the result depends on iteration order. Is that
    deterministic?
  - Could this fallback misfire on a vuln that has both a top-level
    `severity` (string) and `aliases[].severity[]` (list)? The
    top-level `isinstance(direct, str)` branch returns first, so
    the alias path is unreachable. But what if `direct` is an
    empty list `[]`? Walk: `isinstance(direct, list)` matches
    empty list, the `for` loop yields nothing, and we fall
    through to aliases. ✓

#### D.4 — UNKNOWN summary annotation

- **F-W4FU-XX-D4** — The new behaviour emits a single
  `::warning::pip-audit N finding(s) without parseable severity`
  line. Walk:
  - Is "without parseable severity" operator-meaningful? An auditor
    walking the nightly run will need to grep the raw JSON
    artefact to triage these. Does the artefact path appear in
    the warning message? (No — by current code.) Does that
    matter?
  - Severity policy implication: pre-absorption, UNKNOWN was silent
    AND counted toward LOW. New behaviour: UNKNOWN warns AND is
    excluded from MEDIUM totals. Walk
    `tests/test_supply_chain_security.py::TestCheckPipAuditExtraShapes::test_missing_severity_field_summary_warning`:
    does it assert exit 0? (Yes, lines 178-179 of the test.) Is
    that the right call given `pip-audit` operators expect
    UNKNOWN to remain non-blocking?

### E. `tools/check_bandit.py` — null-results + UNDEFINED handling
(claims to absorb F-W4-06 / F-W4-TR-01)

Refactored into 3 helper functions + thin orchestrator. The
`results = report.get("results") or []` bug-line was replaced with
explicit "missing key" / "null value" / "non-list" handling.

#### E.1 — Null-results disambiguation

- **F-W4FU-XX-E1** — `_extract_results` at `:39-56`:
  - Missing key → `::error::bandit report missing 'results' field`
    + exit 1.
  - `null` value → `::error::bandit report 'results' is null
    (malformed)` + exit 1.
  - Non-list → `::error::bandit report 'results' field is not a
    list` + exit 1.
  - Empty list → returns `[]`, no error.
  Walk:
  - Does pre-absorption test
    `test_results_not_a_list_fails` still pass? (It asserts the
    "not a list" string in stderr.) Confirm.
  - The new tests `test_results_null_fails` +
    `test_results_missing_key_fails` — are the assertion strings
    distinct enough to catch a regression that collapsed the
    three branches back to one? E.g. if a refactor merged "null"
    + "missing" into one error message, the missing-key test would
    still pass on the null fixture.

#### E.2 — UNDEFINED summary annotation

- **F-W4FU-XX-E2** — `_classify_issues` at `:59-77` separately
  counts UNDEFINED severity (rather than letting it fall into
  LOW silent). Output: `::warning::bandit N issue(s) with
  UNDEFINED severity`. Walk:
  - Same questions as D.4 — operator-meaningful? Should the
    summary include the test_id list of UNDEFINED issues? The
    current implementation drops the per-finding context.
  - The test `test_undefined_severity_summary_warning` asserts
    `"UNDEFINED" in captured` — is the assertion strong enough
    to pin the summary phrasing? A regression that printed the
    UNDEFINED finding line directly (with `[UNDEFINED/LOW]`
    prefix) would also pass this assertion.

### F. `tools/check_anchor_resolution.py` — regex-free ATX parser
(claims to absorb python:S5852 hotspot — both rounds)

The pre-absorption regex `^(.+?)\s*#*\s*$` was replaced in `ffceaf7`
with `^(#{1,6}) +(.+)$` (still flagged by Sonar). The followup
commit `105285f` eliminated the regex entirely in favour of a
procedural `_parse_atx_heading`. Cognitive complexity in
`_resolve_link` + `main` was also reduced via helper extraction.

#### F.1 — Procedural parser correctness

- **F-W4FU-XX-F1** — `_parse_atx_heading` at `:95-119` walks each
  candidate line: count leading hashes (must be 1-6), require a
  space, take rest as body, hand off to `_normalise_heading_body`.
  Walk corner cases against CommonMark §4.2:
  - `# ` (hash + space + nothing) — body is empty; the helper's
    `if not body: return None` rejects. ✓
  - `# heading` — count 1, body "heading". ✓
  - `####### too many hashes` — count 7 (loop continues past 6 to
    count all consecutive hashes); helper rejects. ✓ Wait:
    line 110 checks `hash_count > 6`, but line 108 increments
    while `line[hash_count] == "#"` — for `#######`, `hash_count`
    becomes 7. Then `7 > 6` is True, returns None. ✓
  - `#heading` (no space after hash) — `line[hash_count] != " "`
    triggers the early return at `:113`. ✓
  - `#\theading` (tab after hash, not space) — early return. ✓
    But CommonMark §4.2 says "an opening sequence of 1–6 unescaped
    `#` characters and a space or end-of-line"; tab is NOT
    permitted, so reject is correct. Confirm.
  - `   ## indented heading` (up to 3 leading spaces allowed by
    CommonMark §4.2) — first char is " ", not "#", so
    `_parse_atx_heading` returns None. CommonMark would parse this
    AS a heading; ForgeLM's parser does not. Is that a real
    concern for any project doc? Run a grep to confirm no shipped
    doc starts a heading line with leading whitespace.
  - `## heading ###` (closing-hash decoration) — body is
    `"heading ###"`, then `_normalise_heading_body` strips
    trailing `#`s and the surrounding whitespace. Confirm
    `_normalise_heading_body("heading ###") == "heading"`.
  - `## heading ###extra` (closing hashes followed by more text) —
    `_normalise_heading_body` strips `#` greedily then `rstrip`
    again. Walk: trimmed starts as `"heading ###extra"`,
    `endswith("#")` is False (ends in `"a"`), so the while loop
    never enters, and we return `"heading ###extra"`. ✓ The slug
    will then strip the punctuation. Is that the GFM-correct
    rendering?

#### F.2 — Helper-extraction behaviour invariance

- **F-W4FU-XX-F2** — `_resolve_link` was split into
  `_resolve_pure_anchor`, `_locate_target`,
  `_resolve_anchor_against_target`, plus the orchestrator. Walk:
  - `_locate_target` returns `Path | BrokenLink`. The orchestrator
    uses `isinstance(target_or_broken, BrokenLink)` to dispatch.
    Is the type union safe across all call sites? (If `Path`
    were ever subclassed, would `isinstance(... BrokenLink)`
    misfire? `BrokenLink` is `@dataclass(frozen=True)`; it's not
    a `Path`. ✓)
  - `_resolve_anchor_against_target`'s `re.fullmatch(r"L\d+(?:-L\d+)?", anchor_part)`
    is the only remaining regex in the resolver. Sonar's S5852
    heuristic doesn't flag it because the pattern is
    backtracking-safe. Confirm by reading.
  - `main` was split into `_build_argparser`, `_resolve_excludes`,
    `_collect_broken`, `_report_broken`. Walk: the four helpers
    + the four-line `main` should produce IDENTICAL stdout for
    every input the pre-absorption main accepted. Run the existing
    test suite — does it cover the strict + advisory + quiet +
    exclude flag-combination matrix?

#### F.3 — Sonar hotspot resolution

- **F-W4FU-XX-F3** — The followup commit message claims:
  "Sonar's next analysis on this PR should drop the hotspot to
  zero." Verify:
  - Run `curl -s "https://sonarcloud.io/api/hotspots/search?projectKey=cemililik_ForgeLM&pullRequest=33&ps=100"`
    after the next CI run. Hotspot count must be 0.
  - The remaining `_LINK_RE` (`\[([^\]]*)\]\(([^)]*)\)`) and
    `_SKIP_HREF_PATTERNS` are still regex-based; confirm none
    of them get newly flagged by S5852.

### G. New test cases — vacuous-test scan (claims to absorb
F-W4-TR-01..F-W4-TR-08)

17 new tests were added across `test_supply_chain_security.py`
(8 new) and `test_check_anchor_resolution.py` (9 new). The
test-rigour bar from the original prompt remains: a test that
only asserts schema shape (not behaviour contract) is vacuous.

#### G.1 — Bandit UNDEFINED test (claims to absorb F-W4-TR-01)

- **F-W4FU-XX-G1** —
  `test_undefined_severity_summary_warning` at
  `test_supply_chain_security.py`. Walk:
  - The fixture omits `issue_severity`. The assertion is
    `"::warning::bandit" in captured` and `"UNDEFINED" in
    captured`. Is the assertion strong enough to pin both:
    (a) the issue is NOT classified as HIGH/MEDIUM, AND
    (b) the summary annotation explicitly mentions UNDEFINED?
  - Could a regression that printed the per-finding line
    `[UNDEFINED/LOW] forgelm/x.py:1 B999 ...` AS A WARNING (rather
    than the summary) pass the test? Yes — both substrings would
    appear. Tighten the assertion?

#### G.2 — Pip-audit UNKNOWN summary test (claims to absorb F-W4-TR-05)

- **F-W4FU-XX-G2** —
  `test_missing_severity_field_summary_warning`. Walk:
  - Fixture: vuln with no `severity` field. Assertion: `"::warning::pip-audit"`
    + `"without parseable severity"`. The substring
    `"without parseable severity"` is unique to the new code path
    — any regression that reverted to silent UNKNOWN would fail.
    ✓

#### G.3 — Pip-audit aliases nested test (claims to absorb F-W4-TR-02)

- **F-W4FU-XX-G3** — `test_aliases_nested_severity_2_6_shape`.
  Fixture: vuln with `aliases: [{id, severity: [{type: "CVSS_V3",
  severity: "HIGH"}]}]`. Asserts exit 1. Walk:
  - Does the fixture actually exercise the 2.6.x fallback (vs the
    top-level `severity` field)? The vuln has no top-level
    `severity` key, so `direct = vuln.get("severity")` is None,
    `isinstance(None, str)` is False, `isinstance(None, list)`
    is False → falls through to aliases. ✓
  - The nested `severity` list carries `severity: "HIGH"` (a
    string field, not the list). The new code's
    `_severity_from_entry` checks `entry.get("severity")` first,
    which returns "HIGH", normalises, returns HIGH. ✓
  - But: does pip-audit 2.6.x actually emit `severity: "HIGH"`
    inside the alias dict, or `severity: [{type, score}]`?
    Re-confirm against pip-audit 2.6.x JSON output captured
    from a real run. If the fixture shape is fictional,
    the test pins a contract that doesn't match reality.

#### G.4 — SBOM serialNumber uniqueness test (claims to absorb F-W4-TR-08)

- **F-W4FU-XX-G4** —
  `TestSbomSerialNumberUniqueness::test_serial_number_changes_between_runs`.
  Walk:
  - Spawns two `tools/generate_sbom.py` subprocesses and asserts
    `sn_a != sn_b`. The SBOM emitter at
    `tools/generate_sbom.py:106` uses `f"urn:uuid:{uuid.uuid4()}"`.
    Confirm `uuid.uuid4()` IS the source of randomness (not a
    seeded UUID5 derived from content); the test would silently
    pass if the emitter swapped to UUID5 of a stable content
    hash AND the content differed by a millisecond timestamp.
  - The 60s subprocess timeout — adequate for a cold-import +
    full SBOM generation? Run locally and confirm.

#### G.5 — Anchor checker tests (claims to absorb F-W4-TR-03/04/06/07)

- **F-W4FU-XX-G5** — The 6 new anchor tests cover apostrophe +
  backtick + ATX-close + tel: + javascript: + image-link skip
  patterns + strict-mode broken-anchor. Walk:
  - `test_atx_closing_hashes_stripped`: asserts
    `_normalise_heading_body("My Title #") == "My Title"` and
    `_normalise_heading_body("My Title  ###  ") == "My Title"`.
    Does the CommonMark §4.2 spec say the closing run must be
    preceded by whitespace? If yes, the helper's behaviour for
    `"foo###"` (no space before closing run) — current code
    strips them anyway. Off-spec but defensible if no project
    doc has unspaced closing runs.
  - `test_strict_mode_exits_one_on_broken_anchor`: planted
    `target.md#nonexistent` should fail strict. Confirm the test
    fails when run against a regression that special-cased
    anchor-not-found differently from file-not-found.
  - `test_image_link_missing_target_flagged` + `_present_target_resolves`:
    both rely on the regex `_LINK_RE.findall("![alt](image.png)")`
    matching the embedded `[alt](image.png)`. Confirm by hand.

### H. Cross-cutting (XPR) checks

#### H.1 — Documentation drift (post-absorption)

- **F-W4FU-XPR-01** — Did every absorption that touched code also
  update the matching doc?
  - `_DOCTOR_SECRET_ENV_NAMES` comment reword for `FORGELM_RESUME_TOKEN`
    → ghost-features-analysis line 604 updated? Yes (per absorption).
    Cross-check the comment text in `_doctor.py:662` against the
    ghost-features description — must agree.
  - Bilingual parity registry growth (4 → 14 new pairs, total
    23) → CHANGELOG line 84 reflects the new tally? (Updated.)
    `localization.md:39` row "Yes" matches reality? Run the
    parity strict mode and confirm 23/23.
  - The closure-plan summary at `:131` says "1374 → 1411 tests
    (+37 net)". After this absorption, the actual count grew to
    1414 (17 new tests minus 14 displaced = 3 additional from
    the absorption, on top of the 1411 frozen at 9a1738a). Does
    the closure plan need a third update, or is the 1411 baseline
    still honest at the wave-4-merge boundary?

#### H.2 — `forgelm verify-audit` cookbook end-to-end test

- **F-W4FU-XPR-02** — The absorption replaced the broken
  `--output-dir / --json` invocation with the shipping syntax.
  Run end-to-end:
  ```bash
  cd /tmp && rm -rf wave4fu-test
  mkdir wave4fu-test && cd wave4fu-test
  FORGELM_AUDIT_SECRET=test FORGELM_OPERATOR=tester \
      python3 -m forgelm.cli --config /path/to/config_template.yaml \
      --dry-run
  # Confirm audit_log.jsonl + audit_log.manifest.json exist.
  python3 -m forgelm.cli verify-audit ./outputs/audit_log.jsonl --require-hmac
  # Must exit 0.
  ```
  Walk: does the deployer-guide cookbook actually produce a
  verifiable chain from `--dry-run`? The dry-run skips training but
  does emit the run-start audit entry; that single-entry chain
  must verify.

#### H.3 — Closure-plan honesty

- **F-W4FU-XPR-03** — `closure-plan-202604300906.md:131` (the
  Wave 4 closure summary) was updated from "6 yeni QMS TR mirror"
  to the more honest "10 yeni QMS TR mirror (4 Faz-23 pair'leri +
  6 mevcut QMS dosyaları için)". Walk:
  - Does the count `4 + 6 = 10` match the actual diff? List the
    10 TR mirrors against `git diff --name-only 9a1738a..HEAD --
    docs/qms/*-tr.md`.
  - Test count `1374 → 1411 (+37 net)` — does the math work?
    The frozen-tree count was 1411 per F-XPR-03 of the original
    test-rigour report. (1374 + 37 = 1411 ✓.) But the post-absorption
    count is 1414 — does the closure plan need updating again,
    or is the absorption's test additions a separate accounting?

#### H.4 — Lint / format equivalence

- **F-W4FU-XPR-04** — The absorptions ran `ruff format` between
  commits. Spot-check whether any auto-format change altered
  *behaviour* vs purely cosmetic. E.g. changes to docstring
  indentation, line splitting that affected an f-string's
  embedded expression. (`tools/check_pip_audit.py` had its
  `_SCORE_TYPE_LABELS` set definition reformatted from 6-line to
  1-line by ruff — confirm that's purely cosmetic.)

#### H.5 — Backwards compatibility (post-absorption)

- **F-W4FU-XPR-05** — Walk every public-API surface touched in
  the diff:
  - `forgelm.cli` — no facade re-exports added or removed by this
    absorption. ✓
  - `tools/check_anchor_resolution.py` — `_HEADING_RE` removed,
    `_parse_atx_heading` added. The `__all__` (none defined) is
    unchanged. Are any third-party callers importing
    `_HEADING_RE` from this module? (Internal `tools/` script;
    not part of the `forgelm` package public surface. Unlikely.)
  - `tools/check_pip_audit.py` — `_normalise_severity` semantics
    changed (CVSS_V3 string now returns UNKNOWN, not "CVSS_V3").
    Any external import? (No `__all__`; private helper.)
  - `tools/check_bandit.py` — `main` signature unchanged but
    behaviour for `{"results": null}` reports flipped from
    silent-pass to fail-loudly. Is that a *user-visible* behaviour
    change that an existing CI consumer would notice? (Yes —
    previously a malformed bandit run passed silently; now it
    fails. The change is correct but worth a CHANGELOG line.)

#### H.6 — gemini-code-assist inline reply audit

- **F-W4FU-XPR-06** — The maintainer replied to two
  gemini-code-assist comments via `gh api .../replies`. Walk:
  - PR #33 thread on `tools/check_bilingual_parity.py:79` — reply
    cites `ffceaf7` and "23/23 OK". Confirm the link resolves
    and the SHA matches the absorption commit.
  - PR #33 thread on `docs/qms/access_control.md:189` — reply
    cites `ffceaf7` and the rewritten jq pipeline. Confirm.

## Ground rules

- **Read the relevant standard before commenting.** The project
  [docs/standards/](../../standards/) directory is the rulebook.
- **Re-evaluate, don't just trust.** An "absorbed" finding in
  the maintainer's commit message is a *claim*. Verify the
  fix against the cited file:line. If the fix is correct, say
  so explicitly in your "Verified absorptions" section. If the
  fix is incomplete or wrong, that's a `F-W4FU-NN` finding.
- **Cite line numbers.** If you cannot point at a line, the
  finding is not actionable.
- **Distinguish original vs newly introduced.** Tag every
  finding with whether it traces back to an original
  (`F-W4-NN` / `F-W4-PS-NN` / `F-W4-TR-NN`) or is *new*
  (introduced by the absorption itself). Use the
  `Trace-back to original finding` field in the deliverable.
- **No phantom severity inflation.** A doc typo is `NIT`. A
  user-visible CLI bug on the happy path is `HIGH` minimum.
- **No re-litigating closed scope.** "Should ForgeLM also do X"
  is not a finding. Stay in the diff.
- **Compliance / privacy claims demand code citations.** Any
  prose change about the HMAC chain key, salt derivation,
  rotation cadence, or audit fail-closed semantics MUST cite
  the actual `forgelm/compliance.py` line where the contract
  lives. If a doc change cannot point at the code that backs
  it, that's a `HIGH` finding.

## Required deliverable structure

Each reviewing agent returns a single Markdown report with this
skeleton, saved as
`docs/analysis/code_reviews/wave4fu-<agent-name>.md`:

```markdown
# Wave 4 Follow-up — <agent-name> Review of `closure/wave4-integration`

> Branch: `closure/wave4-integration` · HEAD `105285f` · Reviewer focus:
> <one-sentence focus>. Re-evaluating absorptions since `9a1738a`.

## Summary
- Verdict: [Block / Conditional / Approve]
- CRITICAL: N · HIGH: N · MEDIUM: N · LOW: N · NIT: N
- One-sentence headline of the highest-severity finding.

## Findings

### F-W4FU-NN · <SEVERITY> · <one-line title>
- **File:** path:line[-line]
- **Trace-back:** F-W4-NN / F-W4-PS-NN / F-W4-TR-NN / NEW
- **What's wrong:** ...
- **User-visible consequence:** ...
- **Suggested fix:** ```code```
- **Regression test:** ```python ...```

(repeat per finding)

## Verified absorptions

For each CRITICAL / HIGH from the four original reports + the
2 inline PR comments + 4 SonarCloud items (3 code-smells +
1 hotspot), state:

- **F-<original-id> [verified]** — fix lands at <file:line>; the
  contract <X> now holds. Walked: <what you walked>.
- **F-<original-id> [partial]** — fix addresses <X> but misses
  <Y>; new finding F-W4FU-NN tracks it.
- **F-<original-id> [regressed]** — fix introduces <Z>; new
  finding F-W4FU-NN tracks it.

## What this report deliberately did not cover

(scope notes, deferred items, out-of-PR areas)

## Merge recommendation

(Block / Conditional / Approve, with the headline reasons)
```

## How to launch

Spawn 4 parallel sub-agents (you may use any harness that supports
parallel workers; the original review used Claude `Agent` calls
in a single message). Pass each agent the SAME prompt, with one
extra line at the top stating its agent name + focus:

1. **Code-correctness agent.** Focus areas: §C.1, C.2, D (all),
   E (all), F (all), H.2, H.4, H.5. Walk the pip-audit / bandit /
   anchor-checker rewrites for behaviour invariance.
2. **Privacy / security agent.** Focus areas: §B (all), C (all),
   D.4, E.2, H.5. Privacy bar reigns — any prose change about
   HMAC key derivation, salt, rotation cadence, or fail-closed
   audit semantics must cite the actual code.
3. **Standards / compliance agent.** Focus areas: §A (all), B (all),
   H.1, H.3, H.6. Cite [docs/standards/](../../standards/)
   extensively. The §3 tally arithmetic is the headline check.
4. **Test-rigour agent.** Focus areas: §D (all), E (all), F (all),
   G (all), H.4. Vacuous-test bar reigns — every new test must
   pin a behaviour contract, not a schema shape.

Agents run independently. Maintainer absorbs in a single round
(per the established Wave 3 / Wave 4 cadence: even out-of-scope
real bugs are fixed in the same round, not deferred).

---

*Frozen at `105285f` on 2026-05-06.* *If any reviewer finds the
prompt itself ambiguous, surface it as a `F-W4FU-PROMPT-NN`
finding before merging — the prompt itself is part of the audit
trail.*

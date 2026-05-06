# Wave 5 — Multi-Agent Code Review Prompt (pre-merge audit)

> **Use this prompt verbatim** to launch the multi-agent review on
> the Wave 5 PR. The prompt is self-contained: each reviewing agent
> can pick it up cold without context from prior conversations.
>
> Wave 5 is the **Faz 30 full sweep** — the final pre-release
> documentation + tooling closure. No prior Wave 5 absorption rounds
> yet — this is the FIRST review pass. Wave 5 also closes the
> remaining Tier 1 ghost-feature drift items, ships the
> `check_cli_help_consistency.py` guard with strict CI wire-up, and
> drives the anchor-checker baseline to zero with strict CI wire-up.

---

## Repo & branch under review

- **Repo:** `cemililik/ForgeLM`
- **PR:** **TBD** (`closure/wave5-integration` → `development`).
  Open with `gh pr create --base development --head closure/wave5-integration`.
- **Frozen HEAD at prompt freeze:** `6448c2d`
- **Diff vs `development`:** ~122 files, ~9272 insertions, ~654
  deletions across 7 commits.
- **What it consolidates (closure-plan §10 Faz 30 Tasks A through
  O):** 50 new doc-triplet files (reference + guide + usermanual
  EN+TR for 11 v0.5.x subcommands + library API + performance);
  one new CI tool (`tools/check_cli_help_consistency.py` with 15
  pinned tests); two CI gates flipped from advisory to `--strict`
  (anchor resolution + cli-help consistency); 5 site/* HTML pages
  brought to v0.5.5 final state; README + CONTRIBUTING + CLAUDE.md
  + roadmap + 10 standards files final pass; `_meta.yaml`
  navigation +8 pages; `pyproject.toml` version bump
  `0.5.1rc1` → `0.5.5`; closure-plan honesty pass on Tasks K + L
  + M dispositions.

## Wave 5 commits in scope

| SHA | Title | Findings absorbed |
|---|---|---|
| `e18baa0` | wave-5-tier-1: clear remaining ghost-feature drift items + open Wave 5 | GH-011 / GH-016 / GH-018 / GH-020 |
| `2a32842` | wave-5-task-a: 50 new feature doc-triplet files | Task A reference (11) + guide (5) + usermanual (9) × EN+TR |
| `c7bedc9` | wave-5-task-j: tools/check_cli_help_consistency.py — CLI / docs drift guard | Task J new tool + tests + advisory CI |
| `fbb082d` | wave-5-tasks-jn-cleanup: drive CLI + anchor drift baselines to 0; flip both gates to --strict | Tasks J + N follow-up cleanup |
| `2834d62` | wave-5-tasks-bc: _meta.yaml +8 page entries for new Wave 5 usermanual pages | Tasks B + C (rebuild verified) |
| `4610dc6` | wave-5-tasks-defg: site v0.5.5 + README/CONTRIBUTING/CLAUDE/roadmap/standards final pass | Tasks D + E + F + G |
| `6448c2d` | wave-5-tasks-hiklm: finalise Wave 5 closure-plan disposition; Faz 30 complete | Tasks H + I + K + L + M (incl. honest Task K disposition) |

## What ForgeLM is (60 seconds)

A **config-driven, enterprise-grade LLM fine-tuning toolkit** —
YAML in, fine-tuned model + compliance artifacts out. Built for
CI/CD pipelines, not notebooks. Six alignment paradigms
(SFT/DPO/SimPO/KTO/ORPO/GRPO), integrated safety evaluation
(Llama Guard), EU AI Act compliance artefacts (Articles 9–17 +
Annex IV), append-only audit log, opt-in human approval gate,
auto-revert on quality regression, GDPR Article 15 + 17 subject
rights tooling, ISO 27001 / SOC 2 alignment evidence
(Wave 4 / Faz 22 + 23). Wave 5 closes the v0.5.5 documentation
sweep + ships two new strict CI gates. Read
[docs/product_strategy.md](../../product_strategy.md) for the
fuller background.

Project rulebook lives under [docs/standards/](../../standards/) —
read [coding.md](../../standards/coding.md),
[error-handling.md](../../standards/error-handling.md),
[testing.md](../../standards/testing.md),
[logging-observability.md](../../standards/logging-observability.md),
[regex.md](../../standards/regex.md),
[localization.md](../../standards/localization.md),
[documentation.md](../../standards/documentation.md), and
[code-review.md](../../standards/code-review.md) before
commenting. Project-wide guidance for AI agents is in the root
`CLAUDE.md`.

## Critical framing for this review (don't skip)

**Wave 5 is documentation-heavy + low new-code.** The bulk of the
diff is 50 new markdown doc files + 1 new tool + minor config /
flag-table corrections. Treat the bar accordingly:

- **CLI examples must run.** Every `forgelm <subcommand> ...`
  invocation in any new doc MUST match the live parser surface
  (`forgelm <subcommand> --help`). The new
  `tools/check_cli_help_consistency.py --strict` gate enforces
  this; if the gate is green at HEAD `6448c2d` (449/449 OK) but
  you find any drift in your walk, that is a finding against
  the gate (it has a false-negative).
- **Bilingual parity strict** runs at 39/39 OK on HEAD. Any new
  EN doc must mirror its TR counterpart's H2/H3/H4 spine. Any
  drift you find is a finding against the parity tool.
- **Anchor strict** runs at 264/264 OK on HEAD. Any broken
  Markdown anchor / relative-link reference is a finding against
  the anchor tool.
- **Site claims strict** is green: site cites v0.5.5, pyproject
  is `0.5.5`, the 5 quickstart templates + 16 GPU profiles are
  cross-checked against shipped code. Drift here is CRITICAL —
  the site is the marketing surface.
- **Alignment, not certified.** ISO/SOC 2 framing must say
  "aligned" / "alignment evidence", never "certified" /
  "compliant". This carried over from Wave 4 / D-22-01;
  re-verify Wave 5's site/* and new doc files honour it.

## What we want from this round

**Goal:** decide whether `closure/wave5-integration` at `6448c2d`
is mergeable to `development` (the v0.5.5 release-prep PR).

Block on real defects; do not gate on style nits or hypothetical
futures. The five gates that ALREADY run strict on HEAD give you a
"shipped contract" baseline — if a guard says clean, dispute the
guard, not the doc.

Be concrete. Every finding must include:

1. **Severity tag** — `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` / `NIT`.
2. **Finding ID** — `F-W5-NN` (e.g. `F-W5-01`, `F-W5-12`).
3. **File:line citation** — `docs/reference/verify_audit.md:42` or
   a short range `:42-55`.
4. **One-paragraph reasoning** — what is wrong, what is the
   user-visible consequence, why it qualifies for that severity.
5. **Suggested fix** — a code or text snippet, not a vague
   direction.
6. **Test or guard that would have caught it** — name the
   `tools/check_*.py` rule + assertion shape, OR the
   `tests/test_*.py` test + a stub of the assertion. For
   doc-only findings, name the guard.

Severity bar (unchanged from Wave 4 — same calibration):

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
  migration path. Blocks merge.
- `MEDIUM` — logic bug in an off-the-happy-path branch,
  observability gap, or design-doc statement that contradicts
  shipped code. Should be fixed before merge but the call is
  the maintainer's.
- `LOW` — defensive-coding improvement, minor inconsistency,
  missing edge-case test that would not have changed PR
  direction.
- `NIT` — naming, line wrap, comment phrasing. Note in passing
  only; do not stack these.

## Areas to scrutinise

These are the surfaces most likely to harbour real issues.

### A. The 50 new doc-triplet files (Task A, commit `2a32842`)

Inventory:

- 11 reference docs `docs/reference/<cmd>_subcommand.md` + TR
  (verify_audit, verify_annex_iv, verify_gguf, purge,
  reverse_pii, approve, approvals, doctor, cache_subcommands,
  safety_eval, library_api_reference).
- 5 guide docs `docs/guides/<topic>.md` + TR (getting-started,
  air_gap_deployment, human_approval_gate, library_api,
  performance).
- 9 usermanual pages `docs/usermanuals/{en,tr}/<section>/<page>.md`
  (compliance/verify-audit, compliance/annex-iv,
  compliance/gdpr-erasure, compliance/human-approval-gate,
  deployment/verify-gguf, operations/iso-soc2-deployer,
  operations/supply-chain, reference/library-api,
  reference/performance).

For each new file, walk:

#### A.1 — CLI surface accuracy

- **F-W5-XX-A1** — Run `forgelm <subcommand> --help` for the
  command the doc covers. Walk the doc's flag list, exit-code
  table, and example invocations. Confirm:
  - Every `--flag` cited exists in the parser.
  - Every flag's choices `{a,b,c}` match the parser.
  - Positional arguments match (e.g. `approve <run_id>` is
    positional, NOT `--run-id` — that contract was reaffirmed
    in Wave 4 round 1).
  - Exit codes cited match `forgelm/cli/subcommands/_<cmd>.py`
    return values + the public 0/1/2/3/4 contract per
    `docs/reference/exit-codes.md`.
- The new tool `tools/check_cli_help_consistency.py --strict`
  runs at 449/449 OK on HEAD. If you find a flag drift
  the tool missed, tag it as a tool-coverage gap (the tool is
  the canonical guard for this class — false negatives there
  are MEDIUM minimum).

#### A.2 — Audit events emitted

- **F-W5-XX-A2** — Each reference doc lists `audit_log.jsonl`
  events the command emits. Cross-check against
  `docs/reference/audit_event_catalog.md`. If a doc names
  an event that isn't in the catalog (or vice versa), that's
  drift — HIGH if the event is real but the catalog is missing
  it, MEDIUM if the doc names a fictional event.

#### A.3 — Symbol citations

- **F-W5-XX-A3** — Each new doc cites `forgelm.<symbol>` /
  `forgelm.cli.subcommands._<cmd>.<symbol>` for code references.
  These must resolve in the live package. Spot-check 3-5 random
  citations per doc; an `ImportError` on any cite is a HIGH
  finding (Faz 26 stable-symbol-cite policy).

#### A.4 — Bilingual parity (post-strict)

- **F-W5-XX-A4** — The parity guard runs at 39/39 OK at HEAD.
  If you find an EN/TR drift the guard missed (e.g. a new H4
  in EN absent from TR, or vice versa), tag it as a
  parity-tool gap (HIGH — Wave 3 / Faz 24 explicitly committed
  to "every EN H2/H3/H4 has a TR counterpart").

### B. The new tool `tools/check_cli_help_consistency.py` (Task J, commit `c7bedc9`)

#### B.1 — Tool correctness

- **F-W5-XX-B1** — The tool ships in 749 LOC + 15 pinned tests
  (`tests/test_check_cli_help_consistency.py`). Walk:
  - Does the parser-surface discovery (Option A —
    subprocess-based) handle missing subcommands gracefully?
  - The synopsis-line skip heuristic (`_is_synopsis_line()`)
    skips lines containing `[` to avoid false positives on
    argparse-style USAGE lines. What about ATX heading lines
    that legitimately contain `[term](link)` markdown links?
    Verify this isn't a false-negative.
  - The forward-reference framing heuristic tolerates `planned`
    / `roadmap` / `future` / `not in v0.5.5` / `(planned)`
    within ±3 lines. Could an attacker craft a doc that
    smuggles real drift past the gate by adding the framing
    text adjacent to a real bug? Test-rigour bar.
  - The `Wrong:` / `Don't:` / `Anti-pattern:` / `Legacy:` /
    `Yanlış:` skip patterns for code-block context — does the
    tool correctly resume scanning after the wrong-block ends?
- The 15 tests pin: real syntax green, each historical drift
  class (verify-audit `--output-dir/--json`, benchmark
  `--model`, deploy `--target kserve`, chat `--top-p`),
  forward-ref tolerance, wrong-block tolerance, --quiet,
  parser-discovery sanity. Walk for vacuous-test bar:
  do the assertions actually pin the contract or shape only?

#### B.2 — Tool design

- **F-W5-XX-B2** — Cognitive complexity: the prompt brief
  required `< 15` per function (Sonar S3776). Walk
  `_extract_invocations`, `main`, `_check_drift_in_doc` and
  similar — do any exceed?
- The tool spawns subprocesses for parser discovery. On a
  fresh checkout (CI-ish env), is `python3 -m forgelm.cli` on
  PATH? The tool documents this as a precondition; verify
  it gracefully fails-loud if missing.

#### B.3 — Strict CI flip

- **F-W5-XX-B3** — `.github/workflows/ci.yml` flipped the gate
  from advisory `continue-on-error: true` to
  `python3 tools/check_cli_help_consistency.py --strict` in
  commit `fbb082d`. Walk the ci.yml diff: was anything else
  changed alongside? Is the strict step in the right job
  (validate)? Position relative to bilingual-parity step?

### C. Anchor checker --strict CI flip (Task N, commit `fbb082d`)

#### C.1 — Drift baseline cleanup

- **F-W5-XX-C1** — The cleanup commit touched 35 files,
  +180 / −128 LOC. Walk the diff: every change should be a
  pure link-target / slug-case update, with no semantic
  rephrasing. Especially scrutinise:
  - The `docs/usermanuals/tr/data/pii-ml.md` Turkish-letter
    slug fix (`{#dil-secimi}` removal + Unicode-preserving
    canonical slugs `#dil-seçimi`). Is the GFM behaviour
    actually preserving Unicode letters? Verify by computing
    the slug via the tool's `_slugify_heading` helper.
  - The `forgelm/data_audit.py` → `forgelm/data_audit/` package
    references. Is the path actually a directory now (Faz 14
    split landed)? Verify `ls forgelm/data_audit/`.
  - The `forgelm/cli.py` → `forgelm/cli/` references. Same.
  - The `documentation.md` self-illustrative
    `[Other doc 1](other.md)` rephrasing — is the pedagogical
    intent preserved or did the rewrite break the surrounding
    prose flow?

#### C.2 — Strict CI flip

- **F-W5-XX-C2** — The new step `Markdown anchor resolution
  check (strict)` was added to `.github/workflows/ci.yml`.
  Walk: position in the validate job (between bilingual-parity
  + cli-help-consistency)? Comment style consistent with
  surrounding steps? `--strict` flag passed correctly?

### D. Site v0.5.5 finalisation (Task D, commit `4610dc6`)

#### D.1 — Per-page accuracy

- **F-W5-XX-D1** — Walk each touched HTML page:
  - `site/index.html` — hero badge `v0.5.5`, stat tile
    `1428 / Tests passing on every commit`, capabilities
    grid +3 cards (Library API, ISO/SOC 2, GDPR rights).
    Cross-check the test count against
    `python3 -m pytest --collect-only -q | tail -3`.
  - `site/features.html` — +6 Enterprise/MLOps cards + new
    "Compliance & GDPR tooling" group. Does every claim cite
    a shipped subcommand?
  - `site/compliance.html` — Article 14 / GDPR / "Aligned, not
    certified" sections. Does the alignment-vs-certified
    framing hold throughout? No `compliant` / `certified` slip?
  - `site/quickstart.html` — `pip install forgelm==0.5.5`
    install line + `forgelm doctor` + verify-audit + approvals
    + approve flow. Does each command actually work as cited?
  - `site/privacy.html` — install line + GDPR Art. 15/17
    section. Cross-link target valid?
- The `tools/check_site_claims.py --strict` gate runs green at
  HEAD. If you find drift between site copy and shipped reality
  the gate missed, that's a tool-coverage gap (HIGH —
  site/* is the marketing surface and the gate is its only
  guard).

#### D.2 — i18n

- **F-W5-XX-D2** — `site/js/translations.js` got 6-language
  bumps for hero badge + install commands; new EN+TR keys for
  home / features / compliance / privacy. DE/FR/ES/ZH new
  keys fall back to EN per `i18n.js`. Walk:
  - Are the new EN+TR keys structurally consistent (same
    nested key paths)?
  - Does the i18n key resolution actually fall back to EN
    when the key is missing for DE/FR/ES/ZH? Spot-check by
    reading `site/js/i18n.js` resolution logic.

### E. Top-level docs final pass (Task E, commit `4610dc6`)

#### E.1 — README.md

- **F-W5-XX-E1** — Feature list + stat block + CI guard list.
  Cross-check the feature list claims against shipped
  subcommands via `forgelm --help`. Stat block: was 26 test
  modules → 72 (matches `git ls-files tests/ | wc -l`); was
  ~800 tests → 1428 (matches collected count).

#### E.2 — CONTRIBUTING.md

- **F-W5-XX-E2** — Validation gauntlet command at the bottom.
  Does it list the four (or six?) actual guards CI runs? If
  the user runs the cited command locally, does it match
  what CI does?

#### E.3 — CLAUDE.md

- **F-W5-XX-E3** — Repository structure section. Walk:
  - `forgelm.cli/` package post-Faz-15 split present?
  - `forgelm.data_audit/` package post-Faz-14 split present?
  - `forgelm.compliance` symbol set referenced?
  - Skill listing matches `ls .claude/skills/`?

### F. Standards final pass (Task G, commit `4610dc6`)

10 standards files touched. Walk:

#### F.1 — `docs/standards/README.md`

- **F-W5-XX-F1** — Index complete? All 10 files listed?

#### F.2 — `docs/standards/architecture.md`

- **F-W5-XX-F2** — Package splits (`data_audit/`, `cli/`)
  reflected? "Module cohesion ~1000 line ceiling" rule
  intact?

#### F.3 — `docs/standards/documentation.md`

- **F-W5-XX-F3** — Bilingual H3/H4 parity rule formalised?
  New CI guards (`check_anchor_resolution`,
  `check_cli_help_consistency`) added to the doc-related
  guard list?

#### F.4 — `docs/standards/localization.md`

- **F-W5-XX-F4** — EN+TR mandatory + DE/FR/ES/ZH deferred
  policy formalised? QMS row says "Yes" (post-Wave-4 sweep)?
  Wave 5 doesn't expand the policy further; just verify.

#### F.5 — `docs/standards/release.md`

- **F-W5-XX-F5** — v0.5.5 release sequence documented?
  cross-OS matrix + pre-commit + cut-release skill all
  cited?

#### F.6 — `docs/standards/testing.md`

- **F-W5-XX-F6** — Test count refreshed to ~72 modules /
  1428 tests? cov-fail-under=40 still cited?

#### F.7 — `docs/standards/regex.md`

- **F-W5-XX-F7** — The 8 hard rules from Phase 11/11.5/12
  cycle intact?

### G. Roadmap final state (Task F, commit `4610dc6`)

#### G.1 — `docs/roadmap.md` + `-tr.md`

- **F-W5-XX-G1** — Phase 12.6 closure cycle ✅ Done? v0.5.5
  next-up? Phase 13 (Pro CLI) still planned?

#### G.2 — `docs/roadmap/releases.md`

- **F-W5-XX-G2** — v0.5.5 row added with placeholder content
  for release-day fill-in?

#### G.3 — `docs/roadmap/risks-and-decisions.md`

- **F-W5-XX-G3** — Wave 5 cycle decisions appended (Path B
  over Path A; bilingual policy; cli-help baseline cleanup;
  anchor strict CI flip)?

#### G.4 — `docs/roadmap/phase-12-6-closure-cycle.md` (NEW)

- **F-W5-XX-G4** — Summary listing all 38 fazlar with
  wave-merge SHA references? Honest closure of Faz 30 Tasks
  K + L + M dispositions?

### H. Tier 1 ghost-feature drift (commit `e18baa0`)

#### H.1 — GH-011 / GH-016 / GH-018 / GH-020

- **F-W5-XX-H1** — Each GH-NN item's fix verified against
  shipped parser surface. Walk:
  - GH-011 — `benchmarks.md` (EN+TR) → `--benchmark-only` flag
    form. Verify by running `python3 -m forgelm.cli --help`
    + grepping `benchmark`.
  - GH-016 — `--export-bundle` → `--compliance-export` rename
    in 3 QMS / roadmap files. Verify `forgelm --compliance-export
    --help` and that the docs actually invoke `--compliance-export`,
    not the legacy `--export-bundle`.
  - GH-018 — `kserve` / `triton` removal from
    `deploy-targets.md` (EN+TR). Verify `forgelm deploy
    --target` choices match `{ollama,vllm,tgi,hf-endpoints}`
    only.
  - GH-020 — Ingest flag drift in `ingestion.md` +
    `pii-masking.md` + `language-detection.md` (EN+TR).
    Verify `forgelm ingest --help` shows
    `{sliding,paragraph,markdown}` strategy choices,
    `--chunk-tokens` (NOT `--max-tokens`), no
    `--language` / `--include` / `--exclude` / `--format`
    / `--pii-locale` flags.

### I. pyproject.toml version bump

- **F-W5-XX-I1** — `pyproject.toml` bumped `0.5.1rc1` → `0.5.5`
  in commit `4610dc6` (Task D). The closure-plan said Faz 33
  (release) handles version bump; Wave 5 brought it forward
  because `check_site_claims.py --strict` enforces
  site/code version match (site cites v0.5.5).
  Is this acceptable, or should the release bump have been
  deferred? Walk:
  - Does `from forgelm import __version__` resolve to `0.5.5`?
  - Does the `pip install forgelm==0.5.5` line actually
    work as written if v0.5.5 is not yet on PyPI? (No — but
    this is the install line for **after** the release tag
    is published. Faz 33 will tag + publish; users will
    have v0.5.5 on PyPI within minutes.)

### J. Cross-cutting (XPR) checks

#### J.1 — Five strict guards green

- **F-W5-XPR-01** — Run all five strict gates locally and
  confirm each exits 0:
  - `python3 tools/check_bilingual_parity.py --strict` (39/39).
  - `python3 tools/check_anchor_resolution.py --strict` (264/264).
  - `python3 tools/check_cli_help_consistency.py --strict` (449/449).
  - `python3 tools/check_site_claims.py --strict`.
  - `python3 tools/check_field_descriptions.py --strict
    forgelm/config.py`.

#### J.2 — Pytest baseline

- **F-W5-XPR-02** — `python3 -m pytest --no-cov -q` exits 0.
  Test count: 1428 passed / 14 skipped on HEAD. Should grow
  by 15 vs Wave 4 final (1413; the 15 new tests are
  `tests/test_check_cli_help_consistency.py`).

#### J.3 — Dry-run

- **F-W5-XPR-03** — `forgelm --config config_template.yaml
  --dry-run` exits 0 cleanly.

#### J.4 — `closure-plan-202604300906.md` honesty

- **F-W5-XPR-04** — Walk the closure plan §2 status table.
  Does it correctly reflect:
  - Wave 4 ✅ Done (PR #33 merged via `01e40ba`).
  - Wave 5 🔄 in progress on `closure/wave5-integration`.
  - All 38 fazlar accounted for.
  - Faz 33 POST-WAVE.

#### J.5 — Ghost feature analysis residual claims

- **F-W5-XPR-05** — `docs/analysis/code_reviews/
  ghost-features-analysis-20260502.md` originally identified
  28 ghost entries. Wave 4 + Wave 5 closed all of them via
  doc-rename (Tier 1) or shipped subcommand (Tier 2,
  Faz 34-38). Walk: are there any GH-NN items still open
  that the maintainer's closure summary marks as resolved?

## Ground rules

- **Read the relevant standard before commenting.** The project
  [docs/standards/](../../standards/) directory is the rulebook.
- **Re-evaluate, don't just trust.** Wave 5's strict guards run
  green at HEAD. If you find drift, prove it with a one-line
  reproduction (e.g. `python3 -m forgelm.cli <sub> --help` output
  vs the doc's claim).
- **Cite line numbers.** If you cannot point at a line, the
  finding is not actionable.
- **No phantom severity inflation.** A doc typo is `NIT`. A
  user-visible CLI bug on the happy path is `HIGH` minimum.
- **No re-litigating closed scope.** "Should ForgeLM also do X"
  is not a finding. Stay in the diff.
- **Five guards before merge.** If any of the five strict gates
  is red on HEAD, that is a CRITICAL block-merge finding
  regardless of any other surface.

## Required deliverable structure

Each reviewing agent returns a single Markdown report saved as
`docs/analysis/code_reviews/wave5-<agent-name>.md`:

```markdown
# Wave 5 — <agent-name> Review of `closure/wave5-integration`

> Branch: `closure/wave5-integration` · HEAD `6448c2d` · Reviewer focus:
> <one-sentence focus>.

## Summary
- Verdict: [Block / Conditional / Approve]
- CRITICAL: N · HIGH: N · MEDIUM: N · LOW: N · NIT: N
- One-sentence headline of the highest-severity finding.

## Findings

### F-W5-NN · <SEVERITY> · <one-line title>
- **File:** path:line[-line]
- **What's wrong:** ...
- **User-visible consequence:** ...
- **Suggested fix:** ```code```
- **Regression test / guard:** ```python ...```

(repeat per finding)

## Verified absorptions

For each closure-plan §10 Faz 30 Task that this PR claims to close,
state:

- **Task A [verified]** — 50 new doc files ship; CLI / parity /
  anchor strict gates green. Walked: <what you walked>.
- **Task J [verified]** — new tool ships with 15 tests + strict
  CI flip in commit fbb082d.
- (... per task)

## What this report deliberately did not cover

(scope notes, deferred items, out-of-PR areas)

## Merge recommendation

(Block / Conditional / Approve, with the headline reasons)
```

## How to launch

Spawn 4 parallel sub-agents (you may use any harness that
supports parallel workers; the prior wave reviews used Claude
`Agent` calls in a single message). Pass each agent the SAME
prompt, with one extra line at the top stating its agent name +
focus:

1. **Code-correctness agent.** Focus areas: §B (new tool),
   §C (anchor cleanup diff), §H (Tier 1 drift), §I (version bump),
   §J.1, §J.2, §J.3.
2. **Privacy / security agent.** Focus areas: §A.1 (CLI surface
   accuracy on the GDPR / approval / verify-* subcommands), §A.2
   (audit events emitted), §A.3 (symbol citations), §D
   (alignment-not-certified framing on site/*).
3. **Standards / compliance agent.** Focus areas: §A.4 (parity),
   §E (top-level docs), §F (10 standards files), §G (roadmap),
   §J.4 (closure plan honesty), §J.5 (ghost feature residual
   claims). Cite [docs/standards/](../../standards/) extensively.
4. **Test-rigour agent.** Focus areas: §B.1 (the 15 new tests),
   §B.2 (tool design), §C.1 (cleanup-diff drift), §J.2 (pytest
   baseline), vacuous-test scan of the 15 new tests.

Agents run independently. Maintainer absorbs in a single round
(per the established Wave 3-4 cadence: even out-of-scope real
bugs are fixed in the same round, not deferred).

---

*Frozen at `6448c2d` on 2026-05-06.* *If any reviewer finds the
prompt itself ambiguous, surface it as a `F-W5-PROMPT-NN`
finding before merging — the prompt itself is part of the audit
trail.*

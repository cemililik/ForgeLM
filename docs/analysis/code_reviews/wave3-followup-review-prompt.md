# Wave 3 Follow-up — Multi-Agent Code Review Prompt (post-absorption)

> **Use this prompt verbatim** to launch the multi-agent review on the
> 5 absorption commits that landed on PR #31 after the original
> 4-agent review completed.  The prompt is self-contained: each
> reviewing agent can pick it up cold without context from the prior
> review round.
>
> The original Wave 3 review (per
> [`wave3-review-prompt.md`](wave3-review-prompt.md), HEAD `61d74fa`)
> produced 4 reports under `docs/analysis/code_reviews/wave3-*.md`.
> The maintainer absorbed those reports plus inline PR-comment
> findings (CodeRabbit / gemini-code-assist) plus SonarCloud quality
> gate failures across **5 commits**.  This second-pass review asks:
> *did the absorption correctly address the original findings, and
> did the absorption itself introduce any new defects?*

---

## Repo & branch under review

- **Repo:** `cemililik/ForgeLM`
- **PR:** [#31](https://github.com/cemililik/ForgeLM/pull/31)
  (`closure/wave3-integration` → `development`)
- **HEAD SHA at prompt freeze:** `7adecb1`
- **Pre-absorption SHA (the snapshot the original 4-agent review
  read):** `95e2bf8` (before that, `61d74fa`)
- **Absorption-only diff range:** `git diff 95e2bf8..7adecb1`
  — 24 files changed, ~1051 insertions, ~265 deletions.
- **5 absorption commits in scope** (oldest → newest):

  | SHA       | Title                                                                     | Findings absorbed |
  |-----------|---------------------------------------------------------------------------|------|
  | `5491572` | absorb 4-agent review + 6 inline PR comment findings                      | F-W3-01..14, F-W3-PS-01..09, F-W3S-01..09, F-W3T-01..12 + 6 inline |
  | `6ba93be` | absorb 3 SonarCloud + 1 hotspot findings on PR #31                        | python:S1172, S2201, S3776 + dos hotspot |
  | `730a015` | close 2 remaining SonarCloud hotspots on PR #31                           | python:S5852 (final), S5443 |
  | `cd66c54` | close gemini-code-assist fence-length finding                             | CommonMark §4.5 fence length |
  | `7adecb1` | warn on implicit --output-dir + --salt-source; drop unreachable fallback  | implicit-output-dir cross-tool correlation risk |

## What ForgeLM is (60 seconds)

A **config-driven, enterprise-grade LLM fine-tuning toolkit** — YAML
in, fine-tuned model + compliance artifacts out.  Built for CI/CD
pipelines, not notebooks.  Six alignment paradigms
(SFT/DPO/SimPO/KTO/ORPO/GRPO), integrated safety evaluation
(Llama Guard), EU AI Act compliance artefacts (Articles 9–17 + Annex
IV), append-only audit log, opt-in human approval gate, auto-revert
on quality regression, GDPR Article 15 + 17 subject rights tooling.
Read [docs/product_strategy.md](../../product_strategy.md) for the
fuller background.

Project rulebook lives under [docs/standards/](../../standards/) — read
[coding.md](../../standards/coding.md),
[error-handling.md](../../standards/error-handling.md),
[testing.md](../../standards/testing.md),
[logging-observability.md](../../standards/logging-observability.md),
[regex.md](../../standards/regex.md),
[localization.md](../../standards/localization.md), and
[code-review.md](../../standards/code-review.md) before commenting.
Project-wide guidance for AI agents is in the root `CLAUDE.md`.

The original 4 review reports under
[`docs/analysis/code_reviews/`](.) document the prior bar:

- [`wave3-code-correctness.md`](wave3-code-correctness.md) — 15 findings.
- [`wave3-privacy-security.md`](wave3-privacy-security.md) — 14 findings + 2 cross-phase.
- [`wave3-standards.md`](wave3-standards.md) — 9 findings + 7 cross-phase passes.
- [`wave3-test-rigor.md`](wave3-test-rigor.md) — 14 findings + 5 cross-phase notes.

The maintainer's absorption summary (per-finding disposition) is at
[PR #31 issuecomment-4380828720](https://github.com/cemililik/ForgeLM/pull/31#issuecomment-4380828720).

## What this round is for

**Goal:** decide whether `closure/wave3-integration` at `7adecb1` is
mergeable to `development`, given the absorptions claim to have
addressed the original 4-agent review.

**Question shape:** the previous review framed defects in code shipped
*before* absorption.  This review asks two complementary questions:

1. **Did the absorptions correctly fix the original findings?**
   Walk every CRITICAL / HIGH from the 4 prior reports.  For each,
   verify the claimed fix lands at the cited file:line and actually
   addresses the original concern (not "a fix that compiles" but
   "the contract the original finding asked about now holds").
2. **Did the absorptions themselves introduce defects?**  The diff
   touches 24 files; the largest absorption (`5491572`) rewrote
   most of `forgelm/cli/subcommands/_reverse_pii.py`.  Treat the
   rewrite as new code — same severity bar as the original review.

Be concrete.  Every finding must include:

1. **Severity tag** — `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` / `NIT`.
2. **Finding ID** — `F-W3FU-NN` (e.g. `F-W3FU-01`, `F-W3FU-12`).
3. **File:line citation** — `forgelm/cli/subcommands/_reverse_pii.py:524`
   or a short range `:520-545`.
4. **One-paragraph reasoning** — what is wrong, what is the user-visible
   consequence, and why it qualifies for that severity tier.
5. **Suggested fix** — a code or text snippet, not a vague direction.
6. **Test that would have caught it** — name the test file + a stub
   of the assertion.
7. **Trace-back to original finding (if any)** — when re-evaluating
   a claimed absorption, cite the original finding ID
   (e.g. F-W3-03, F-W3-PS-01, F-W3S-01, F-W3T-01) so the maintainer
   can compare against the pre-absorption code.

Severity bar (unchanged from the original prompt — same calibration):

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

These are the surfaces most likely to harbour real issues *post-absorption*.

### A. `_reverse_pii.py` — heaviest rewrite (`5491572` + `6ba93be` + `7adecb1`)

The dispatcher grew from 384 lines to ~635 lines.  Walk every new
helper for soundness, and every removed branch for missed callers.

#### A.1 — Audit fail-closed semantics (claims to absorb F-W3-01 + F-W3-PS-02 + F-W3S-01)

- **File:** `forgelm/cli/subcommands/_reverse_pii.py:_maybe_audit_logger`
- The new policy: `ConfigError` → WARNING + `None` (best-effort);
  every other exception (`OSError`, `ValueError`) → fail-closed
  with `EXIT_TRAINING_ERROR`.  Walk:
  - Is the `(OSError, ValueError)` catch tuple complete?  Could
    `AuditLogger.__init__` raise something not in the tuple
    (`PermissionError` is `OSError` subclass; `RuntimeError`,
    `KeyError` from a corrupt manifest)?
  - The `explicit=` kwarg distinguishes operator-supplied vs
    inferred audit dirs but the failure path treats both the same
    (`fail closed`).  Is that consistent with the docstring's
    "explicit values fail loudly when unwritable rather than
    silently dropping" framing?  Or should the implicit default
    fall back to a different writable location instead of failing?
  - The two `try / except Exception as audit_exc: _output_error_and_exit`
    wrappers around `_emit_audit_event` (success path + failure
    path) — does the failure path's nested try/except correctly
    preserve the original exception's audit semantics?

#### A.2 — Salted audit hash + cross-tool correlation (claims to absorb F-W3-PS-01 + F-W3-PS-09)

- **File:** `_reverse_pii.py:_hash_for_audit`,
  `_resolve_query_form`, `_run_reverse_pii_cmd`
- The hash is now `SHA256(salt + raw_query)` using the same
  per-output-dir salt purge uses for `target_id`.  Walk:
  - The `salt: Optional[bytes]` signature has a `None` legacy path
    (`hashlib.sha256(raw).hexdigest()` unsalted).  Can any caller
    in production reach the `None` branch, or is it dead code?
    If dead, drop it; if reachable, document why an unsalted hash
    is acceptable on that path.
  - `_resolve_query_form` ALWAYS calls `_resolve_salt(output_dir)`
    even in plaintext mode (because the audit hash needs a salt).
    Side effect: every reverse-pii invocation creates
    `.forgelm_audit_salt` in the resolved `output_dir`.  Is that
    documented?  Is it the same semantic as `forgelm purge` (does
    purge also unconditionally create the salt file on first run)?
  - The new `salt_source_label` field is recorded in the audit
    event.  In plaintext mode it gets the `_resolve_salt` return
    value (`per_dir` or `env_var`) — i.e. the audit chain says
    `"scan_mode": "plaintext", "salt_source": "per_dir"`.  Is
    that label semantically right (the salt is irrelevant to the
    plaintext scan; it's only used for the audit hash) or
    misleading?

#### A.3 — `--type literal` default (claims to absorb F-W3-02)

- **File:** `_parser.py:_add_reverse_pii_subcommand` +
  `_reverse_pii.py:_build_search_pattern`
- The default changed `custom` → `literal`.  The previous
  `custom`-default would `re.compile(query)` directly; the new
  `literal`-default `re.escape`s the query.  Walk:
  - Is this a *user-visible* breaking change that 0.5.4 operators
    would notice?  E.g. an operator who previously passed a
    regex without `--type custom` and got regex semantics by
    default now gets literal semantics — the documented behaviour
    is correct but the migration is silent.
  - Is the new `literal` choice surfaced in every doc location
    (`json-output.md`, `cli.md`, `gdpr_erasure.md`, audit catalog)?
    Cross-check.
  - The choice list at `_parser.py:921-925` adds `literal` first;
    confirm `argparse choices=` set is identical between
    `_parser.py` and `_IDENTIFIER_TYPES` in `_reverse_pii.py`.

#### A.4 — Snippet match-span centring (claims to absorb F-W3-03)

- **File:** `_reverse_pii.py:_truncate_snippet`,
  `_scan_file`
- The signature changed: now takes `match_span: Tuple[int, int]`
  and centres the window.  Walk:
  - Does `_scan_file` always pass a valid span?  Could
    `pattern.search(stripped)` return `None` on a line that the
    iterator believes matched?  (Defensive: should the helper
    handle `match_span=None`?)
  - The budget calculation
    `ctx = max((budget - match_len) // 2, 0)` has a degenerate
    case when `match_len > budget`.  What happens if the operator
    matches a regex that captures most of a 200-char line?
    Verify the snippet is still bounded at `_SNIPPET_MAX_CHARS`.
  - Multi-byte / grapheme cluster handling — F-W3T-05 absorption
    pinned a regression test, but does it cover edge cases like
    a match span that lands on a single emoji ZWJ sequence?
  - The trailing-ellipsis logic uses `< len(line)` to decide
    whether to append `…`.  If `win_end == len(line)` exactly,
    no ellipsis; if `win_end == len(line) - 1`, ellipsis.  Off-
    by-one risk?

#### A.5 — `UnicodeDecodeError` handling (claims to absorb F-W3-04)

- **File:** `_run_reverse_pii_cmd` exception handler
- The `except (OSError, UnicodeDecodeError) as exc:` block now
  catches both classes and emits a failure audit event.  Walk:
  - Does the audit event correctly record `error_class =
    "UnicodeDecodeError"` (not `OSError`)?  The
    `exc.__class__.__name__` should preserve the real class.
  - Other `ValueError` subclasses from `open()` / `read()` (e.g.
    `LookupError` from a custom encoding) — same treatment, or
    do they bubble?  Compare to the comment claim at
    `_reverse_pii.py:48-51` about "malformed UTF-8 mid-corpus".

#### A.6 — Audit-dir default move (claims to absorb F-W3-06 + F-W3-PS-06 + F-W3S-02)

- **File:** `_reverse_pii.py:_resolve_audit_dir`
- The default moved from `output_dir` to
  `<output_dir>/audit/`.  Walk:
  - Does this break any operator workflow that pinned
    `audit_log.jsonl` to the corpus dir?  CHANGELOG note
    sufficient?
  - The `forgelm purge` and `forgelm audit` subcommands — what
    are their audit-dir defaults?  Are the three subcommands
    consistent?
  - When the audit dir doesn't exist yet, `AuditLogger.__init__`
    creates it via `os.makedirs(... exist_ok=True)`.  Any
    permission edge case for the new `<output_dir>/audit/`
    sub-creation?

#### A.7 — ReDoS guard (claims to absorb F-W3-PS-03 + F-W3-07 + F-W3S-03)

- **File:** `_reverse_pii.py:_scan_file_with_alarm`,
  `_scan_files_with_redos_guard`
- POSIX SIGALRM-based per-file 30s budget.  Walk:
  - On Windows the guard is a no-op.  Is that documented?  Does
    the audit event say anything about the guard being skipped?
  - SIGALRM is a process-wide signal.  If `_scan_file_with_alarm`
    is called from a thread, the alarm will fire on the main
    thread.  Are there any test fixtures or ForgeLM invocation
    paths that run reverse-pii in a thread?
  - The alarm restoration logic (`finally` clause that resets
    the alarm + restores the previous handler) — does it
    correctly handle re-entrant calls?  Could a previous
    handler's signal be lost?
  - Is 30s the right budget?  Compare to the audit chain's
    expected per-event latency.

#### A.8 — Implicit `output_dir` warning (claims to absorb the new finding from `7adecb1`)

- **File:** `_run_reverse_pii_cmd:524-541`
- When `--salt-source` is set + `--output-dir` is implicit, a
  WARNING fires about cross-tool correlation risk.  Walk:
  - Is the warning's message text accurate?  It names "Cross-tool"
    — is that operator-meaningful?
  - Should this be an ERROR instead of WARNING?  The original
    finding offered both (a) error, (b) warning; the maintainer
    chose (b).  Is that the right call given the privacy
    sensitivity of Article 15 access requests?
  - The warning suppression — does `--quiet` mute it?  Per
    `logging-observability.md`, quiet mode should still surface
    warnings *to the run log*, not stdout.

### B. `forgelm/config.py` — F-compliance-110 refactor (`6ba93be`)

#### B.1 — Cognitive-complexity refactor (claims to absorb python:S3776)

- **File:** `config.py:_warn_high_risk_compliance` +
  `_resolve_risk_label`, `_warn_unacceptable_practice`,
  `_enforce_safety_gate_for_strict_tier`
- The function was refactored into 3 helpers + a thin orchestrator.
  Walk:
  - **Behaviour invariance:** does the new code produce identical
    output for every input the old code handled?  Specifically:
    - `risk_assessment` AND `compliance` BOTH set to high-risk
      vs only one set — does `_resolve_risk_label` pick
      consistently with the previous `(self.compliance and …) or
      (self.risk_assessment and …)` ordering?  The old code
      preferred `self.compliance.risk_classification` last; the
      new code prefers `risk_assessment.risk_category` first
      (line 858).  Is that an intentional swap?
    - The `auto_revert` warning previously fired BEFORE the
      `unacceptable` extra notice; the new code preserves that
      order via `_warn_unacceptable_practice` after the
      auto_revert log.  Confirm via test_eu_ai_act caplog.
    - `track_categories` warning — previously inside `elif`
      against safety not enabled; new code is in the
      `_enforce_safety_gate_for_strict_tier` body after the
      raise.  Equivalent?
  - The error message format — old code used `% (label,)` lazy
    formatting; new code uses `f"... {label!r} ..."` eager.  Is
    `label!r` rendering identical to the old `%r`?  Quoting style
    matters for the regression test
    `pytest.raises(ConfigError, match="evaluation.safety.enabled")`.

### C. `tools/check_bilingual_parity.py` — heading recogniser rewrite (`5491572` + `6ba93be` + `730a015` + `cd66c54`)

#### C.1 — Heading prefix split (claims to absorb python:S5852)

- The single `_HEADING_RE` was split into `_HEADING_PREFIX_RE`
  (compiled regex) + `_strip_atx_close_and_whitespace` (pure
  Python).  Walk:
  - **CommonMark §4.2 conformance for ATX-close strip:** the
    helper requires whitespace BEFORE the trailing run of hashes
    for them to count as ATX-close.  Spec says "An optional
    closing sequence of `#` characters preceded by a space".
    Verify the helper matches: `## Foo ##` → `Foo` (yes), `## Foo## `
    (no space before closing `##`) → `Foo##` (kept as content)?
    The new helper checks `stripped[hash_start - 1] in " \t"`.
    Tab is acceptable per CommonMark; space is acceptable; a
    multi-byte whitespace character (NBSP) is NOT.  Is this a
    real risk for any project doc?

#### C.2 — Fence length / type enforcement (claims to absorb gemini-code-assist medium)

- The fence detection now stores the full opener and requires the
  closer to have the same first character AND length ≥ opener.
  Walk:
  - The check `marker[0] == fence_marker[0]` only inspects the
    first character.  CommonMark §4.5: "The closing code fence
    must use the same character as the opening fence (backticks
    or tildes)" — first-char check is sufficient since the
    `_FENCE_RE` already restricts to `(```+|~~~+)` (homogeneous
    runs).  Confirm.
  - Indented fences — CommonMark allows up to 3 spaces of indent
    on the fence line, but the parity tool's regex `^(```+|~~~+)`
    is anchored at column 0.  Is that acceptable for ForgeLM's
    docs (which use no leading indent)?
  - The new `test_longer_opening_fence_not_closed_by_shorter_run`
    + `test_backtick_fence_not_closed_by_tilde_fence` regressions
    cover the headline fix.  Is there a third edge case (closer
    longer than opener) that needs a test?

#### C.3 — Pair registry growth (8 → 9 pairs)

- `audit_event_catalog{,-tr}.md` was added to `_PAIRS`.
  `safety_compliance-tr.md` was deliberately NOT added (in-progress
  allowlist via `test_every_tr_mirror_appears_in_pair_registry`).
  Walk:
  - Is the allowlist mechanism the right shape?  Or should the
    test just track an issue link for safety_compliance-tr.md's
    Wave 4 completion?
  - Are there any other `*-tr.md` files outside
    `docs/{guides,reference}/` that DO have parity contracts the
    test should cover (but currently don't because the test scope
    is limited to those two directories)?

### D. `forgelm/webhook.py` — timeout fallback (claims to absorb F-W3S-04)

- **File:** `webhook.py:80-100`
- Now reads
  `WebhookConfig.model_fields["timeout"].default`.  Walk:
  - Late-import inside the method body — defensible (avoids
    circular imports with `config.py`)?  Or could it be a top-of-
    file import?
  - The clamp message format (`%ds`) — does it correctly render
    `10` for the new default?
  - The `not isinstance(timeout, (int, float))` guard remains.
    Could a Pydantic-validated `WebhookConfig` ever produce a
    non-numeric `timeout`?  If not, is the guard dead code?

### E. Test rigour (claims to absorb F-W3T-01 + F-W3T-02 + F-W3T-03 + …)

#### E.1 — Failure-path no-leak invariant (F-W3T-01)

- **File:** `test_reverse_pii.py:test_mid_scan_io_failure_writes_failed_audit_event_without_leaking_identifier`
- The test asserts
  `"alice@example.com" not in json.dumps(evt)` on the failure
  path.  Walk:
  - Is the assertion strong enough?  An attacker could embed a
    transformed form (base64, hex, ROT13) that the substring
    check misses.  Should the test also assert
    `evt["query_hash"] == _hash_for_audit("alice@example.com", salt)`
    (positive shape)?
  - The test fixture passes a custom `_flaky_scan` that raises
    `OSError` on the second call.  Does the test exercise the
    `UnicodeDecodeError` path too, or is that
    `test_malformed_utf8_corpus_exits_runtime_error_with_audit_event`
    only?  If the no-leak assertion is in the OSError test only,
    the UnicodeDecodeError audit event isn't pinned for no-leak.

#### E.2 — Strict-tier parametrize (F-W3T-02)

- **File:** `test_eu_ai_act.py:test_strict_tier_safety_disabled_raises_config_error`
- Now `@pytest.mark.parametrize("tier", ["high-risk", "unacceptable"])`.
  Walk:
  - Is the `match=` regex on the `pytest.raises` permissive
    enough for both tiers?  The error message includes the tier
    label, so `match="evaluation.safety.enabled"` should match
    both — confirm.
  - Are both tiers exercised end-to-end (not just at config
    validation)?  An integration test in `test_integration.py`
    pins one of them; does it pin both?

#### E.3 — Setext exclusion (F-W3T-03)

- **File:** `test_check_bilingual_parity.py:test_setext_headings_are_not_matched`
- Walk: the test plants `Setext H1\n=====` and asserts only
  `## Real H2` registers.  Does it also cover the case where a
  setext underline appears AFTER the structural heading set is
  built (i.e., line N is `Some text\n========\n## H2`)?  The
  `=====` is on its own line and would not match `_HEADING_PREFIX_RE`
  — confirmed safe by inspection, but is there a test?

### F. Cross-cutting (XPR) checks

#### F.1 — Documentation drift (post-absorption)

- **F-W3FU-XPR-01** — Did every absorption that touched code also
  update the matching doc?  Specifically:
  - `--type literal` default change → `cli.md`, `json-output.md`,
    `gdpr_erasure.md`, audit catalog — all four updated?
  - `salt_source` field in audit event → audit catalog (EN+TR)
    + `json-output.md` (EN+TR) updated?
  - Audit-dir default `<output_dir>/audit/` → operator guide,
    `cli.md`, `_parser.py` help text — all consistent?

#### F.2 — Wave 3 closure-plan honesty

- **F-W3FU-XPR-02** — `closure-plan-202604300906.md:130` "Kalan
  iş" list now says 4 phases pending.  Cross-check against the
  table at L75-110: are exactly 4 phases marked PENDING and
  exactly 3 (24 + 28 + 38) marked Wave 3 done?

#### F.3 — Coverage / behaviour parity

- **F-W3FU-XPR-03** — The original review's "Verified absorptions"
  section in each report (e.g.
  `wave3-code-correctness.md:619-663`) lists contracts that were
  PASSING before absorption.  Did any absorption inadvertently
  break one of those passing contracts?  Spot-check 3 random
  passing items per original report.

#### F.4 — Backwards compatibility (post-absorption)

- **F-W3FU-XPR-04** — Walk every public-API surface touched in
  the diff:
  - `forgelm.cli` facade re-exports — added `_emit_audit_event`,
    `_resolve_audit_dir`.  Is that acceptable additive change?
  - `_scan_files_with_redos_guard` signature lost `output_format`.
    Is it a public symbol?  If yes, who imports it?  (The
    `__all__` list in `_reverse_pii.py` doesn't include it; the
    facade doesn't either — should be safe.)

#### F.5 — Lint / format equivalence

- **F-W3FU-XPR-05** — The absorptions ran `ruff format` between
  commits.  Spot-check whether any auto-format change altered
  *behaviour* vs purely cosmetic.  E.g. changes to docstring
  indentation, line splitting that affected an f-string's
  embedded expression.

## Ground rules

- **Read the relevant standard before commenting.** The project
  [docs/standards/](../../standards/) directory is the rulebook.
- **Re-evaluate, don't just trust.**  An "absorbed" finding in
  the maintainer's PR comment summary is a *claim*.  Verify the
  fix against the cited file:line.  If the fix is correct, say
  so explicitly in your "Verified absorptions" section.  If the
  fix is incomplete or wrong, that's a `F-W3FU-NN` finding.
- **Cite line numbers.**  If you cannot point at a line, the
  finding is not actionable.
- **Distinguish original vs newly introduced.**  Tag every
  finding with whether it traces back to an original
  (`F-W3-NN` / `F-W3-PS-NN` / `F-W3S-NN` / `F-W3T-NN`) or is
  *new* (introduced by the absorption itself).  Use the
  `Trace-back to original finding` field in the deliverable.
- **No phantom severity inflation.**  A doc typo is `NIT`.  A
  user-visible CLI bug on the happy path is `HIGH` minimum.
- **No re-litigating closed scope.**  "Should ForgeLM also do X"
  is not a finding.  Stay in the diff.
- **Reverse-pii is a privacy-sensitive surface.**  Same rule as
  the original prompt: any path where cleartext can leak into
  the audit log is `CRITICAL`.

## Required deliverable structure

Each reviewing agent returns a single Markdown report with this
skeleton, saved as
`docs/analysis/code_reviews/wave3fu-<agent-name>.md`:

```markdown
# Wave 3 Follow-up — <agent-name> Review of `closure/wave3-integration`

> Branch: `closure/wave3-integration` · HEAD `7adecb1` · Reviewer focus:
> <one-sentence focus>.  Re-evaluating absorptions since `95e2bf8`.

## Summary
- Verdict: [Block / Conditional / Approve]
- CRITICAL: N · HIGH: N · MEDIUM: N · LOW: N · NIT: N
- One-sentence headline of the highest-severity finding.

## Findings

### F-W3FU-NN · <SEVERITY> · <one-line title>
- **File:** path:line[-line]
- **Trace-back:** F-W3-NN / F-W3-PS-NN / F-W3S-NN / F-W3T-NN / NEW
- **What's wrong:** ...
- **User-visible consequence:** ...
- **Suggested fix:** ```code```
- **Regression test:** ```python ...```

(repeat per finding)

## Verified absorptions

For each CRITICAL / HIGH from the four original reports + the
4 inline PR comments + 5 SonarCloud items, state:

- **F-<original-id> [verified]** — fix lands at <file:line>; the
  contract <X> now holds.  Walked: <what you walked>.
- **F-<original-id> [partial]** — fix addresses <X> but misses
  <Y>; new finding F-W3FU-NN tracks it.
- **F-<original-id> [regressed]** — fix introduces <Z>; new
  finding F-W3FU-NN tracks it.

## What this report deliberately did not cover

(scope notes, deferred items, out-of-PR areas)

## Merge recommendation

(Block / Conditional / Approve, with the headline reasons)
```

## How to launch

Spawn 4 parallel sub-agents (you may use any harness that supports
parallel workers; the original review used Claude `Agent` calls
in a single message).  Pass each agent the SAME prompt, with one
extra line at the top stating its agent name + focus:

1. **Code-correctness agent.** Focus areas: §A.1, A.4, A.5, A.7,
   B.1, C.2, F.4, F.5.
2. **Privacy / security agent.** Focus areas: §A.1, A.2, A.6, A.8,
   E.1.  Privacy bar reigns.
3. **Standards / compliance agent.** Focus areas: §A.3, A.6, B.1,
   D, F.1, F.2, F.3.  Cite docs/standards/* extensively.
4. **Test-rigour agent.** Focus areas: §A.4, A.7, C.2, C.3, E (all),
   F.3.  Vacuous-test bar reigns.

Agents run independently.  Maintainer absorbs in a single round
(per the established Wave 3 cadence).

---

*Frozen at `7adecb1` on 2026-05-05.*  *If any reviewer finds the
prompt itself ambiguous, surface it as a `F-W3FU-PROMPT-NN`
finding before merging — the prompt itself is part of the audit
trail.*

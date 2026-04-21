# Code Review Standard

> **Scope:** Every pull request to `cemililik/ForgeLM`. Applies equally to external contributors and the maintainer.
> **Enforced by:** `.github/pull_request_template.md` checklist + CI gates + reviewer attention.

## The default state of a PR is "blocked"

A PR merges only after:

1. **Green CI** — all required checks pass.
2. **One approval** — from the maintainer or an authorized reviewer.
3. **Self-checklist complete** — every box in the PR template ticked honestly.
4. **No open review comments** marked as "changes requested."

No exceptions for "trivial" changes. Even typo fixes go through CI.

## PR template

The current template lives at [`.github/pull_request_template.md`](../../.github/pull_request_template.md). Every PR auto-fills it. Structure:

```markdown
## Summary
<one-sentence description>

## Changes
- bullet 1
- bullet 2

## Type
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Refactoring
- [ ] Test
- [ ] CI/CD

## Testing
- [ ] `pytest tests/` passes
- [ ] `ruff check .` passes
- [ ] `ruff format --check .` passes
- [ ] New tests added for new code
- [ ] `forgelm --config config_template.yaml --dry-run` works

## Checklist
- [ ] Code follows `docs/standards/coding.md`
- [ ] Documentation updated (if behaviour-visible)
- [ ] `-tr.md` mirrors updated (if user-facing docs changed)
- [ ] No new heavy deps (or added as optional extra)
- [ ] `config_template.yaml` updated if a new config field was added
- [ ] CHANGELOG entry added under `[Unreleased]`
```

**Rule:** every box must be ticked or explicitly crossed out (`~~[x]~~`) with a reason in the PR description. "Skipped because..." is acceptable. "Forgot" is not.

## What reviewers look for

In order of priority:

### 1. Does it match [architecture.md](architecture.md)?

- Right module for the concern?
- Is config flow respected? (YAML → Pydantic → passed down, not env-var-sniffing inside modules)
- Are new deps declared as extras?
- Does it grow a module past ~1000 lines without splitting?

### 2. Does it match [coding.md](coding.md)?

- Ruff passes (CI catches this; reviewer skims for it)
- Type hints on public functions
- `Optional[X]` not `X | None` (consistency)
- Google-style docstrings
- No silent-try-except (see [error-handling.md](error-handling.md))

### 3. Are the tests real?

- New public function has a happy-path + at least one error-path test
- No `pytest.skip` without justification
- No GPU dependency in unit tests
- `pragma: no cover` used only for documented exemptions
- If auto-revert / safety gate / exit code behaviour changed, is there a test that triggers it?

### 4. Is the observability correct?

- Every new decision gate emits an audit log event
- Every new exit code is documented in [error-handling.md](error-handling.md)
- No `print()` outside CLI JSON-output blocks
- No secrets in logs

### 5. Is the documentation correct?

- If a config field was added: updated in `docs/reference/configuration.md` and its TR mirror
- If CLI surface changed: updated in `docs/reference/usage.md` and TR mirror
- If a new guide is warranted: added under `docs/guides/`
- CHANGELOG entry written

### 6. Is the scope right?

- Does it do one thing? (A bug fix + a refactor + a new feature in one PR: split.)
- Are drive-by reformats included that obscure the real diff? (Reject those.)
- Is it a minimum viable implementation, or has scope crept?

## Comment etiquette

For reviewers:

1. **Specific over abstract.** "`line 47`: the docstring contradicts the type hint — fix one" beats "docstrings need attention."
2. **Suggest code when you can.** GitHub's suggestion syntax is cheap and concrete.
3. **Distinguish blocking from optional.** Prefix optional: "Nit:", "Style:", "FYI:". Blocking comments don't need a prefix.
4. **Praise specific things, not the whole PR.** "The hash chain in `AuditLogger._append()` is clean" > "LGTM!".
5. **Say why.** Every blocking comment includes a reason. "Change this to X" with no reason = bad feedback.

For PR authors:

1. **Don't debate on tone.** If a reviewer asks a question, answer with code or explanation.
2. **Acknowledge each comment.** Thread-level "Done" / "Won't do — reason" for every thread.
3. **Don't resolve threads you didn't open.** The reviewer closes their own.
4. **One new commit per round of feedback.** Don't force-push during review (unless requested) — it destroys diff-per-comment history.

## Merging

**Default: squash merge.**

- Keeps history linear and readable.
- Commit message = PR title. Edit it to be good *before* clicking merge.
- Trailers: `Co-authored-by:` for multi-author PRs, `Fixes #N` for issue closure.

**Exception: merge commit** for:

- Multi-commit PRs where each commit is a meaningful, reviewed unit (rare).
- Dependabot bulk updates.

Don't rebase-and-merge. Don't disable CI checks. Don't bypass branch protection.

## Reviewing your own PR before requesting review

Do this *first*. It saves reviewer time:

1. **Read the diff top to bottom in GitHub's UI.** Not `git diff` locally — GitHub's web UI is what reviewers see, and the rendering reveals issues the CLI hides.
2. **Check every `TODO`, `FIXME`, `XXX`.** Did you mean to leave them? Add owner + issue link or remove.
3. **Check every `import`.** Unused? Out of order?
4. **Click the test files.** Does each new test actually assert something?
5. **Click the doc diffs.** Does it render correctly? Do links work?

If you find issues at this stage, push fixes before requesting review. Don't make the reviewer find them.

## Handling pushback

Sometimes a reviewer is wrong. Sometimes you are. The default assumption is **"reviewer is right"** — if you disagree:

1. State the specific disagreement in a comment.
2. Link to a standard, prior art, or concrete reason.
3. If unresolved, escalate to a third reviewer or discuss in an issue.

The goal is the codebase, not the ego. A PR that gets blocked from merging isn't a failure; a bad change that gets merged is.

## Anti-patterns (from maintainer experience + external analyses)

Referencing [marketing/strategy/05-yapmayacaklarimiz.md](../marketing/strategy/05-yapmayacaklarimiz.md) and analyses of adjacent projects:

| Anti-pattern | Why rejected | Fix |
|---|---|---|
| Disabling CI with `\|\| true` or `continue-on-error` | Masks failures; fake safety | Fix the underlying issue |
| `--amend` + force-push after reviewer started commenting | Destroys review history | New commits only until merge |
| Merging "docs-only" PRs that reference not-yet-written code | Creates permanent drift | Docs follow code, same PR or later |
| Bundled refactor + feature PRs | Hides logic changes in formatting noise | Split into separate PRs |
| "I'll add tests next PR" | Tests never come | Block merge until tests in same PR |
| Review approval from LLM-only with no human reading | No real review | Human approval required, even if LLM helped |
| Marking a stub/placeholder "Done" | False progress | Use `NotImplementedError` with issue link; mark phase "Planned" |
| Renaming without updating docs | Silent doc rot | `grep -r <old_name>` before pushing |

## Quick self-review command

Before pushing:

```bash
# Formatter + linter + all tests + dry-run
ruff format . && ruff check . && pytest tests/ && \
forgelm --config config_template.yaml --dry-run
```

If that passes and the PR template is honest, you're ready.

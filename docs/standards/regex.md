# Regex Hygiene Standard

> **Scope:** Every `re.compile`, `re.match`, `re.search`, `re.sub`, `re.findall`, and `re.split` call in [`forgelm/`](../../forgelm/) and [`tests/`](../../tests/).
> **Why this exists:** Phase 11/11.5/12 review cycles produced ~10 distinct SonarCloud / reviewer findings on regex correctness, ReDoS exposure, and code-smell patterns. This standard codifies the lessons so the next regex we ship doesn't trip the same flags.
> **Enforced by:** Code review checklist (in [code-review.md](code-review.md)) + the ReDoS guard in [logging-observability.md](logging-observability.md) when audit / ingest extends.

## Hard rules

These come straight from real findings on the ForgeLM codebase. If a new regex breaks one, fix the regex (or fail review).

### 1. No `[A-Za-z0-9_]`; use `\w`

`[A-Za-z0-9_]` and `\w` mean the same thing in Python's default regex flavour. Use the shorter form — SonarCloud `python:S6353` flags the verbose alternative every time.

```python
# WRONG — Sonar flagged this in forgelm/data_audit.py (Phase 12 review round 2)
"github_token": re.compile(r"\b(?:ghp|gho)_[A-Za-z0-9_]{20,}\b"),

# RIGHT
"github_token": re.compile(r"\b(?:ghp|gho)_\w{20,}"),
```

If you actually need to exclude underscore (rare), use `[A-Za-z0-9]` (no `_`). Document why.

### 2. No single-char character classes; use the character

`[ ]` is a one-character class wrapping a single space. It's identical to a literal space, just slower for the engine and noisier to read. SonarCloud `python:S6328`.

```python
# WRONG — flagged in forgelm/ingestion.py (Phase 12 review round 2)
re.compile(r"^[ ]{0,3}(#{1,6})\s+(.+?)$", re.MULTILINE)

# RIGHT
re.compile(r"^ {0,3}(#{1,6})\s+(.+?)$", re.MULTILINE)
```

Same applies to `[a]`, `[\.]`, `[\\]` — strip the character class.

### 3. Bound your quantifiers

If the practical max is small, write it: `{1,6}` instead of `+`. Bounded quantifiers eliminate a whole class of ReDoS shapes and document the actual contract.

```python
# WEAK — accepts arbitrary-depth nesting; ATX heading depth is ≤ 6 in CommonMark
re.compile(r"^(#+)[ \t]+(.+)$")

# STRONG — bounded to the spec
re.compile(r"^(#{1,6})[ \t]+(.+)$")
```

### 4. Don't let two unbounded greedy/lazy quantifiers compete for the same characters

This is the #1 ReDoS shape we keep hitting. When two `*` / `+` / `*?` / `+?` quantifiers can both consume the same characters (overlapping character classes, or `.` matching everything), the engine has to try every split — O(n²) on lines that don't ultimately match.

```python
# WRONG — ReDoS-prone. Phase 12 audit confirmed: 100ms at n=2000, 600ms at n=5000.
# `[ \t]+`, `(.+?)`, and `[ \t]*$` can all match a space — engine tries every split.
re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*$", re.MULTILINE)

# RIGHT — anchor the body's first/last char on non-whitespace.
# Now `[ \t]+` and `[ \t]*` can't compete with the body capture.
re.compile(r"^ {0,3}(#{1,6})[ \t]+(\S(?:[^\n]*\S)?)[ \t]*$", re.MULTILINE)
```

The fix pattern: replace `(.+?)` between two whitespace runs with `(\S(?:[^\n]*\S)?)` — non-whitespace anchor at both ends, negated character class `[^\n]` in the middle.

### 5. Don't use `\s` when you mean `[ \t]`

`\s` matches `[ \t\n\r\f\v]` — including newlines. Under `re.MULTILINE` this almost always introduces ambiguity that the engine has to backtrack through, especially when the regex is anchored with `^…$`.

```python
# WRONG — `\s` overlaps with newlines under MULTILINE
re.compile(r"^(\w+)\s+(.+)$", re.MULTILINE)

# RIGHT — explicit "horizontal whitespace only"
re.compile(r"^(\w+)[ \t]+(.+)$", re.MULTILINE)
```

`\s` is acceptable in single-line contexts where newlines genuinely *should* count (rare in our codebase — the audit / ingest pipelines all process pre-split text).

### 6. Avoid `.*?` with a back-reference under `re.DOTALL`

This combination is the SonarCloud `python:S5852` "polynomial runtime" trigger. Even when CPython's regex engine handles it well in practice, the static analyser flags every instance.

```python
# WRONG — Sonar flagged data_audit.py L896 (Phase 12 review round 2.5).
# The `(?P=fence)` back-reference + lazy `.*?` + DOTALL is a textbook ReDoS shape.
_CODE_FENCE_BLOCK = re.compile(
    r"^ {0,3}(?P<fence>`{3,}|~{3,})[^\n]*\n.*?^ {0,3}(?P=fence)[ \t]*$",
    re.MULTILINE | re.DOTALL,
)

# RIGHT — replace the regex with a per-line state machine.
# Same logic; provably O(n); identical behaviour pinned by tests.
def _strip_code_fences(text: str) -> str:
    out, open_fence = [], None
    for line in text.splitlines(keepends=True):
        ...
```

The principle: when a regex with a back-reference needs to span multiple lines, write it as a state machine. The line-walker pattern in [`forgelm/ingestion.py::_markdown_sections`](../../forgelm/ingestion.py) and [`forgelm/data_audit.py::_strip_code_fences`](../../forgelm/data_audit.py) is the model.

### 7. Anchor `^` / `$` and use `re.MULTILINE` deliberately

`^` and `$` mean different things with and without `re.MULTILINE`. Pick one and document the intent.

- **`re.MULTILINE`** when you're working line-by-line on a multi-line string. Use `[^\n]` instead of `.` for the body (avoids overlap with `^` / `$`).
- **No `re.MULTILINE`** when the input is one logical line at a time (passed through `for line in text.splitlines()` already). Then `^` / `$` are start / end of the whole string.

### 8. No `^.*` when you mean "from the start"

`^.*` invites the engine to backtrack `.*` for every failure. If you really mean "from the start of the line", anchor and stop being greedy:

```python
# WRONG — `^.*foo` against a line that doesn't contain "foo" walks the whole line.
re.compile(r"^.*ERROR:")

# RIGHT — the engine fails at column 0 if "ERROR:" isn't there.
re.compile(r"^[^E]*ERROR:")  # or just .startswith("ERROR:")
```

For "starts with X", just use `text.startswith("X")`. Regex isn't the answer to every string question.

## ReDoS exposure budget

Some regexes consume operator-controlled input (e.g. `audit` / `ingest` walking user-provided JSONL or PDFs). Adversarial 100K-row corpora are a realistic threat for a CI/CD pipeline that runs ForgeLM on a webhook trigger.

For any regex that runs on operator-controlled input:

- **Verify linearity empirically.** Run the regex against a 10K-character pathological input. Wall-clock should be ≤ 10ms. If it isn't, the regex is broken.
- **Or replace with a non-regex parser.** State machines (line walkers) are O(n) by construction. We use them in [`forgelm/data_audit.py::_strip_code_fences`](../../forgelm/data_audit.py) and [`forgelm/ingestion.py::_markdown_sections`](../../forgelm/ingestion.py) precisely because the regex equivalents tripped SonarCloud.

The pathological-input benchmark for our regexes:

```python
import re, time
pat = re.compile(r"YOUR_PATTERN")

for n in [1_000, 5_000, 10_000]:
    payload = "ADVERSARIAL_BUILDER" * n
    t0 = time.perf_counter()
    pat.search(payload)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    print(f"n={n}: {elapsed_ms:.2f} ms")
```

Linear scaling on doubling input → safe. Quadratic / exponential scaling → broken; fix the regex or replace with a parser.

## Test fixture hygiene

Test files that exercise security-sensitive regexes (PII, credentials, JWTs) inevitably contain credential-shaped strings. Repo-wide secret scanners (gitleaks, trufflehog, GitGuardian) treat full literals as leaks even when they're test fixtures.

**Build secret-shaped fixtures from inert fragments at runtime.** The regex still has to match the canonical shape; no full literal credential lives in the source tree.

```python
# WRONG — gitleaks flags this as a real AWS key leak.
text = "config: aws_access_key_id=AKIAIOSFODNN7EXAMPLE end"

# RIGHT — module-level fragment-built constant.
FAKE_AWS_KEY: str = "AKIA" + "IOSFODNN7" + "EXAMPLE"
text = f"config: aws_access_key_id={FAKE_AWS_KEY} end"
```

The same applies to PEM block markers in regex source (we split `r"-----" + r"BEGIN " + r"..."` in [`forgelm/data_audit.py::_SECRET_PATTERNS`](../../forgelm/data_audit.py) for this reason).

## Pre-merge checklist

Before opening a PR that touches regex:

- [ ] No `[A-Za-z0-9_]` (use `\w`).
- [ ] No single-char character classes (use the character).
- [ ] Quantifiers bounded where the spec allows (`{1,6}` not `+`).
- [ ] No two competing unbounded quantifiers over the same character class.
- [ ] No `.*?` + back-reference + `DOTALL` (replace with a state machine).
- [ ] `re.MULTILINE` matches the actual input shape — line-by-line vs. whole-string.
- [ ] If the regex runs on operator-controlled input: linearity verified by 10K-char pathological benchmark.
- [ ] Test fixtures with credential-shaped strings built from inert fragments.

## Related standards

- [coding.md](coding.md) — overall Python style.
- [code-review.md](code-review.md) — the `regex` line item in the review checklist.
- [testing.md](testing.md) — how to add ReDoS regression tests.

## Real findings this standard absorbs

Each rule above traces back to a concrete review finding:

| Rule | Finding (file:line) | Phase |
|---|---|---|
| `[A-Za-z0-9_]` → `\w` | `data_audit.py:_SECRET_PATTERNS["github_token"]` | 12 round 2 |
| Single-char class | `ingestion.py:_MARKDOWN_HEADING_PATTERN` | 12 round 2 |
| Two competing quantifiers | `ingestion.py:_MARKDOWN_HEADING_PATTERN` | 12 round 2.5 (ReDoS confirmed) |
| `\s` overlap with `\n` | `ingestion.py:_MARKDOWN_HEADING_PATTERN` (early Phase 12) | 12 round 1 |
| `.*?` + back-ref + DOTALL | `data_audit.py:_CODE_FENCE_BLOCK` | 12 round 2.5 |
| Test fixture fragmentation | `tests/test_data_audit_phase12.py`, `tests/test_ingestion_phase12.py` | 12 round 2 |
| PEM marker fragmentation | `data_audit.py:_SECRET_PATTERNS["openssh_private_key"]` | 12 round 2 |

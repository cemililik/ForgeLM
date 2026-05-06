# Coding Standard

> **Scope:** All Python code under [`forgelm/`](../../forgelm/) and [`tests/`](../../tests/).
> **Enforced by:** `ruff check` + `ruff format --check` in CI ([`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)).

## Tooling

Configured in [`pyproject.toml`](../../pyproject.toml):

```toml
[tool.ruff]
target-version = "py310"
line-length = 120

[tool.ruff.lint]
select = ["F", "E9", "W", "B", "I"]
ignore = ["B008", "B905"]
```

- **Python 3.10+ only.** Support matrix: 3.10, 3.11, 3.12, 3.13 (tested in CI).
- **Line length: 120.** Not 80, not 88.
- **Lint rules:** pyflakes (`F`), syntax errors (`E9`), warnings (`W`), bugbear (`B`), import order (`I`).
- **Format:** `ruff format` (Black-compatible). Run before every commit.

Install dev tools: `pip install -e '.[dev]'` pulls in `ruff>=0.4.0` and `pytest>=8.0.0`.

## Naming

Follow PEP 8 with one clarification:

| Kind | Convention | Example |
|---|---|---|
| Module | `snake_case.py` | `forgelm/model_card.py` |
| Class | `PascalCase` | `ForgeConfig`, `AuditLogger`, `WebhookNotifier` |
| Function / method | `snake_case` | `train_with_auto_revert`, `generate_model_card` |
| Constant | `UPPER_SNAKE_CASE` | `EXIT_CONFIG_ERROR`, `DEFAULT_TIMEOUT` |
| Private | `_leading_underscore` | `_setup_logging`, `_send` |
| Pydantic config class | `XxxConfig` | `ModelConfig`, `LoraConfigModel`, `TrainingConfig` |

**One-letter variables:** allowed only for conventional math/loop locals (`i`, `j`, `x`, `y`). In domain code prefer descriptive names.

## Type hints

**Required on public API.** Use them on every `def` that's imported elsewhere or called from CLI.

- Use `Optional[X]`, not `X | None`. Codebase is uniformly `Optional` (e.g., `forgelm/config.py`, `forgelm/trainer.py`). Stay consistent even though both are valid on 3.10+.
- Use `List[X]`, `Dict[K, V]`, `Tuple[...]` from `typing` — matches existing imports.
- Use `Literal["a", "b"]` for enum-like string fields (seen throughout `forgelm/config.py`).
- `Any` is acceptable where structure is external (YAML dicts, HF return values) but prefer concrete types where possible.

```python
from typing import Any, Dict, List, Literal, Optional

def generate_data_governance_report(
    config: Any,
    dataset: Dict[str, Any],
) -> Dict[str, Any]:
    ...
```

## Docstrings

**Google style.** One-line summary, blank line, optional sections (`Args:`, `Returns:`, `Raises:`).

Module docstrings are required and should state purpose; for compliance-touching modules, cite the EU AI Act article:

```python
"""EU AI Act compliance, training data provenance, and audit trail generation.

Covers: Article 9 (Risk Management), Article 10 (Data Governance),
Article 11 + Annex IV (Technical Documentation), Article 12 (Record-Keeping),
Article 13 (Transparency), Article 14 (Human Oversight), Article 15 (Accuracy),
and Article 17 (Quality Management System).
"""
```

Function docstrings are required when:
- The function is public (no leading underscore) and non-trivial, or
- The behaviour is not obvious from the name and signature.

Keep them terse — if the docstring would just restate the name, skip it.

## Imports

Managed by `ruff` (rule `I`). Order:

1. Standard library
2. Third-party
3. Local (`forgelm.*`)

Within each group, alphabetical. `ruff format` handles this automatically.

**Do not** use wildcard imports (`from x import *`). **Do not** re-export via `__init__.py` unless there's a deliberate public API reason.

## Pydantic models

Every YAML-backed config section is a `BaseModel` subclass in [`forgelm/config.py`](../../forgelm/config.py). Follow:

- Field order: required first, then optional with defaults.
- Defaults must be safe for "omit from YAML" case.
- Use `field_validator` for cross-field checks; prefer `model_validator(mode='after')` for whole-model invariants.
- Do **not** silently coerce invalid values. Raise `ValueError` with actionable message (see [error-handling.md](error-handling.md)).

```python
class TrainingConfig(BaseModel):
    trainer_type: Literal["sft", "dpo", "simpo", "kto", "orpo", "grpo"] = "sft"
    num_train_epochs: float = 1.0
    per_device_train_batch_size: int = 1
    ...
```

## Comments

Default to no comments. Only add them when *why* is non-obvious:

- A non-trivial workaround → name the upstream bug or issue.
- A deliberately surprising default → say why.
- A TODO with an owner and condition.

**Never** write comments that restate the code. **Never** write comments that reference a specific PR, issue, or past fix — that belongs in git history or the changelog.

## Anti-patterns (rejected at review)

These come from [`docs/analysis/QKV-Core/14-forgelm-icin-cikarimlar.md`](../analysis/QKV-Core/14-forgelm-icin-cikarimlar.md) — concrete sins ForgeLM avoids:

| Anti-pattern | Why rejected | Correct form |
|---|---|---|
| Silent import fallback: `try: import X; except: X = None` | Breaks type hints, hides missing deps | Optional extras with explicit `ImportError` + install hint |
| `|| true` in CI | Masks real failures | Fix the test or xfail with reason |
| `torch.CUDA` (actual typo seen in another repo) | Runtime error disguised as config | Use `torch.cuda` always |
| Zero-byte files | Git noise | Delete or fill with minimal valid content |
| Hypothetical file paths in docs | Drift between docs and code | Every cited path must exist in a CI check |
| Placeholder stubs marked "v2.0 Ready" | False advertising | `NotImplementedError("Planned for Phase N")` with issue link |
| `[A-Za-z0-9_]` in regex | Verbose; SonarCloud `python:S6353` | `\w` |
| `[ ]{0,3}` (single-char class) | Noisy; SonarCloud `python:S6328` | ` {0,3}` |
| Two competing greedy/lazy quantifiers over the same char class (`[ \t]+(.+?)[ \t]*$`) | O(n²) ReDoS — confirmed at `n=2000` in `_MARKDOWN_HEADING_PATTERN`; review round 2.5 | Anchor on `\S` at body boundaries: `[ \t]+(\S(?:[^\n]*\S)?)[ \t]*$` |
| `.*?` + back-reference + `re.DOTALL` | SonarCloud `python:S5852`; replace with state machine | Per-line walker (see [`_strip_code_fences`](../../forgelm/data_audit/_quality.py)) |

For deeper regex rules (8 hard rules + ReDoS exposure budget + test fixture hygiene), see [regex.md](regex.md).

## When you break these rules

You don't. Ruff will catch the style ones. Reviewers will catch the rest. If a rule actively blocks a legitimate change, open a PR here first to update the standard — with reasoning.

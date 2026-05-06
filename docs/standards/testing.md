# Testing Standard

> **Scope:** Everything under [`tests/`](../../tests/) + CI workflows under [`.github/workflows/`](../../.github/workflows/).
> **Enforced by:** `.github/workflows/ci.yml` (required) + `.github/workflows/nightly.yml` (compatibility).

## Layout

Current structure (post Wave 4 round-2 absorption: ~70 test modules,
one per feature area; ~1413 tests collected). The tree below is a
**representative subset** — see `git ls-files tests/` for the full
inventory:

```
tests/
├── conftest.py                     # Shared fixtures (minimal_config factory)
├── runtime_smoke.py                # Full-pipeline smoke fixture generator
├── test_smoke.py                   # Basic imports + CLI invocation
├── test_integration_smoke.py       # End-to-end dry-run across trainer types
├── test_cli.py                     # CLI argument parsing + exit codes
├── test_cli_subcommands.py         # Subcommand dispatching
├── test_config.py                  # Pydantic schemas + validators
├── test_trainer.py                 # Trainer orchestration logic
├── test_alignment.py               # DPO / SimPO / KTO / ORPO / GRPO
├── test_long_context.py            # RoPE scaling, NEFTune, sample packing
├── test_galore.py                  # GaLore optimizer
├── test_moe_functions.py           # MoE expert quantize + freeze
├── test_phase7.py                  # VLM + merging + PiSSA
├── test_merging_algos.py           # TIES / DARE / SLERP
├── test_synthetic.py               # Teacher → student distillation
├── test_benchmark.py               # lm-eval-harness wrapper
├── test_safety_advanced.py         # Llama Guard + severity + categories
├── test_judge_functions.py         # LLM-as-judge evaluation
├── test_compliance.py              # Audit log + manifests + provenance
├── test_eu_ai_act.py               # Articles 9-15 + Annex IV
├── test_model_card.py              # Model card generation
├── test_cost_estimation.py         # GPU cost heuristics
├── test_webhook.py                 # Slack/Teams notifier
├── test_distributed.py             # DeepSpeed / FSDP config
├── test_data_edge_cases.py         # Malformed datasets, edge cases
├── test_supply_chain_security.py   # Wave 4 / Faz 23 — pip-audit + bandit + SBOM
├── test_check_anchor_resolution.py # Wave 4 / Faz 26 — markdown anchor resolver
├── test_check_bilingual_parity.py  # Bilingual EN/TR mirror parity
├── test_gdpr_erasure.py            # GDPR Article 17 (forgelm purge)
└── …
```

**Rules:**

- One `test_<module>.py` per `forgelm/<module>.py` where practical.
- Cross-cutting features (EU AI Act, alignment) get their own file that may import multiple modules.
- `conftest.py` holds shared fixtures only. Domain-specific helpers live in the test files that need them.
- A new feature PR adds the matching `test_*.py` in the **same** PR. No "tests in next PR."

## Fixtures

From [`tests/conftest.py`](../../tests/conftest.py):

```python
def minimal_config(**overrides):
    """Create a minimal valid ForgeConfig dict for testing."""
    data = {
        "model": {"name_or_path": "org/model"},
        "lora": {},
        "training": {},
        "data": {"dataset_name_or_path": "org/dataset"},
    }
    data.update(overrides)
    return data
```

**Rules:**

1. **Factory functions over static fixtures.** `minimal_config(training={"trainer_type": "dpo"})` is better than 50 parametrized fixtures.
2. **No GPU in unit tests.** Mock `torch.cuda.is_available()` or use CPU-only paths. Unit tests must run on a laptop with no GPU.
3. **No network in unit tests.** Mock `requests.post`, `huggingface_hub.snapshot_download`, etc. Integration tests may hit `localhost` but never external services.
4. **Deterministic.** `random.seed(42)`, `torch.manual_seed(42)` in any test that touches RNG. Flaky test = broken test.

## Test categories

| Category | Scope | Speed | Runs in CI? |
|---|---|---|---|
| **Smoke** (`test_smoke.py`) | Import + CLI `--help` works | < 5s | Every push |
| **Unit** (`test_<module>.py`) | One function / method at a time, heavy mocking | < 60s total | Every push |
| **Integration smoke** (`test_integration_smoke.py`) | Full pipeline dry-run, no GPU, mocked HF | < 5min | Every push |
| **Distributed** (`test_distributed.py`) | DeepSpeed/FSDP config generation (no actual multi-GPU) | < 30s | Every push |
| **Compatibility** (via `nightly.yml`) | Upstream dep upgrades — latest TRL, PEFT, Unsloth | ~10min | Nightly only |

**Never** write a test that requires an actual GPU. The fixture `runtime_smoke.py` exists so "full pipeline" checks are dry-runs. If you genuinely need GPU validation, document it as a manual release-gate check in [release.md](release.md), not a CI test.

## Mocking

Preferred libraries: `unittest.mock.patch`, `pytest.monkeypatch`, `requests_mock`.

**What to mock:**

- Network: `requests.post`, `huggingface_hub.*` downloads, OpenAI/Anthropic API calls
- GPU: `torch.cuda.is_available`, `torch.cuda.get_device_name`
- Time: `time.sleep`, datetime patterns where tests need determinism
- Third-party heavy imports: `unsloth`, `bitsandbytes`, `deepspeed`, `lm_eval` (when unavailable)

**What NOT to mock:**

- Pydantic validation (use real config objects)
- File I/O under `tmp_path` (use the real filesystem via pytest fixture)
- YAML parsing
- Anything `forgelm`-internal that has a fast real implementation

## Coverage

From [`pyproject.toml`](../../pyproject.toml):

```toml
[tool.coverage.report]
fail_under = 40
```

**40% is the floor, not the target.** Current repo sits well above it. The floor was raised from `25` to `40` during Phase 11/11.5 review cycles once the audit / ingest module suite landed; the standard is now in lock-step with the toml. Rules:

1. Every new module starts at or above the overall floor.
2. Public API (non-underscore functions) has coverage.
3. Error paths (every `raise` and every `sys.exit(!=0)`) must have at least one test that triggers them.
4. `pragma: no cover` is allowed only for:
   - `if __name__ == "__main__":` blocks
   - `except ImportError:` fallbacks for optional deps
   - Explicit "not implemented on this platform" branches

If you need to exempt more, file an issue first.

## CI gates

From [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml):

1. **Lint** — `ruff check` + `ruff format --check` on entire repo. Failure = PR blocked.
2. **Test matrix** — Python 3.10, 3.11, 3.12, 3.13 on ubuntu-latest.
3. **Coverage** — `pytest --cov=forgelm --cov-fail-under=40` (enforced via `addopts` in `pyproject.toml`'s `[tool.pytest.ini_options]`, kept in lock-step with `[tool.coverage.report].fail_under`).
4. **Dry-run validation** — `forgelm --config config_template.yaml --dry-run` must succeed.

From [`.github/workflows/nightly.yml`](../../.github/workflows/nightly.yml):

- Unbounded upstream versions (latest TRL/PEFT/Unsloth) to catch breaking changes early.
- Failure does **not** block PRs but triggers an issue.

**No `|| true` anywhere.** If a step is allowed to fail, use `continue-on-error: true` with a comment explaining why.

## Writing a new test

Template for a new module's test file:

```python
"""Tests for forgelm.<module>."""
import pytest
from forgelm.<module> import <public_api>


class TestPublicFunction:
    def test_happy_path(self, tmp_path):
        result = <public_api>(...)
        assert result.status == "ok"

    def test_raises_on_invalid_input(self):
        with pytest.raises(ConfigError, match="trainer_type"):
            <public_api>(bad_input)

    @pytest.mark.parametrize("value,expected", [
        ("sft", "SFTTrainer"),
        ("dpo", "DPOTrainer"),
    ])
    def test_trainer_class_selection(self, value, expected):
        assert select_trainer(value).__name__ == expected
```

## Anti-patterns

| Anti-pattern | Why rejected | Correct form |
|---|---|---|
| `pytest.skip("not yet implemented")` | Tracks zero actual behaviour | Use `pytest.mark.xfail(reason="...")` with an issue link |
| Test that just calls the function and asserts no exception | Proves nothing | Assert specific returns/side effects |
| `sleep(2); assert something` | Flaky by construction | Use `monkeypatch` for time, or event-based waits |
| `print()` to debug tests | Noisy output | Use `caplog` fixture for log assertions |
| `@pytest.fixture(scope="session")` for mutable state | Cross-test pollution | Scope to `function` unless immutable |

## Quick checklist before opening PR

- [ ] `pytest tests/` passes locally
- [ ] `ruff check . && ruff format --check .` passes
- [ ] `forgelm --config config_template.yaml --dry-run` succeeds if you touched CLI or trainer
- [ ] New public function or class has tests covering happy path + one error path
- [ ] Any new exit code or exception is tested
- [ ] No GPU or network required for new unit tests

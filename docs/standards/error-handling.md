# Error Handling Standard

> **Scope:** All error paths in [`forgelm/`](../../forgelm/). CI/CD orchestrators depend on these rules to make decisions — violating them silently breaks pipelines downstream.
> **Enforced by:** Code review + CI tests under `tests/test_cli.py`, `tests/test_config.py`.

## Exit codes

Defined in [`forgelm/cli.py`](../../forgelm/cli.py):

```python
EXIT_SUCCESS = 0
EXIT_CONFIG_ERROR = 1
EXIT_TRAINING_ERROR = 2
EXIT_EVAL_FAILURE = 3
EXIT_AWAITING_APPROVAL = 4
```

| Code | When | Who reads it |
|---|---|---|
| **0** | Happy path — training completed, all gates passed | CI/CD success |
| **1** | Config validation failed (YAML schema, Pydantic error) | CI/CD "fail fast"; user fixes YAML |
| **2** | Training crashed or failed mid-run (OOM, CUDA error, unhandled exception) | CI/CD retry logic |
| **3** | Training completed but eval/safety/benchmark threshold failed, and auto-revert happened | CI/CD decision: do not deploy |
| **4** | Training + evals passed, but `require_human_approval: true` — staged, awaiting human sign-off | CI/CD pauses pipeline |

**Rules:**

1. Never use numbers outside this set. If you invent a new failure class, add it here with a name and update this table first.
2. Every `sys.exit(N)` must use a named constant. `sys.exit(1)` literal is a review red flag.
3. Exit codes are part of the public contract. Changing the meaning of a code is a breaking change — bump major version.
4. Always log before exiting (see [logging-observability.md](logging-observability.md)).

## Exception types

Custom exceptions are **deliberately few**. One class per coarse-grained failure domain:

```python
# forgelm/config.py:387
class ConfigError(Exception):
    """Raised when configuration validation fails."""
```

**Rules for adding a new exception class:**

- The class must be catchable by a specific `except` site that does something different. If you'd catch it and do the same thing as `except Exception`, you don't need the class.
- Name ends with `Error` (`ConfigError`, not `ConfigException`).
- Docstring states exactly when it's raised.
- Lives in the module that owns the domain (`ConfigError` in `config.py`, not a separate `exceptions.py`).

## Raise vs exit

| Situation | Do |
|---|---|
| Inside `config.py`, `trainer.py`, `model.py`, etc. | **Raise.** Let the caller decide. |
| Inside `cli.py` dispatch | **Log + `sys.exit(N)`.** CLI is the top level. |
| Inside tests | **Assert.** Tests are tests. |
| Optional dep missing | **Raise `ImportError`** with install hint. See [architecture.md](architecture.md#3-optional-dependencies-are-extras-never-silent-imports). |

**Never `sys.exit()` from a non-CLI module.** That hides the error from callers, tests, and the library use case.

## Validation errors from Pydantic

Pydantic raises `ValidationError`. In `cli.py`:

```python
try:
    config = ForgeConfig.load(args.config)
except ValidationError as e:
    logger.error("Configuration error:\n%s", e)
    sys.exit(EXIT_CONFIG_ERROR)
except FileNotFoundError:
    logger.error("Config file not found: %s", args.config)
    sys.exit(EXIT_CONFIG_ERROR)
```

**Do not** bare-catch `Exception` at the CLI level. Known failure modes get dedicated branches; unknown failures should bubble up with a traceback (that's a bug we want to see).

## try/except patterns

### Acceptable

```python
# Narrow, documented, caller-specific recovery:
try:
    import wandb
except ImportError as e:
    raise ImportError(
        "W&B tracking requires the 'tracking' extra. "
        "Install with: pip install 'forgelm[tracking]'"
    ) from e
```

```python
# Converting a third-party exception to a domain exception:
try:
    response = requests.post(webhook_url, json=payload, timeout=10)
    response.raise_for_status()
except requests.RequestException as e:
    logger.warning("Webhook delivery failed: %s", e)
    # Webhook failures never abort training.
```

### Rejected

```python
# ❌ Silent swallowing
try:
    do_critical_thing()
except Exception:
    pass

# ❌ Bare except (also caught by ruff B/E9)
try:
    x()
except:
    ...

# ❌ Catch and rewrap without context
try:
    risky()
except Exception as e:
    raise RuntimeError("something failed")  # lost: from e
```

**Rule:** If you `except`, you must either (a) recover with a known-good fallback, (b) log and re-raise with `from e`, or (c) convert to a domain exception with `from e`. "Log and swallow" is a bug unless the failure is explicitly non-fatal (webhooks, cleanup).

## User-facing error messages

The audience is an engineer reading a CLI terminal in the dark. Messages must be:

1. **Specific about what.** "YAML file is invalid" — no. "`training.trainer_type` must be one of sft/dpo/simpo/kto/orpo/grpo, got 'spo'" — yes.
2. **Actionable.** State what the user should do. Include the config key, the expected value range, or the command to run.
3. **Not apologetic.** "Oops!" and "Sorry, but" — delete.
4. **Plain English, not jargon.** "CUDA OOM at layer 12" is fine; "Tensor RANK-42 exception in autograd graph" is not.

Template:

```
<what failed> : <key/location> : <why> : <how to fix>

Example:
  Configuration error : training.trainer_type : value 'spo' not recognized :
  must be one of [sft, dpo, simpo, kto, orpo, grpo]. See docs/reference/configuration.md.
```

## Auto-revert

When evaluation gates fail after training (`safety.py`, `benchmark.py`), `trainer.py` deletes the trained artifacts and exits with `EXIT_EVAL_FAILURE` (3). This is a feature, not an error:

- The audit log entry explaining **why** the model was reverted must be written before cleanup.
- The model card must **not** be generated for reverted runs.
- The webhook notification must fire with `status: "failed"` and the reason.

Reverting is a deliberate gate, not a panic. Treat it that way.

## What errors look like in JSON output

When `--output-format json` is set, errors still go to stdout as a single JSON object:

```json
{
  "status": "error",
  "exit_code": 1,
  "error_type": "ConfigError",
  "message": "training.trainer_type must be one of [sft, dpo, simpo, kto, orpo, grpo], got 'spo'",
  "details": {"field": "training.trainer_type", "value": "spo"}
}
```

Human-friendly logs still go to **stderr**. Pipeline consumers read stdout. Never mix the two.

## Testing error paths

Every custom exception and every non-zero exit path must have a test. See [testing.md](testing.md) for structure. Pattern:

```python
def test_invalid_trainer_type_raises_config_error(tmp_path):
    config_path = tmp_path / "bad.yaml"
    config_path.write_text("training:\n  trainer_type: spo\n...")

    result = subprocess.run(
        ["forgelm", "--config", str(config_path), "--dry-run"],
        capture_output=True, text=True
    )
    assert result.returncode == 1  # EXIT_CONFIG_ERROR
    assert "trainer_type" in result.stderr
```

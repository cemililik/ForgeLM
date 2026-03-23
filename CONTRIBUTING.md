# Contributing to ForgeLM

Thanks for your interest in contributing! ForgeLM is an open-source project and we welcome contributions of all kinds.

## Ways to Contribute

- **Bug reports** — found something broken? [Open a bug report](https://github.com/cemililik/ForgeLM/issues/new?template=bug_report.yml)
- **Feature requests** — have an idea? [Open a feature request](https://github.com/cemililik/ForgeLM/issues/new?template=feature_request.yml)
- **Code** — fix a bug, add a feature, improve tests
- **Documentation** — fix typos, improve guides, add examples
- **Notebooks** — add Colab notebooks for new use cases
- **Config templates** — share training configs that worked well for you

## Quick Start for Code Contributors

### 1. Fork & Clone

```bash
git clone https://github.com/YOUR_USERNAME/ForgeLM.git
cd ForgeLM
```

### 2. Install (dev mode)

```bash
python3 -m pip install -e ".[dev]"
```

### 3. Create a branch

```bash
git checkout -b fix/my-bugfix
# or
git checkout -b feat/my-feature
```

### 4. Make your changes

Edit the code, then verify:

```bash
# Run tests
pytest tests/ -q

# Run linter
ruff check .

# Check formatting
ruff format --check .

# Quick smoke test
forgelm --config config_template.yaml --dry-run
```

### 5. Submit a PR

Push your branch and open a Pull Request against `main`. The PR template will guide you through the checklist.

## Development Setup

### Project Structure

```
forgelm/
├── cli.py           # CLI entry point
├── config.py        # Pydantic config models
├── data.py          # Dataset loading
├── model.py         # Model + LoRA setup
├── trainer.py       # Training orchestration
├── results.py       # TrainResult dataclass
├── benchmark.py     # lm-eval-harness
├── safety.py        # Safety evaluation
├── judge.py         # LLM-as-Judge
├── compliance.py    # EU AI Act artifacts
├── model_card.py    # Model card generation
├── merging.py       # Model merging (TIES/DARE/SLERP)
├── wizard.py        # Interactive config wizard
├── webhook.py       # Notifications
└── utils.py         # Auth & checkpoints

tests/               # 17 test files, 179+ tests
notebooks/           # 5 Colab notebooks
configs/deepspeed/   # ZeRO presets
docs/guides/         # 6 user guides
```

### Running Tests

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_config.py -v

# With coverage
pytest tests/ --cov=forgelm --cov-report=term-missing
```

Some tests require `torch` and are skipped when it's not installed. This is expected in lightweight dev environments.

### Code Style

We use [ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
# Check
ruff check .
ruff format --check .

# Auto-fix
ruff check --fix .
ruff format .
```

Configuration is in `pyproject.toml` under `[tool.ruff]`.

## Guidelines

### Code

- **Keep it simple.** ForgeLM's strength is simplicity. Don't add complexity unless necessary.
- **Config-driven.** New features should be configurable via YAML. No hardcoded behavior.
- **Optional dependencies.** Heavy dependencies go in optional groups: `pip install forgelm[feature]`.
- **Tests required.** Every new feature or bugfix needs a test. We have 179+ tests — keep it growing.
- **Ruff clean.** CI will reject code that doesn't pass `ruff check`.
- **No secrets.** Never commit tokens, API keys, or credentials. Use env vars.

### Config Changes

If you add a new config field:

1. Add the field to the Pydantic model in `config.py`
2. Add it to `config_template.yaml` (commented with example)
3. Update the [Configuration Guide](docs/configuration.md) if it's user-facing
4. Add a test in `tests/test_config.py`

### Adding a New Trainer Type

1. Add the type to `valid_trainers` set in `config.py`
2. Add trainer-specific parameters to `TrainingConfig`
3. Add the TRL config builder in `trainer.py:_get_training_args_for_type()`
4. Add the trainer initialization in `trainer.py:train()`
5. Add dataset format detection in `data.py`
6. Update the wizard in `wizard.py`
7. Add tests in `tests/test_alignment.py`
8. Add a notebook in `notebooks/`

### Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add KTO trainer support
fix: handle NaN eval_loss in auto-revert
docs: add GRPO notebook example
test: add merging algorithm tests
chore: update CI to Python 3.13
style: apply ruff format
```

## First-Time Contributors

Look for issues labeled [`good first issue`](https://github.com/cemililik/ForgeLM/labels/good%20first%20issue). These are designed to be approachable for newcomers.

## Questions?

- **GitHub Discussions** — [Ask a question](https://github.com/cemililik/ForgeLM/discussions)
- **Issues** — [Report a bug or request a feature](https://github.com/cemililik/ForgeLM/issues)

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).

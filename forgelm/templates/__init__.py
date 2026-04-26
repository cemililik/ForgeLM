"""Bundled quickstart templates.

Each sub-directory is a self-contained template:
- ``config.yaml`` — the YAML config quickstart materializes from
- ``data.jsonl`` — the bundled seed dataset (some templates ship without one)
- optional ``README.md`` — template-specific notes

The Python registry lives in :mod:`forgelm.quickstart`. This package only
exists so ``importlib.resources`` / ``Path(__file__).parent`` resolve correctly
when ForgeLM is installed via wheel.
"""

"""Shared factories for ForgeLM tests.

Single source of truth for the canonical "minimal valid config" dict shape.
Test modules either:

- Receive the factory via the ``minimal_config`` pytest fixture in
  ``tests/conftest.py`` (preferred for new tests), or
- Import it directly via ``from tests._helpers.factories import minimal_config``
  (kept stable for non-pytest callers).

Per the testing standard (``docs/standards/testing.md``):

    Factory functions over static fixtures. ``minimal_config(training={...})``
    is better than 50 parametrized fixtures.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


def minimal_config(**overrides: Any) -> Dict[str, Any]:
    """Build the smallest valid ``ForgeConfig`` dict for testing.

    Returns a fresh dict on every call (deepcopy of the canonical defaults
    so mutations by callers cannot leak between tests). Top-level overrides
    replace the corresponding section wholesale; merge sub-keys yourself if
    you need partial updates.
    """
    data: Dict[str, Any] = deepcopy(
        {
            "model": {"name_or_path": "org/model"},
            "lora": {},
            "training": {},
            "data": {"dataset_name_or_path": "org/dataset"},
        }
    )
    data.update(overrides)
    return data

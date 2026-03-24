"""Shared test fixtures and utilities for ForgeLM tests."""


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

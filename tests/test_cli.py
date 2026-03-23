"""Unit tests for forgelm.cli module."""
import os
import sys
import pytest
from unittest.mock import patch
from io import StringIO

from forgelm.cli import (
    _get_version,
    _setup_logging,
    _run_dry_run,
    EXIT_SUCCESS,
    EXIT_CONFIG_ERROR,
    EXIT_TRAINING_ERROR,
    EXIT_EVAL_FAILURE,
    main,
)
from forgelm.config import ForgeConfig


def _minimal_config_dict():
    return {
        "model": {"name_or_path": "org/model"},
        "lora": {},
        "training": {},
        "data": {"dataset_name_or_path": "org/dataset"},
    }


class TestExitCodes:
    def test_exit_code_values(self):
        assert EXIT_SUCCESS == 0
        assert EXIT_CONFIG_ERROR == 1
        assert EXIT_TRAINING_ERROR == 2
        assert EXIT_EVAL_FAILURE == 3


class TestGetVersion:
    def test_returns_string(self):
        v = _get_version()
        assert isinstance(v, str)
        assert len(v) > 0


class TestSetupLogging:
    def test_setup_does_not_raise(self):
        _setup_logging("DEBUG")
        _setup_logging("INFO")
        _setup_logging("WARNING")
        _setup_logging("ERROR")


class TestDryRun:
    def test_dry_run_minimal_config(self):
        config = ForgeConfig(**_minimal_config_dict())
        # Should not raise
        _run_dry_run(config)

    def test_dry_run_with_evaluation(self):
        data = _minimal_config_dict()
        data["evaluation"] = {"auto_revert": True, "max_acceptable_loss": 2.0}
        config = ForgeConfig(**data)
        _run_dry_run(config)

    def test_dry_run_with_webhook(self):
        data = _minimal_config_dict()
        data["webhook"] = {"url": "https://example.com/hook"}
        config = ForgeConfig(**data)
        _run_dry_run(config)

    def test_dry_run_trust_remote_code_warning(self):
        data = _minimal_config_dict()
        data["model"]["trust_remote_code"] = True
        config = ForgeConfig(**data)
        _run_dry_run(config)


class TestMainEntrypoint:
    def test_missing_config_exits(self):
        with patch("sys.argv", ["forgelm"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == EXIT_CONFIG_ERROR

    def test_nonexistent_config_exits(self):
        with patch("sys.argv", ["forgelm", "--config", "/nonexistent/file.yaml"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == EXIT_CONFIG_ERROR

    def test_dry_run_exits_success(self, tmp_path):
        import yaml
        cfg_path = str(tmp_path / "config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump(_minimal_config_dict(), f)

        with patch("sys.argv", ["forgelm", "--config", cfg_path, "--dry-run"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == EXIT_SUCCESS

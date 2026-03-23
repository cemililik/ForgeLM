"""Unit tests for CLI subcommands (--merge, --compliance-export, --benchmark-only)."""

import json
import os
from unittest.mock import patch

import pytest
import yaml

from forgelm.cli import (
    EXIT_CONFIG_ERROR,
    EXIT_SUCCESS,
    _run_compliance_export,
    main,
)
from forgelm.config import ForgeConfig


def _minimal_config(**overrides):
    data = {
        "model": {"name_or_path": "org/model"},
        "lora": {},
        "training": {},
        "data": {"dataset_name_or_path": "org/dataset"},
    }
    data.update(overrides)
    return data


class TestComplianceExportCLI:
    def test_compliance_export_creates_files(self, tmp_path):
        config = ForgeConfig(**_minimal_config())
        output_dir = str(tmp_path / "compliance")
        _run_compliance_export(config, output_dir, "text")

        assert os.path.isfile(os.path.join(output_dir, "compliance_report.json"))
        assert os.path.isfile(os.path.join(output_dir, "training_manifest.yaml"))
        assert os.path.isfile(os.path.join(output_dir, "data_provenance.json"))

    def test_compliance_export_json_output(self, tmp_path, capsys):
        config = ForgeConfig(**_minimal_config())
        output_dir = str(tmp_path / "compliance")
        _run_compliance_export(config, output_dir, "json")

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["success"] is True
        assert len(result["files"]) == 3

    def test_compliance_export_via_main(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        output_dir = str(tmp_path / "audit")
        with open(cfg_path, "w") as f:
            yaml.dump(_minimal_config(), f)

        with patch("sys.argv", ["forgelm", "--config", cfg_path, "--compliance-export", output_dir]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == EXIT_SUCCESS

        assert os.path.isdir(output_dir)


class TestMergeCLI:
    def test_merge_without_config_exits(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump(_minimal_config(), f)

        with patch("sys.argv", ["forgelm", "--config", cfg_path, "--merge"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == EXIT_CONFIG_ERROR

    def test_merge_with_disabled_config_exits(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        data = _minimal_config(merge={"enabled": False})
        with open(cfg_path, "w") as f:
            yaml.dump(data, f)

        with patch("sys.argv", ["forgelm", "--config", cfg_path, "--merge"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == EXIT_CONFIG_ERROR

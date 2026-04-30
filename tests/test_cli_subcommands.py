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


class TestComplianceExportCLI:
    def test_compliance_export_creates_files(self, tmp_path, minimal_config):
        config = ForgeConfig(**minimal_config())
        output_dir = str(tmp_path / "compliance")
        _run_compliance_export(config, output_dir, "text")

        assert os.path.isfile(os.path.join(output_dir, "compliance_report.json"))
        assert os.path.isfile(os.path.join(output_dir, "training_manifest.yaml"))
        assert os.path.isfile(os.path.join(output_dir, "data_provenance.json"))

    def test_compliance_export_json_output(self, tmp_path, capsys, minimal_config):
        config = ForgeConfig(**minimal_config())
        output_dir = str(tmp_path / "compliance")
        _run_compliance_export(config, output_dir, "json")

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["success"] is True
        assert len(result["files"]) == 3

    def test_compliance_export_via_main(self, tmp_path, minimal_config):
        cfg_path = str(tmp_path / "config.yaml")
        output_dir = str(tmp_path / "audit")
        with open(cfg_path, "w") as f:
            yaml.dump(minimal_config(), f)

        with patch("sys.argv", ["forgelm", "--config", cfg_path, "--compliance-export", output_dir]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == EXIT_SUCCESS

        assert os.path.isdir(output_dir)


class TestMergeCLI:
    def test_merge_without_config_exits(self, tmp_path, minimal_config):
        cfg_path = str(tmp_path / "config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump(minimal_config(), f)

        with patch("sys.argv", ["forgelm", "--config", cfg_path, "--merge"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == EXIT_CONFIG_ERROR

    def test_merge_with_disabled_config_exits(self, tmp_path, minimal_config):
        cfg_path = str(tmp_path / "config.yaml")
        data = minimal_config(merge={"enabled": False})
        with open(cfg_path, "w") as f:
            yaml.dump(data, f)

        with patch("sys.argv", ["forgelm", "--config", cfg_path, "--merge"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == EXIT_CONFIG_ERROR


class TestAuditSubcommand:
    """Phase 11.5: `forgelm audit PATH` subcommand + legacy `--data-audit` alias."""

    def _make_jsonl(self, path, rows):
        with open(path, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def test_audit_subcommand_writes_report(self, tmp_path):
        data_path = tmp_path / "data.jsonl"
        self._make_jsonl(data_path, [{"text": "alpha"}, {"text": "beta"}])
        out_dir = tmp_path / "audit"

        with patch(
            "sys.argv",
            ["forgelm", "audit", str(data_path), "--output", str(out_dir)],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == EXIT_SUCCESS

        assert (out_dir / "data_audit_report.json").is_file()

    def test_audit_subcommand_json_envelope(self, tmp_path, capsys):
        data_path = tmp_path / "data.jsonl"
        self._make_jsonl(data_path, [{"text": "alpha"}])
        out_dir = tmp_path / "audit"

        with patch(
            "sys.argv",
            [
                "forgelm",
                "audit",
                str(data_path),
                "--output",
                str(out_dir),
                "--output-format",
                "json",
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == EXIT_SUCCESS

        envelope = json.loads(capsys.readouterr().out)
        assert envelope["success"] is True
        assert "pii_severity" in envelope
        assert envelope["report_path"].endswith("data_audit_report.json")

    def test_legacy_data_audit_flag_still_works(self, tmp_path):
        data_path = tmp_path / "data.jsonl"
        self._make_jsonl(data_path, [{"text": "legacy alias still routes here"}])
        out_dir = tmp_path / "audit"

        with patch(
            "sys.argv",
            ["forgelm", "--data-audit", str(data_path), "--output", str(out_dir)],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == EXIT_SUCCESS

        # Same on-disk product as the subcommand path.
        assert (out_dir / "data_audit_report.json").is_file()

    def test_audit_quality_filter_flag(self, tmp_path):
        # Phase 12: --quality-filter populates quality_summary.
        data_path = tmp_path / "data.jsonl"
        self._make_jsonl(
            data_path,
            [{"text": "1234567890 !@#$%^&*()"}, {"text": "fine prose passes the heuristics."}],
        )
        out_dir = tmp_path / "audit"

        with patch(
            "sys.argv",
            ["forgelm", "audit", str(data_path), "--output", str(out_dir), "--quality-filter"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == EXIT_SUCCESS

        with open(out_dir / "data_audit_report.json", encoding="utf-8") as fh:
            report = json.load(fh)
        assert "quality_summary" in report
        assert report["quality_summary"].get("samples_flagged", 0) >= 1

    def test_audit_rejects_invalid_jaccard_threshold(self, tmp_path):
        # Phase 12: --jaccard-threshold enforces [0.0, 1.0] at parse-time.
        data_path = tmp_path / "data.jsonl"
        self._make_jsonl(data_path, [{"text": "alpha"}])

        with patch(
            "sys.argv",
            ["forgelm", "audit", str(data_path), "--jaccard-threshold", "1.5"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            # argparse error → exit code 2 (its standard convention).
            assert exc_info.value.code == 2

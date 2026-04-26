"""Tests for Phase 10 CLI additions: chat/export/deploy subcommands and --fit-check."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
import yaml

from forgelm.cli import (
    EXIT_CONFIG_ERROR,
    EXIT_SUCCESS,
    EXIT_TRAINING_ERROR,
    _run_fit_check,
    main,
)
from forgelm.config import ForgeConfig


def _minimal_cfg_dict(**overrides):
    data = {
        "model": {"name_or_path": "org/model"},
        "lora": {},
        "training": {},
        "data": {"dataset_name_or_path": "org/dataset"},
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# --fit-check flag
# ---------------------------------------------------------------------------


class TestFitCheckFlag:
    def test_fit_check_text_output(self, tmp_path, capsys):
        cfg_path = str(tmp_path / "config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump(_minimal_cfg_dict(), f)

        torch_stub = MagicMock()
        torch_stub.cuda.is_available.return_value = False

        transformers_stub = MagicMock()
        transformers_stub.AutoConfig.from_pretrained.return_value = MagicMock(
            hidden_size=4096,
            num_hidden_layers=32,
            intermediate_size=11008,
            vocab_size=32000,
            num_attention_heads=32,
            num_key_value_heads=32,
        )

        with patch("sys.argv", ["forgelm", "--config", cfg_path, "--fit-check"]):
            with patch.dict(sys.modules, {"torch": torch_stub, "transformers": transformers_stub}):
                with pytest.raises(SystemExit) as exc_info:
                    main()
        assert exc_info.value.code == EXIT_SUCCESS

        captured = capsys.readouterr()
        assert "VRAM Fit Check" in captured.out or "UNKNOWN" in captured.out

    def test_fit_check_json_output(self, tmp_path, capsys):
        cfg_path = str(tmp_path / "config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump(_minimal_cfg_dict(), f)

        torch_stub = MagicMock()
        torch_stub.cuda.is_available.return_value = False

        transformers_stub = MagicMock()
        transformers_stub.AutoConfig.from_pretrained.return_value = MagicMock(
            hidden_size=4096,
            num_hidden_layers=32,
            intermediate_size=11008,
            vocab_size=32000,
            num_attention_heads=32,
            num_key_value_heads=32,
        )

        with patch("sys.argv", ["forgelm", "--config", cfg_path, "--fit-check", "--output-format", "json"]):
            with patch.dict(sys.modules, {"torch": torch_stub, "transformers": transformers_stub}):
                with pytest.raises(SystemExit) as exc_info:
                    main()
        assert exc_info.value.code == EXIT_SUCCESS

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert "verdict" in result
        assert "estimated_gb" in result
        assert "breakdown" in result

    def test_fit_check_without_config_fails(self):
        with patch("sys.argv", ["forgelm", "--fit-check"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == EXIT_CONFIG_ERROR


# ---------------------------------------------------------------------------
# forgelm deploy subcommand
# ---------------------------------------------------------------------------


class TestDeployCLI:
    def test_deploy_ollama_exits_success(self, tmp_path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        out = str(tmp_path / "Modelfile")
        with patch("sys.argv", ["forgelm", "deploy", str(model_dir), "--target", "ollama", "--output", out]):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == EXIT_SUCCESS
        assert os.path.isfile(out)

    def test_deploy_vllm_exits_success(self, tmp_path):
        out = str(tmp_path / "vllm.yaml")
        # vllm accepts HF Hub IDs; no local-path validation
        with patch("sys.argv", ["forgelm", "deploy", "./model", "--target", "vllm", "--output", out]):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == EXIT_SUCCESS

    def test_deploy_tgi_exits_success(self, tmp_path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        out = str(tmp_path / "docker-compose.yaml")
        with patch("sys.argv", ["forgelm", "deploy", str(model_dir), "--target", "tgi", "--output", out]):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == EXIT_SUCCESS

    def test_deploy_hf_endpoints_exits_success(self, tmp_path):
        out = str(tmp_path / "endpoint.json")
        # hf-endpoints expects HF Hub repo IDs; no local-path validation
        with patch("sys.argv", ["forgelm", "deploy", "./model", "--target", "hf-endpoints", "--output", out]):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == EXIT_SUCCESS

    def test_deploy_bad_target_exits_error(self, tmp_path):
        out = str(tmp_path / "out.cfg")
        with patch("sys.argv", ["forgelm", "deploy", "./model", "--target", "bogus", "--output", out]):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == EXIT_TRAINING_ERROR

    def test_deploy_json_output(self, tmp_path, capsys):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        out = str(tmp_path / "Modelfile")
        with patch(
            "sys.argv",
            ["forgelm", "--output-format", "json", "deploy", str(model_dir), "--target", "ollama", "--output", out],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == EXIT_SUCCESS

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["success"] is True
        assert result["target"] == "ollama"

    def test_deploy_with_system_prompt(self, tmp_path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        out = str(tmp_path / "Modelfile")
        with patch(
            "sys.argv",
            [
                "forgelm",
                "deploy",
                str(model_dir),
                "--target",
                "ollama",
                "--output",
                out,
                "--system",
                "You are helpful.",
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == EXIT_SUCCESS
        with open(out) as f:
            content = f.read()
        assert "You are helpful." in content

    def test_deploy_does_not_require_config(self, tmp_path):
        """forgelm deploy must work without --config."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        out = str(tmp_path / "Modelfile")
        with patch("sys.argv", ["forgelm", "deploy", str(model_dir), "--target", "ollama", "--output", out]):
            with pytest.raises(SystemExit) as exc_info:
                main()
        # Must exit with success, not CONFIG_ERROR
        assert exc_info.value.code != EXIT_CONFIG_ERROR


# ---------------------------------------------------------------------------
# forgelm export subcommand
# ---------------------------------------------------------------------------


class TestExportCLI:
    def test_export_missing_llama_cpp_exits_error(self, tmp_path):
        out = str(tmp_path / "model.gguf")
        with patch.dict(sys.modules, {"llama_cpp": None}):
            with patch("sys.argv", ["forgelm", "export", "./model", "--output", out]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
        assert exc_info.value.code == EXIT_TRAINING_ERROR

    def test_export_json_on_failure(self, tmp_path, capsys):
        out = str(tmp_path / "model.gguf")
        with patch.dict(sys.modules, {"llama_cpp": None}):
            with patch(
                "sys.argv",
                [
                    "forgelm",
                    "--output-format",
                    "json",
                    "export",
                    "./model",
                    "--output",
                    out,
                ],
            ):
                with pytest.raises(SystemExit) as exc_info:
                    main()

        assert exc_info.value.code == EXIT_TRAINING_ERROR
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["success"] is False

    def test_export_does_not_require_config(self, tmp_path):
        """forgelm export must work without --config."""
        out = str(tmp_path / "model.gguf")
        with patch.dict(sys.modules, {"llama_cpp": None}):
            with patch("sys.argv", ["forgelm", "export", "./model", "--output", out]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
        # Error because llama_cpp missing — but NOT CONFIG_ERROR
        assert exc_info.value.code != EXIT_CONFIG_ERROR

    def test_export_success_path(self, tmp_path):
        out = str(tmp_path / "model.gguf")

        llama_cpp_stub = MagicMock()
        pkg_dir = str(tmp_path / "llama_cpp")
        os.makedirs(pkg_dir, exist_ok=True)
        llama_cpp_stub.__file__ = os.path.join(pkg_dir, "__init__.py")
        open(os.path.join(pkg_dir, "convert_hf_to_gguf.py"), "w").close()

        def fake_run(cmd, **kwargs):
            actual = cmd[cmd.index("--outfile") + 1] if "--outfile" in cmd else out
            with open(actual, "wb") as f:
                f.write(b"gguf data")
            m = MagicMock()
            m.returncode = 0
            m.stderr = ""
            return m

        with patch.dict(sys.modules, {"llama_cpp": llama_cpp_stub}):
            with patch("subprocess.run", side_effect=fake_run):
                with patch(
                    "sys.argv",
                    ["forgelm", "export", str(tmp_path), "--output", out, "--quant", "q8_0"],
                ):
                    with pytest.raises(SystemExit) as exc_info:
                        main()

        assert exc_info.value.code == EXIT_SUCCESS


# ---------------------------------------------------------------------------
# forgelm chat subcommand (smoke tests; no actual model loaded)
# ---------------------------------------------------------------------------


class TestChatCLI:
    def test_chat_does_not_require_config(self):
        """Running forgelm chat without --config must not exit with CONFIG_ERROR."""
        with patch("forgelm.cli._run_chat_cmd", side_effect=KeyboardInterrupt):
            with patch("sys.argv", ["forgelm", "chat", "./model"]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
        # Should be SUCCESS (KeyboardInterrupt handled gracefully in _run_chat_cmd)
        assert exc_info.value.code != EXIT_CONFIG_ERROR

    def test_chat_subcommand_registered(self, capsys):
        """forgelm chat --help must succeed and document model_path."""
        with patch("sys.argv", ["forgelm", "chat", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "model_path" in captured.out


# ---------------------------------------------------------------------------
# _run_fit_check helper
# ---------------------------------------------------------------------------


class TestRunFitCheckHelper:
    def test_text_output_contains_verdict(self, capsys):
        from forgelm.fit_check import FitCheckResult

        mock_result = FitCheckResult(
            verdict="FITS",
            estimated_gb=7.5,
            available_gb=24.0,
            recommendations=[],
            breakdown={"base_model_gb": 4.5},
        )

        cfg = ForgeConfig(**_minimal_cfg_dict())
        with patch("forgelm.fit_check.estimate_vram", return_value=mock_result):
            _run_fit_check(cfg, "text")

        captured = capsys.readouterr()
        assert "FITS" in captured.out

    def test_json_output_structure(self, capsys):
        from forgelm.fit_check import FitCheckResult

        mock_result = FitCheckResult(
            verdict="OOM",
            estimated_gb=35.0,
            available_gb=12.0,
            recommendations=["Reduce batch size"],
            breakdown={"base_model_gb": 18.0},
        )

        cfg = ForgeConfig(**_minimal_cfg_dict())
        with patch("forgelm.fit_check.estimate_vram", return_value=mock_result):
            _run_fit_check(cfg, "json")

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["verdict"] == "OOM"
        assert result["estimated_gb"] == pytest.approx(35.0)
        assert result["recommendations"] == ["Reduce batch size"]


# ---------------------------------------------------------------------------
# Subcommand routing (no training flow triggered)
# ---------------------------------------------------------------------------


class TestSubcommandRouting:
    def test_existing_flags_unchanged_after_subcommand_addition(self, tmp_path):
        """--dry-run must still work without interference from subparsers."""
        cfg_path = str(tmp_path / "config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump(_minimal_cfg_dict(), f)

        with patch("sys.argv", ["forgelm", "--config", cfg_path, "--dry-run"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == EXIT_SUCCESS

    def test_wizard_still_works(self):
        """--wizard flow must be unaffected."""
        mock_wizard = MagicMock(return_value=None)
        with patch("forgelm.wizard.run_wizard", mock_wizard):
            with patch("sys.argv", ["forgelm", "--wizard"]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
        assert exc_info.value.code == EXIT_SUCCESS

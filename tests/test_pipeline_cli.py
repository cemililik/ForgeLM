"""Phase 14 — CLI flag interaction + dispatcher tests.

Covers :func:`forgelm.cli._pipeline.run_pipeline_from_args`, the argparse
glue layer between the top-level parser and
:class:`forgelm.cli._pipeline.PipelineOrchestrator`.  Focus: flag
combinatorial rules + dispatch routing.  The orchestrator's own state
machine has dedicated coverage in ``tests/test_pipeline_orchestrator.py``;
this file pins the *boundary* between argparse and the orchestrator.
"""

from __future__ import annotations

import argparse
import os
import types
from unittest.mock import MagicMock

from forgelm.cli._exit_codes import EXIT_CONFIG_ERROR, EXIT_SUCCESS
from forgelm.cli._pipeline import run_pipeline_from_args
from forgelm.config import ForgeConfig
from forgelm.results import TrainResult


def _three_stage_cfg(tmp_path):
    return ForgeConfig(
        model={"name_or_path": "org/base"},
        lora={"r": 8},
        training={"trainer_type": "sft"},
        data={"dataset_name_or_path": "org/data"},
        pipeline={
            "output_dir": str(tmp_path / "pipeline_run"),
            "stages": [
                {
                    "name": "sft_stage",
                    "training": {"trainer_type": "sft", "output_dir": str(tmp_path / "stage1")},
                    "data": {"dataset_name_or_path": "org/sft"},
                },
                {
                    "name": "dpo_stage",
                    "training": {"trainer_type": "dpo", "output_dir": str(tmp_path / "stage2")},
                    "data": {"dataset_name_or_path": "org/dpo"},
                },
                {
                    "name": "grpo_stage",
                    "training": {"trainer_type": "grpo", "output_dir": str(tmp_path / "stage3")},
                    "data": {"dataset_name_or_path": "org/math"},
                },
            ],
        },
    )


def _ns(**overrides):
    """Build an argparse.Namespace with the orchestrator-relevant fields."""
    defaults = dict(
        stage=None,
        resume_from=None,
        force_resume=False,
        input_model=None,
        output_format="text",
        dry_run=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _install_fake_trainer(monkeypatch, results):
    iterator = iter(results)

    class _FakeForgeTrainer:
        def __init__(self, *, model, tokenizer, config, dataset):
            os.makedirs(os.path.join(config.training.output_dir, "final_model"), exist_ok=True)
            self.config = config

        def train(self, resume_from_checkpoint=None):
            try:
                return next(iterator)
            except StopIteration:
                return TrainResult(success=True)

    fake_trainer = types.ModuleType("forgelm.trainer")
    fake_trainer.ForgeTrainer = _FakeForgeTrainer
    monkeypatch.setitem(__import__("sys").modules, "forgelm.trainer", fake_trainer)

    fake_model = types.ModuleType("forgelm.model")
    fake_model.get_model_and_tokenizer = lambda config: (MagicMock(), MagicMock())
    monkeypatch.setitem(__import__("sys").modules, "forgelm.model", fake_model)

    fake_data = types.ModuleType("forgelm.data")
    fake_data.prepare_dataset = lambda config, tokenizer: {"train": [{"text": "x"}]}
    monkeypatch.setitem(__import__("sys").modules, "forgelm.data", fake_data)

    fake_utils = types.ModuleType("forgelm.utils")
    fake_utils.setup_authentication = lambda token: None
    monkeypatch.setitem(__import__("sys").modules, "forgelm.utils", fake_utils)


class TestFlagInteractionGuards:
    """Argparse alone cannot express "X and Y are mutually exclusive
    *only when both are non-None*"; the dispatcher enforces it."""

    def test_stage_and_resume_from_mutually_exclusive(self, tmp_path):
        cfg = _three_stage_cfg(tmp_path)
        args = _ns(stage="sft_stage", resume_from="dpo_stage")
        code = run_pipeline_from_args(cfg, b"yaml", args)
        assert code == EXIT_CONFIG_ERROR

    def test_input_model_requires_stage(self, tmp_path):
        cfg = _three_stage_cfg(tmp_path)
        args = _ns(input_model="some/path")
        code = run_pipeline_from_args(cfg, b"yaml", args)
        assert code == EXIT_CONFIG_ERROR

    def test_force_resume_without_resume_from_is_noop(self, tmp_path, monkeypatch):
        """``--force-resume`` without ``--resume-from`` is meaningless
        but not an error — the orchestrator simply ignores it on a
        fresh run.  We pin this so a future overzealous validator
        doesn't start rejecting harmless flag combinations."""
        cfg = _three_stage_cfg(tmp_path)
        _install_fake_trainer(
            monkeypatch, [TrainResult(success=True), TrainResult(success=True), TrainResult(success=True)]
        )
        args = _ns(force_resume=True)
        code = run_pipeline_from_args(cfg, b"yaml", args)
        assert code == EXIT_SUCCESS


class TestDispatchToDryRun:
    def test_dry_run_routes_to_orchestrator_dry_run(self, tmp_path, monkeypatch):
        """``--dry-run`` must take the dry-run branch even when other
        pipeline flags are set — keeps operators from accidentally
        kicking off a real run when they intended to validate."""
        cfg = _three_stage_cfg(tmp_path)
        _install_fake_trainer(monkeypatch, [])
        args = _ns(dry_run=True)
        code = run_pipeline_from_args(cfg, b"yaml", args)
        assert code == EXIT_SUCCESS
        # No state / manifest written by dry-run.
        assert not os.path.exists(tmp_path / "pipeline_run" / "pipeline_state.json")


class TestDispatchToRun:
    def test_full_run_routes_to_orchestrator_run(self, tmp_path, monkeypatch):
        cfg = _three_stage_cfg(tmp_path)
        _install_fake_trainer(monkeypatch, [TrainResult(success=True)] * 3)
        args = _ns()
        code = run_pipeline_from_args(cfg, b"yaml", args)
        assert code == EXIT_SUCCESS
        assert os.path.exists(tmp_path / "pipeline_run" / "pipeline_state.json")

    def test_stage_filter_propagates_to_orchestrator(self, tmp_path, monkeypatch):
        cfg = _three_stage_cfg(tmp_path)
        _install_fake_trainer(monkeypatch, [TrainResult(success=True)])
        args = _ns(stage="sft_stage")
        code = run_pipeline_from_args(cfg, b"yaml", args)
        assert code == EXIT_SUCCESS

    def test_unknown_stage_filter_rejected_via_orchestrator(self, tmp_path, monkeypatch):
        cfg = _three_stage_cfg(tmp_path)
        _install_fake_trainer(monkeypatch, [])
        args = _ns(stage="ghost")
        code = run_pipeline_from_args(cfg, b"yaml", args)
        assert code == EXIT_CONFIG_ERROR

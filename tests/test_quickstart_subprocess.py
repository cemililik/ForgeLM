"""Phase 10.5 UX hardening: subprocess argv + actionable error messages.

Two regressions covered here:

1. ``_resolve_dataset`` raises :class:`FileExistsError` when a per-run scratch
   directory is reused. The message must point the operator at a recovery path
   (``--dataset`` to reuse, or delete the file) instead of just blaming them.
2. ``_run_quickstart_cmd`` builds ``train_cmd`` and ``chat_cmd`` argv lists.
   The ``--config`` and the final-model-dir argument must be absolute paths so
   the child subprocess does not silently fail if the parent's cwd shifts
   between argv construction and ``subprocess.run``.

The ``_RunRecorder`` pattern is duplicated inline (per task instructions) so
this module stays independent of ``tests/test_cli_quickstart_wiring.py``.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest


class _RunRecorder:
    """Minimal stand-in for :func:`subprocess.run` that captures argv lists."""

    def __init__(self, returncodes: list[int] | None = None) -> None:
        self.returncodes = returncodes if returncodes is not None else [0, 0]
        self.calls: list[list[str]] = []

    def __call__(self, argv, *args, **kwargs):  # noqa: D401 — match subprocess.run
        self.calls.append(list(argv))
        idx = len(self.calls) - 1
        rc = self.returncodes[idx] if idx < len(self.returncodes) else 0

        class _Completed:
            returncode = rc

        return _Completed()


# ---------------------------------------------------------------------------
# 1. FileExistsError message must surface recovery actions
# ---------------------------------------------------------------------------


def test_file_exists_error_message_actionable(tmp_path: Path):
    """Reusing a scratch dir must yield an action-oriented FileExistsError."""
    from forgelm.quickstart import _resolve_dataset, get_template

    template = get_template("customer-support")
    scratch = tmp_path / "run-1"

    # First call seeds the dataset into the scratch dir.
    _resolve_dataset(template, dataset_override=None, scratch_dir=scratch)

    # Second call must refuse and explain what the user can do next.
    with pytest.raises(FileExistsError) as exc_info:
        _resolve_dataset(template, dataset_override=None, scratch_dir=scratch)

    msg = str(exc_info.value)
    assert "pass --dataset" in msg, f"Expected '--dataset' recovery hint in error message, got: {msg!r}"
    assert "delete" in msg, f"Expected 'delete' recovery hint in error message, got: {msg!r}"


# ---------------------------------------------------------------------------
# 2. train_cmd argv must use the absolute config path
# ---------------------------------------------------------------------------


def test_train_subprocess_uses_absolute_config_path(tmp_path: Path):
    """If parent cwd changes between argv build and exec, the child still finds the config."""
    from forgelm.cli import main

    config_out = tmp_path / "abs-path-test.yaml"
    recorder = _RunRecorder()

    # final_model_dir must look real so the chat block (also patched) is
    # exercised end-to-end. Without it, _run_quickstart_cmd would log a warning
    # and skip the chat subprocess — fine for this test, but explicit setup
    # keeps the harness uniform with the chat-path test below.
    final_dir = tmp_path / "checkpoints" / "final_model"
    final_dir.mkdir(parents=True)

    argv = [
        "forgelm",
        "quickstart",
        "customer-support",
        "--output",
        str(config_out),
    ]

    with (
        patch("forgelm.quickstart._detect_available_vram_gb", return_value=24.0),
        patch(
            "forgelm.cli._load_quickstart_train_paths",
            return_value=(str(tmp_path / "checkpoints"), "final_model"),
        ),
        patch("subprocess.run", new=recorder),
        patch("sys.argv", argv),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 0
    assert recorder.calls, "subprocess.run was never invoked"

    train_argv = recorder.calls[0]
    assert "--config" in train_argv, f"--config missing from train argv: {train_argv}"
    cfg_value = train_argv[train_argv.index("--config") + 1]
    assert os.path.isabs(cfg_value), f"Expected absolute --config path, got relative: {cfg_value!r}"
    assert cfg_value.endswith("abs-path-test.yaml"), f"Expected the configured output path, got: {cfg_value!r}"


# ---------------------------------------------------------------------------
# 3. chat_cmd argv must use the absolute final_model_dir path
# ---------------------------------------------------------------------------


def test_chat_subprocess_uses_absolute_model_path(tmp_path: Path):
    """The auto-launched chat REPL must receive an absolute model dir."""
    from forgelm.cli import main

    config_out = tmp_path / "abs-path-test.yaml"
    recorder = _RunRecorder()

    # Per task spec: hard-code the patched train paths to a fixed string and
    # force is_dir() True regardless of filesystem state.
    argv = [
        "forgelm",
        "quickstart",
        "customer-support",
        "--output",
        str(config_out),
    ]

    with (
        patch("forgelm.quickstart._detect_available_vram_gb", return_value=24.0),
        patch(
            "forgelm.cli._load_quickstart_train_paths",
            return_value=("/some/checkpoints", "final_model"),
        ),
        patch("pathlib.Path.is_dir", return_value=True),
        patch("subprocess.run", new=recorder),
        patch("sys.argv", argv),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 0
    assert len(recorder.calls) == 2, (
        f"Expected train + chat subprocess calls, got {len(recorder.calls)}: {recorder.calls}"
    )

    chat_argv = recorder.calls[1]
    # The model path is the final positional argument to ``chat``.
    assert "chat" in chat_argv, f"'chat' subcommand missing: {chat_argv}"
    model_path = chat_argv[-1]
    assert os.path.isabs(model_path), f"Expected absolute chat model path, got relative: {model_path!r}"
    assert model_path.endswith("final_model"), f"Expected path to end with 'final_model', got: {model_path!r}"

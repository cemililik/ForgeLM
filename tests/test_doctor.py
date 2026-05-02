"""Phase 34: ``forgelm doctor`` env-check subcommand.

Heavy on lightweight unit tests of individual probes (so a CI runner
without torch / GPU / network access can still exercise the doctor
surface), with one CLI subprocess smoke at the bottom.
"""

from __future__ import annotations

import json
import sys
from collections import namedtuple
from unittest.mock import MagicMock, patch

import pytest

# ``sys.version_info`` is a named tuple (`.major`/`.minor`/`.micro`/...);
# patching with a plain tuple breaks the attribute access in the probe.
# Build a structurally-equivalent fake we can pass to ``patch``.
_FakeVersionInfo = namedtuple("_FakeVersionInfo", ["major", "minor", "micro", "releaselevel", "serial"])


def _make_version(major: int, minor: int, micro: int = 0) -> _FakeVersionInfo:
    return _FakeVersionInfo(major, minor, micro, "final", 0)


# ``shutil.disk_usage`` returns a ``_ntuple_diskusage`` named tuple
# (`.total` / `.used` / `.free`).  Mirror it for the disk-space tests.
_FakeDiskUsage = namedtuple("_FakeDiskUsage", ["total", "used", "free"])

# ---------------------------------------------------------------------------
# Individual probes
# ---------------------------------------------------------------------------


class TestPythonVersionCheck:
    def test_python_310_warns(self) -> None:
        from forgelm.cli.subcommands._doctor import _check_python_version

        with patch("sys.version_info", _make_version(3, 10, 0)):
            result = _check_python_version()
        assert result.status == "warn"
        assert "3.11" in result.detail  # recommendation appears

    def test_python_311_passes(self) -> None:
        from forgelm.cli.subcommands._doctor import _check_python_version

        with patch("sys.version_info", _make_version(3, 11, 5)):
            result = _check_python_version()
        assert result.status == "pass"
        assert "3.11.5" in result.detail

    def test_python_312_passes(self) -> None:
        from forgelm.cli.subcommands._doctor import _check_python_version

        with patch("sys.version_info", _make_version(3, 12, 1)):
            result = _check_python_version()
        assert result.status == "pass"

    def test_python_39_fails(self) -> None:
        from forgelm.cli.subcommands._doctor import _check_python_version

        with patch("sys.version_info", _make_version(3, 9, 7)):
            result = _check_python_version()
        assert result.status == "fail"
        assert "3.10" in result.detail
        assert "below" in result.detail.lower()


class TestTorchCudaCheck:
    def test_no_torch_fails(self) -> None:
        """When torch is not importable doctor must surface a clear fail
        (not crash)."""
        import builtins

        from forgelm.cli.subcommands import _doctor

        original_import = builtins.__import__

        def _block_torch(name, *args, **kwargs):
            if name == "torch":
                raise ImportError("No module named 'torch'")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _block_torch):
            result = _doctor._check_torch_cuda()
        assert result.status == "fail"
        assert "torch" in result.detail.lower()

    def test_torch_cpu_only_warns(self) -> None:
        """CPU-only torch is supported but warned (training will be slow)."""
        from forgelm.cli.subcommands._doctor import _check_torch_cuda

        fake_torch = MagicMock()
        fake_torch.__version__ = "2.5.0"
        fake_torch.cuda.is_available.return_value = False
        fake_torch.version.cuda = None
        with patch.dict("sys.modules", {"torch": fake_torch}):
            result = _check_torch_cuda()
        assert result.status == "warn"
        assert "CPU-only" in result.detail or "cpu-only" in result.detail.lower()

    def test_torch_cuda_passes(self) -> None:
        from forgelm.cli.subcommands._doctor import _check_torch_cuda

        fake_torch = MagicMock()
        fake_torch.__version__ = "2.5.0"
        fake_torch.cuda.is_available.return_value = True
        fake_torch.version.cuda = "12.4"
        with patch.dict("sys.modules", {"torch": fake_torch}):
            result = _check_torch_cuda()
        assert result.status == "pass"
        assert "12.4" in result.detail


class TestGpuInventoryCheck:
    def test_no_torch_fails(self) -> None:
        import builtins

        from forgelm.cli.subcommands import _doctor

        original_import = builtins.__import__

        def _block_torch(name, *args, **kwargs):
            if name == "torch":
                raise ImportError("nope")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _block_torch):
            result = _doctor._check_gpu_inventory()
        assert result.status == "fail"

    def test_no_cuda_warns(self) -> None:
        from forgelm.cli.subcommands._doctor import _check_gpu_inventory

        fake_torch = MagicMock()
        fake_torch.cuda.is_available.return_value = False
        with patch.dict("sys.modules", {"torch": fake_torch}):
            result = _check_gpu_inventory()
        assert result.status == "warn"
        assert result.extras["device_count"] == 0

    def test_two_gpus_pass_with_inventory(self) -> None:
        from forgelm.cli.subcommands._doctor import _check_gpu_inventory

        fake_torch = MagicMock()
        fake_torch.cuda.is_available.return_value = True
        fake_torch.cuda.device_count.return_value = 2
        # 24 GiB and 80 GiB devices.
        props_24 = MagicMock(name="A10", total_memory=24 * (1024**3))
        props_80 = MagicMock(name="A100", total_memory=80 * (1024**3))
        # MagicMock attribute trick: ``name`` is special, set explicitly.
        props_24.name = "NVIDIA A10"
        props_80.name = "NVIDIA A100"
        fake_torch.cuda.get_device_properties.side_effect = [props_24, props_80]
        with patch.dict("sys.modules", {"torch": fake_torch}):
            result = _check_gpu_inventory()
        assert result.status == "pass"
        assert result.extras["device_count"] == 2
        assert len(result.extras["devices"]) == 2
        assert result.extras["devices"][0]["vram_gib"] == 24.0
        assert result.extras["devices"][1]["vram_gib"] == 80.0


class TestOptionalExtraCheck:
    def test_present_module_passes(self) -> None:
        from forgelm.cli.subcommands._doctor import _check_optional_extra

        # ``json`` is always installed in stdlib — use it as the
        # "definitely present" probe target.
        result = _check_optional_extra("fakextra", "json", "stdlib JSON")
        assert result.status == "pass"
        assert "json" in result.detail
        assert result.extras["installed"] is True

    def test_missing_module_warns_with_install_hint(self) -> None:
        from forgelm.cli.subcommands._doctor import _check_optional_extra

        result = _check_optional_extra("ghost", "definitely_not_installed_xyz123", "fake purpose")
        assert result.status == "warn"
        assert "pip install 'forgelm[ghost]'" in result.detail
        assert result.extras["installed"] is False


class TestHfHubReachableCheck:
    def test_unreachable_warns_not_fails(self) -> None:
        """A network outage must NOT flip the gate to fail; doctor exists
        precisely to surface that fact."""
        import urllib.error

        from forgelm.cli.subcommands._doctor import _check_hf_hub_reachable

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("DNS lookup failed")):
            result = _check_hf_hub_reachable(timeout_seconds=0.1)
        assert result.status == "warn"
        assert result.extras["reachable"] is False

    def test_200_response_passes(self) -> None:
        from forgelm.cli.subcommands._doctor import _check_hf_hub_reachable

        fake_response = MagicMock()
        fake_response.status = 200
        fake_response.__enter__ = MagicMock(return_value=fake_response)
        fake_response.__exit__ = MagicMock(return_value=None)
        with patch("urllib.request.urlopen", return_value=fake_response):
            result = _check_hf_hub_reachable(timeout_seconds=0.1)
        assert result.status == "pass"
        assert result.extras["status_code"] == 200


class TestHfCacheOfflineCheck:
    def test_missing_cache_warns(self, tmp_path, monkeypatch) -> None:
        from forgelm.cli.subcommands._doctor import _check_hf_cache_offline

        monkeypatch.setenv("HF_HOME", str(tmp_path / "nonexistent_cache"))
        result = _check_hf_cache_offline()
        assert result.status == "warn"
        assert result.extras["exists"] is False

    def test_populated_cache_passes(self, tmp_path, monkeypatch) -> None:
        from forgelm.cli.subcommands._doctor import _check_hf_cache_offline

        cache_dir = tmp_path / "hf_cache"
        cache_dir.mkdir()
        # Write a small fake blob.
        (cache_dir / "model_blob").write_bytes(b"x" * 1024)
        monkeypatch.setenv("HF_HOME", str(cache_dir))
        result = _check_hf_cache_offline()
        assert result.status == "pass"
        assert result.extras["file_count"] == 1
        assert result.extras["size_gib"] >= 0  # tiny but non-negative

    def test_empty_cache_dir_warns(self, tmp_path, monkeypatch) -> None:
        from forgelm.cli.subcommands._doctor import _check_hf_cache_offline

        cache_dir = tmp_path / "hf_cache_empty"
        cache_dir.mkdir()
        monkeypatch.setenv("HF_HOME", str(cache_dir))
        result = _check_hf_cache_offline()
        assert result.status == "warn"
        assert result.extras["file_count"] == 0


class TestDiskSpaceCheck:
    def test_plenty_passes(self, tmp_path) -> None:
        from forgelm.cli.subcommands._doctor import _check_disk_space

        result = _check_disk_space(str(tmp_path))
        # On a CI runner free space typically > 50 GiB; ensure at least
        # one of the three valid statuses comes back.
        assert result.status in ("pass", "warn", "fail")
        assert result.extras["free_gib"] >= 0

    def test_low_disk_fails(self, tmp_path) -> None:
        from forgelm.cli.subcommands import _doctor

        # Build a fake disk_usage that reports 5 GiB free.
        fake_usage = _FakeDiskUsage(
            total=1000 * (1024**3),
            used=950 * (1024**3),
            free=5 * (1024**3),
        )
        with patch("shutil.disk_usage", return_value=fake_usage):
            result = _doctor._check_disk_space(str(tmp_path))
        assert result.status == "fail"

    def test_warn_threshold(self, tmp_path) -> None:
        from forgelm.cli.subcommands import _doctor

        # 30 GiB free → warn (between 10 and 50).
        fake_usage = _FakeDiskUsage(
            total=1000 * (1024**3),
            used=970 * (1024**3),
            free=30 * (1024**3),
        )
        with patch("shutil.disk_usage", return_value=fake_usage):
            result = _doctor._check_disk_space(str(tmp_path))
        assert result.status == "warn"


class TestOperatorIdentityCheck:
    def test_explicit_env_passes(self, monkeypatch) -> None:
        from forgelm.cli.subcommands._doctor import _check_operator_identity

        monkeypatch.setenv("FORGELM_OPERATOR", "ci-pipeline-prod")
        result = _check_operator_identity()
        assert result.status == "pass"
        assert "ci-pipeline-prod" in result.detail

    def test_missing_env_warns_with_fallback(self, monkeypatch) -> None:
        from forgelm.cli.subcommands._doctor import _check_operator_identity

        monkeypatch.delenv("FORGELM_OPERATOR", raising=False)
        result = _check_operator_identity()
        # On a normal dev workstation getpass.getuser() resolves so we
        # get warn (not fail).
        assert result.status in ("warn", "fail")
        assert "FORGELM_OPERATOR" in result.detail


# ---------------------------------------------------------------------------
# Renderers + exit-code mapping
# ---------------------------------------------------------------------------


def _make_results(*statuses: str):
    from forgelm.cli.subcommands._doctor import _CheckResult

    return [_CheckResult(name=f"test.{i}", status=s, detail=f"d{i}") for i, s in enumerate(statuses)]


class TestExitCodeMapping:
    def test_all_pass_returns_zero(self) -> None:
        from forgelm.cli.subcommands._doctor import _resolve_exit_code

        assert _resolve_exit_code(_make_results("pass", "pass", "pass")) == 0

    def test_warn_only_returns_zero(self) -> None:
        from forgelm.cli.subcommands._doctor import _resolve_exit_code

        # Warns are operator-actionable but do not flip the gate.
        assert _resolve_exit_code(_make_results("pass", "warn", "warn")) == 0

    def test_fail_returns_one(self) -> None:
        from forgelm.cli.subcommands._doctor import _resolve_exit_code

        assert _resolve_exit_code(_make_results("pass", "fail", "warn")) == 1

    def test_crashed_probe_returns_two(self) -> None:
        from forgelm.cli.subcommands._doctor import _CheckResult, _resolve_exit_code

        crashed = _CheckResult(
            name="crash.probe",
            status="fail",
            detail="boom",
            extras={"crashed": True, "error_class": "RuntimeError"},
        )
        assert _resolve_exit_code([crashed]) == 2


class TestRenderers:
    def test_text_renders_summary_line(self) -> None:
        from forgelm.cli.subcommands._doctor import _render_text

        results = _make_results("pass", "warn", "fail")
        out = _render_text(results)
        assert "1 pass" in out
        assert "1 warn" in out
        assert "1 fail" in out
        # Each check is rendered.
        assert "test.0" in out and "test.1" in out and "test.2" in out

    def test_json_envelope_shape(self) -> None:
        from forgelm.cli.subcommands._doctor import _render_json

        results = _make_results("pass", "fail")
        payload = json.loads(_render_json(results))
        assert payload["success"] is False  # has a fail
        assert payload["summary"] == {"pass": 1, "warn": 0, "fail": 1}
        assert len(payload["checks"]) == 2

    def test_json_success_true_when_only_passes_and_warns(self) -> None:
        from forgelm.cli.subcommands._doctor import _render_json

        results = _make_results("pass", "warn", "pass")
        payload = json.loads(_render_json(results))
        assert payload["success"] is True


# ---------------------------------------------------------------------------
# Crash isolation
# ---------------------------------------------------------------------------


class TestProbeCrashIsolation:
    def test_one_crashing_probe_does_not_abort_the_run(self, monkeypatch) -> None:
        """If one probe raises an unexpected exception, the rest must
        still execute and the failed probe must be converted to a fail
        result with a ``crashed`` marker."""
        from forgelm.cli.subcommands import _doctor

        def _boom() -> _doctor._CheckResult:
            raise RuntimeError("synthetic crash")

        # Replace the doctor's check plan with one passing probe + one
        # crashing probe so we can observe the isolation.
        def _fake_plan(*, offline: bool):
            return [
                ("ok.probe", lambda: _doctor._CheckResult(name="ok.probe", status="pass", detail="ok")),
                ("crash.probe", _boom),
            ]

        monkeypatch.setattr(_doctor, "_build_check_plan", _fake_plan)
        results = _doctor._run_all_checks(offline=False)
        assert len(results) == 2
        ok_result = next(r for r in results if r.name == "ok.probe")
        crash_result = next(r for r in results if r.name == "crash.probe")
        assert ok_result.status == "pass"
        assert crash_result.status == "fail"
        assert crash_result.extras.get("crashed") is True
        assert "RuntimeError" in crash_result.detail


# ---------------------------------------------------------------------------
# Plan composition
# ---------------------------------------------------------------------------


class TestCheckPlan:
    def test_offline_uses_cache_probe_not_hub_probe(self) -> None:
        from forgelm.cli.subcommands._doctor import _build_check_plan

        plan_offline = _build_check_plan(offline=True)
        plan_online = _build_check_plan(offline=False)
        names_offline = [name for name, _ in plan_offline]
        names_online = [name for name, _ in plan_online]
        assert "hf_hub.offline_cache" in names_offline
        assert "hf_hub.reachable" not in names_offline
        assert "hf_hub.reachable" in names_online
        assert "hf_hub.offline_cache" not in names_online

    def test_extras_in_plan(self) -> None:
        """All optional extras advertised in pyproject.toml are probed."""
        from forgelm.cli.subcommands._doctor import _OPTIONAL_EXTRAS, _build_check_plan

        plan = _build_check_plan(offline=False)
        names = {name for name, _ in plan}
        for extra, _module, _purpose in _OPTIONAL_EXTRAS:
            assert f"extras.{extra}" in names


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------


class TestDispatcher:
    def test_text_output_prints_summary(self, capsys) -> None:
        from forgelm.cli.subcommands._doctor import _run_doctor_cmd

        args = MagicMock()
        args.offline = True  # avoids the network probe
        with pytest.raises(SystemExit):
            _run_doctor_cmd(args, output_format="text")
        out = capsys.readouterr().out
        assert "Summary:" in out
        assert "forgelm doctor" in out

    def test_json_output_emits_envelope(self, capsys) -> None:
        from forgelm.cli.subcommands._doctor import _run_doctor_cmd

        args = MagicMock()
        args.offline = True
        with pytest.raises(SystemExit):
            _run_doctor_cmd(args, output_format="json")
        payload = json.loads(capsys.readouterr().out)
        assert "success" in payload
        assert "checks" in payload
        assert "summary" in payload
        assert all(set(c) >= {"name", "status", "detail", "extras"} for c in payload["checks"])

    def test_dispatcher_exits_with_resolved_code(self, capsys) -> None:
        from forgelm.cli.subcommands import _doctor

        # Force every probe to pass so exit code is 0.
        def _all_pass_plan(*, offline: bool):
            return [("only.probe", lambda: _doctor._CheckResult(name="only.probe", status="pass", detail="ok"))]

        with patch.object(_doctor, "_build_check_plan", _all_pass_plan):
            args = MagicMock()
            args.offline = False
            with pytest.raises(SystemExit) as ei:
                _doctor._run_doctor_cmd(args, output_format="text")
        assert ei.value.code == 0


# ---------------------------------------------------------------------------
# CLI subprocess smoke
# ---------------------------------------------------------------------------


class TestDoctorCLISmoke:
    def test_doctor_subcommand_registered(self) -> None:
        """`forgelm doctor --help` exits 0 and advertises --offline."""
        import subprocess

        result = subprocess.run(
            [sys.executable, "-m", "forgelm.cli", "doctor", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert "--offline" in result.stdout
        # Common-flag inheritance: --output-format / --quiet / --log-level.
        assert "--output-format" in result.stdout

    def test_doctor_offline_runs_end_to_end(self) -> None:
        """`forgelm doctor --offline --output-format json` produces a valid
        JSON envelope and exits with one of the public exit codes."""
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "forgelm.cli",
                "doctor",
                "--offline",
                "--output-format",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        # Public exit codes: 0 (all pass) / 1 (some fail) / 2 (probe crashed).
        assert result.returncode in (0, 1, 2), result.stderr
        # The JSON envelope is on stdout regardless.
        payload = json.loads(result.stdout)
        assert "success" in payload
        assert "checks" in payload
        assert isinstance(payload["checks"], list)


# ---------------------------------------------------------------------------
# Facade re-exports
# ---------------------------------------------------------------------------


class TestFacadeReExports:
    def test_doctor_helpers_reachable_via_facade(self) -> None:
        """Tests / monkeypatches reach doctor helpers via ``forgelm.cli``."""
        from forgelm import cli as _cli_facade

        for name in (
            "_run_doctor_cmd",
            "_run_all_checks",
            "_render_json",
            "_render_text",
            "_resolve_exit_code",
            "_check_python_version",
            "_check_torch_cuda",
            "_check_operator_identity",
        ):
            assert hasattr(_cli_facade, name), f"forgelm.cli must re-export {name!r}"

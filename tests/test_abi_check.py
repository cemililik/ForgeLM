"""Tests for the shared torch/NumPy ABI compatibility probe.

The probe lives at ``forgelm.cli._abi_check`` and is exercised by two
call sites:

- The doctor probe (``forgelm doctor`` -> ``numpy.torch_abi``) — covered
  in ``tests/test_doctor.py``.
- The training-pipeline preflight (``forgelm.cli._training`` ->
  ``_preflight_numpy_torch_abi``) — covered here.

The preflight is the second line of defense after the PEP 508 marker in
``pyproject.toml`` (``numpy<2; sys_platform == 'darwin' and
platform_machine == 'x86_64'``).  The marker auto-fixes fresh installs
and ``pip install -U`` re-resolves; the preflight catches residual
drift (out-of-band ``pip install numpy>=2`` after a working install).

Note on mocking strategy: we deliberately monkeypatch ``__version__``
on the real torch / numpy modules instead of substituting fake modules
into ``sys.modules``.  Replacing ``sys.modules["torch"]`` with a stand-in
breaks TRL's lazy-module loader for any subsequent test in the same
process (``trl.SFTConfig`` triggers a deferred ``torch._C`` lookup that
fails on the stand-in) — exactly the test pollution we are trying to
avoid in the first place.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from forgelm.cli import _abi_check, _training


class TestMajorMinor:
    """Version-string -> (MAJOR, MINOR) parser tolerates real-world labels."""

    def test_plain_version(self):
        assert _abi_check._major_minor("2.4.4") == (2, 4)

    def test_prerelease_suffix(self):
        assert _abi_check._major_minor("2.2.0a0") == (2, 2)

    def test_local_version_suffix(self):
        # "+cpu", "+cu118", etc. are PyTorch's standard local-version tags.
        assert _abi_check._major_minor("2.2.0+cpu") == (2, 2)
        assert _abi_check._major_minor("2.1.0+cu118") == (2, 1)

    def test_unparseable_returns_zero(self):
        # Defensive fallback: any totally-broken string maps to (0, 0).
        assert _abi_check._major_minor("garbage") == (0, 0)
        assert _abi_check._major_minor("") == (0, 0)


class TestComputeStatus:
    """Branch coverage for the verdict triple, via ``__version__`` swaps.

    Real torch + numpy stay in ``sys.modules``; only the ``__version__``
    strings move.  This is critical: substituting fake modules would
    poison TRL's lazy-import cache for every later test in the suite.
    """

    def test_compatible_modern_numpy(self, monkeypatch):
        import numpy
        import torch

        monkeypatch.setattr(torch, "__version__", "2.4.0")
        monkeypatch.setattr(numpy, "__version__", "2.0.0")
        status, torch_v, numpy_v = _abi_check.compute_numpy_torch_abi_status()
        assert status == _abi_check.ABI_OK
        assert torch_v == "2.4.0"
        assert numpy_v == "2.0.0"

    def test_compatible_legacy_numpy(self, monkeypatch):
        # The known-good Intel Mac pairing: torch 2.2.x (NumPy-1 ABI) + numpy 1.x.
        import numpy
        import torch

        monkeypatch.setattr(torch, "__version__", "2.2.0")
        monkeypatch.setattr(numpy, "__version__", "1.26.4")
        status, _, _ = _abi_check.compute_numpy_torch_abi_status()
        assert status == _abi_check.ABI_OK

    def test_broken_intel_mac_pairing(self, monkeypatch):
        # The exact v0.5.7 target case: torch 2.2.x (NumPy-1 ABI) + numpy 2.x.
        import numpy
        import torch

        monkeypatch.setattr(torch, "__version__", "2.2.2")
        monkeypatch.setattr(numpy, "__version__", "2.4.4")
        status, torch_v, numpy_v = _abi_check.compute_numpy_torch_abi_status()
        assert status == _abi_check.ABI_BROKEN
        assert torch_v == "2.2.2"
        assert numpy_v == "2.4.4"

    def test_boundary_torch_23_with_numpy_2(self, monkeypatch):
        # torch 2.3 was the first wheel built against NumPy 2 ABI —
        # the mismatch window is `torch < 2.3 AND numpy >= 2`, so
        # torch 2.3.0 + numpy 2.x must NOT trip the probe.  Regression
        # guard: a future review that "tightens" the threshold to <=2.3
        # would cause every healthy modern install to fail-fast.
        import numpy
        import torch

        monkeypatch.setattr(torch, "__version__", "2.3.0")
        monkeypatch.setattr(numpy, "__version__", "2.0.0")
        status, _, _ = _abi_check.compute_numpy_torch_abi_status()
        assert status == _abi_check.ABI_OK

    def test_unparseable_torch_version_does_not_false_positive(self, monkeypatch):
        # Corporate fork with a non-semver torch tag would otherwise
        # parse to (0, 0), which compares as `< (2, 3)` and would
        # trip ABI_BROKEN against any healthy numpy >= 2.  Round-4
        # fail-safe: an unparseable version on either side maps to
        # ABI_OK ("version unknown, do not classify") instead.
        import numpy
        import torch

        monkeypatch.setattr(torch, "__version__", "foo-bar-not-semver")
        monkeypatch.setattr(numpy, "__version__", "2.0.0")
        status, _, _ = _abi_check.compute_numpy_torch_abi_status()
        assert status == _abi_check.ABI_OK

    def test_unparseable_numpy_version_does_not_false_positive(self, monkeypatch):
        # Symmetric fail-safe on the numpy side.
        import numpy
        import torch

        monkeypatch.setattr(torch, "__version__", "2.2.0")
        monkeypatch.setattr(numpy, "__version__", "weird-vendor-tag")
        status, _, _ = _abi_check.compute_numpy_torch_abi_status()
        assert status == _abi_check.ABI_OK


class TestRemediation:
    """The shared remediation hint must carry the exact pip command."""

    def test_includes_pip_install(self):
        msg = _abi_check.format_abi_remediation("2.2.2", "2.4.4")
        assert "pip install 'numpy<2'" in msg
        assert "2.2.2" in msg
        assert "2.4.4" in msg

    def test_mentions_doctor(self):
        # Operator who hit this from training should be steered toward
        # `forgelm doctor` for the full environment diagnostic.
        msg = _abi_check.format_abi_remediation("2.2.2", "2.4.4")
        assert "forgelm doctor" in msg

    def test_none_version_raises_explicit_value_error(self):
        # Precondition guard: the helper is only meaningful after an
        # ABI_BROKEN verdict, which guarantees both versions are
        # populated.  A None slipping through (e.g. a future caller
        # mis-classifying ABI_SKIPPED_NUMPY) would otherwise produce a
        # confusing "torch None ..." string in the operator-visible
        # error path.
        with pytest.raises(ValueError, match="format_abi_remediation requires"):
            _abi_check.format_abi_remediation(None, "2.4.4")
        with pytest.raises(ValueError, match="format_abi_remediation requires"):
            _abi_check.format_abi_remediation("2.2.2", None)


class TestPreflightAbortsOnBroken:
    """Training preflight short-circuits the pipeline on a broken ABI."""

    def test_abort_with_log_message_on_broken(self, caplog):
        broken = (_abi_check.ABI_BROKEN, "2.2.2", "2.4.4")
        with patch.object(_abi_check, "compute_numpy_torch_abi_status", return_value=broken):
            with caplog.at_level("ERROR"), pytest.raises(SystemExit) as exc_info:
                _training._preflight_numpy_torch_abi(json_output=False)
        # Exit-code contract: training-pipeline preflight failure maps
        # to EXIT_TRAINING_ERROR (= 2 in the public table).
        assert exc_info.value.code == 2
        # The remediation hint must be in the operator-visible log.
        assert "pip install 'numpy<2'" in caplog.text

    def test_abort_emits_structured_json_envelope(self, capsys):
        broken = (_abi_check.ABI_BROKEN, "2.2.2", "2.4.4")
        with patch.object(_abi_check, "compute_numpy_torch_abi_status", return_value=broken):
            with pytest.raises(SystemExit):
                _training._preflight_numpy_torch_abi(json_output=True)
        captured = capsys.readouterr()
        envelope = json.loads(captured.out)
        # The JSON envelope is the machine-readable contract for CI/CD
        # consumers; lock the key set so a future field rename can't
        # silently break their parser.
        assert envelope["success"] is False
        assert envelope["error"] == "numpy_torch_abi_mismatch"
        assert envelope["torch_version"] == "2.2.2"
        assert envelope["numpy_version"] == "2.4.4"
        assert "pip install 'numpy<2'" in envelope["remediation"]


class TestPreflightPassesOnHealthy:
    """The preflight is a no-op on every non-broken status."""

    @pytest.mark.parametrize(
        "status",
        [
            _abi_check.ABI_OK,
            _abi_check.ABI_SKIPPED_TORCH,
            _abi_check.ABI_SKIPPED_NUMPY,
        ],
    )
    def test_no_op_for(self, status):
        # Returning normally (no SystemExit) is the contract — training
        # continues into the heavy-import block.
        result = (status, "2.4.0", "1.26.4")
        with patch.object(_abi_check, "compute_numpy_torch_abi_status", return_value=result):
            _training._preflight_numpy_torch_abi(json_output=False)


class TestPreflightHandlesProbeCrash:
    """A crash in ``compute_numpy_torch_abi_status`` itself (corrupted
    torch where ``torch.__version__`` raises, theoretical numpy ABI
    poisoning that breaks the import-time machinery, etc.) must be
    converted into a structured exit so the operator never sees a
    raw Python traceback pre-empt the JSON envelope contract.

    Round-5 absorption of CodeRabbit's MAJOR finding against the
    round-3/4 preflight wiring."""

    def _exploding_status(self):
        raise AttributeError("module 'torch' has no attribute '__version__'")

    def test_crash_exits_with_training_error_code(self, caplog):
        with patch.object(_abi_check, "compute_numpy_torch_abi_status", side_effect=self._exploding_status):
            with caplog.at_level("ERROR"), pytest.raises(SystemExit) as exc_info:
                _training._preflight_numpy_torch_abi(json_output=False)
        # Exit-code contract: the preflight crash maps to
        # EXIT_TRAINING_ERROR (= 2 in the public table) — same class
        # as the broken-ABI verdict, so CI/CD doesn't need to
        # distinguish "ABI bad" from "ABI probe died".
        assert exc_info.value.code == 2
        # Operator-visible log must mention the actionable next step.
        assert "forgelm doctor" in caplog.text
        assert "ABI preflight crashed" in caplog.text

    def test_crash_emits_structured_json_envelope(self, capsys):
        with patch.object(_abi_check, "compute_numpy_torch_abi_status", side_effect=self._exploding_status):
            with pytest.raises(SystemExit):
                _training._preflight_numpy_torch_abi(json_output=True)
        captured = capsys.readouterr()
        envelope = json.loads(captured.out)
        # Lock the key set — CI/CD consumers that parse this path
        # need a stable shape, distinct from the "numpy_torch_abi_
        # mismatch" envelope so they can branch on root cause.
        assert envelope["success"] is False
        assert envelope["error"] == "abi_preflight_crashed"
        assert envelope["exception_class"] == "AttributeError"
        assert "__version__" in envelope["exception_message"]
        assert "forgelm doctor" in envelope["remediation"]

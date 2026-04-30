"""Regression tests for the lazy-torch import contract.

`import forgelm.trainer` and `import forgelm.model` must NOT eagerly load
``torch`` (or its transitive deps via ``peft`` / ``transformers``). Eager
torch import costs ~3-5s of CLI startup per invocation, which dominates
``forgelm --help``, ``forgelm wizard``, and unit-test collection time.

A subprocess is used (rather than ``importlib.reload`` + ``sys.modules``
manipulation) because mutating the parent process's module table is fragile
across pytest runs and CI workers.

See closure-plan F-performance-101.
"""

import subprocess
import sys


def test_trainer_does_not_eagerly_load_torch():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import forgelm.trainer; import sys; sys.exit(0 if 'torch' not in sys.modules else 1)",
        ],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, f"forgelm.trainer eagerly loaded torch: {result.stderr.decode()}"


def test_model_does_not_eagerly_load_torch():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import forgelm.model; import sys; sys.exit(0 if 'torch' not in sys.modules else 1)",
        ],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, f"forgelm.model eagerly loaded torch: {result.stderr.decode()}"

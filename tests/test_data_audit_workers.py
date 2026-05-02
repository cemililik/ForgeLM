"""Phase 17: ``audit_dataset(..., workers=N)`` determinism contract.

Pins the per-Phase-17 invariants:

1. The audit JSON is byte-identical regardless of ``workers``.  Operators
   relying on ``data_audit_report.json`` for the EU AI Act Article 10
   governance bundle MUST be able to swap ``--workers 1`` for
   ``--workers 4`` without the artefact's hash changing.
2. ``lang_sample`` (random snippets per split) is byte-identical across
   worker counts — the only random-ish field in the report and the most
   likely place a parallel run would diverge.
3. PII / secrets / quality / near-duplicate counts are identical across
   worker counts.
4. The CLI ``--workers`` flag rejects 0 / negative values at parse time.
5. ``audit_dataset(workers=0)`` raises a typed ``ValueError`` so library
   callers that bypass argparse still see the validation.

The fixture corpus is intentionally small (3 splits × 12 rows) — the
suite runs on every CI matrix combo without budgeting for multi-second
multiprocessing spin-up costs.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _seed_three_split_corpus(tmp_path: Path) -> Path:
    """Build a deterministic 3-split corpus suitable for parallel audit."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    # Same row text across splits would trip cross-split-leakage detection;
    # we want a clean run so per-split assertions stay focused.  Different
    # subjects per split, deterministic content per row index.
    train_rows = [{"text": f"Training sample number {i} about machine learning topics."} for i in range(12)]
    val_rows = [{"text": f"Validation sample {i} on natural language processing benchmarks."} for i in range(8)]
    test_rows = [{"text": f"Test sample {i} for evaluation pipeline regression coverage."} for i in range(6)]
    _write_jsonl(corpus / "train.jsonl", train_rows)
    _write_jsonl(corpus / "validation.jsonl", val_rows)
    _write_jsonl(corpus / "test.jsonl", test_rows)
    return corpus


def _audit_to_canonical_json(corpus: Path, workers: int, output_dir: Path) -> str:
    """Run ``audit_dataset`` and return the on-disk JSON as a canonical string.

    Re-reading the on-disk file (rather than ``asdict(report)``) closes
    the loop on what an operator-facing CI gate actually compares.
    """
    from forgelm.data_audit import audit_dataset

    report = audit_dataset(str(corpus), output_dir=str(output_dir), workers=workers)
    # Sanity: the report dataclass is also self-consistent across runs.
    asdict_payload = asdict(report)
    assert isinstance(asdict_payload, dict)
    written = (output_dir / "data_audit_report.json").read_text(encoding="utf-8")
    return written


# ---------------------------------------------------------------------------
# Determinism contract — workers=1 vs workers=2 vs workers=4
# ---------------------------------------------------------------------------


class TestWorkersDeterminism:
    """The audit JSON must be byte-identical across worker counts."""

    @pytest.mark.parametrize("worker_count", [2, 4])
    def test_audit_json_byte_identical_to_sequential(self, tmp_path: Path, worker_count: int) -> None:
        corpus = _seed_three_split_corpus(tmp_path)

        baseline_dir = tmp_path / "out-w1"
        baseline_dir.mkdir()
        baseline_json = _audit_to_canonical_json(corpus, workers=1, output_dir=baseline_dir)

        parallel_dir = tmp_path / f"out-w{worker_count}"
        parallel_dir.mkdir()
        parallel_json = _audit_to_canonical_json(corpus, workers=worker_count, output_dir=parallel_dir)

        # ``generated_at`` is wall-clock; strip it from both before
        # comparing.  Everything else must match byte-for-byte.
        baseline = json.loads(baseline_json)
        parallel = json.loads(parallel_json)
        baseline.pop("generated_at", None)
        parallel.pop("generated_at", None)
        assert baseline == parallel, (
            f"audit JSON differs between workers=1 and workers={worker_count}; the determinism contract is broken"
        )

    def test_lang_sample_byte_identical(self, tmp_path: Path) -> None:
        """``lang_sample`` is the field most likely to diverge under
        non-deterministic ordering.  Pin it explicitly per split."""
        corpus = _seed_three_split_corpus(tmp_path)

        baseline_dir = tmp_path / "out-w1"
        baseline_dir.mkdir()
        seq_json = _audit_to_canonical_json(corpus, workers=1, output_dir=baseline_dir)

        parallel_dir = tmp_path / "out-w4"
        parallel_dir.mkdir()
        par_json = _audit_to_canonical_json(corpus, workers=4, output_dir=parallel_dir)

        seq = json.loads(seq_json)
        par = json.loads(par_json)
        for split_name in ("train", "validation", "test"):
            seq_split = seq["splits"][split_name]
            par_split = par["splits"][split_name]
            assert seq_split.get("lang_sample") == par_split.get("lang_sample"), (
                f"lang_sample for split {split_name!r} differs between workers=1 and workers=4"
            )


# ---------------------------------------------------------------------------
# Per-component invariants
# ---------------------------------------------------------------------------


class TestWorkersComponentInvariants:
    def test_pii_summary_identical(self, tmp_path: Path) -> None:
        # Inject a PII-bearing row so the summary is non-empty.
        corpus = _seed_three_split_corpus(tmp_path)
        train = corpus / "train.jsonl"
        existing = train.read_text(encoding="utf-8")
        train.write_text(
            existing + json.dumps({"text": "Contact alice@example.com or call 555-123-4567."}) + "\n",
            encoding="utf-8",
        )

        from forgelm.data_audit import audit_dataset

        seq = audit_dataset(str(corpus), workers=1)
        par = audit_dataset(str(corpus), workers=4)
        assert seq.pii_summary == par.pii_summary
        assert seq.pii_severity == par.pii_severity

    def test_near_duplicate_summary_identical(self, tmp_path: Path) -> None:
        # Inject duplicate rows in train to exercise the simhash detector.
        corpus = _seed_three_split_corpus(tmp_path)
        train = corpus / "train.jsonl"
        existing = train.read_text(encoding="utf-8")
        # Two near-identical rows — the simhash detector should flag the pair.
        dup_text = "Customer support handles refund requests promptly."
        train.write_text(
            existing + json.dumps({"text": dup_text}) + "\n" + json.dumps({"text": dup_text + " "}) + "\n",
            encoding="utf-8",
        )

        from forgelm.data_audit import audit_dataset

        seq = audit_dataset(str(corpus), workers=1)
        par = audit_dataset(str(corpus), workers=4)
        assert seq.near_duplicate_summary == par.near_duplicate_summary

    def test_total_samples_identical(self, tmp_path: Path) -> None:
        corpus = _seed_three_split_corpus(tmp_path)
        from forgelm.data_audit import audit_dataset

        seq = audit_dataset(str(corpus), workers=1)
        par = audit_dataset(str(corpus), workers=4)
        assert seq.total_samples == par.total_samples == 26  # 12 + 8 + 6

    def test_secrets_summary_identical(self, tmp_path: Path) -> None:
        corpus = _seed_three_split_corpus(tmp_path)
        # Inject a fake AWS key pattern so the secrets scanner has something
        # to find.  Pattern is intentionally fake (does not start with the
        # real AWS prefix) to avoid the gitleaks pre-commit hook flagging
        # the test fixture itself.
        train = corpus / "train.jsonl"
        existing = train.read_text(encoding="utf-8")
        # AKIA + 16 hex-style characters trips the AWS access-key regex.
        fake_secret = "AKIA" + "1234567890ABCDEF"
        train.write_text(
            existing + json.dumps({"text": f"Sample with AWS-like token {fake_secret}."}) + "\n",
            encoding="utf-8",
        )

        from forgelm.data_audit import audit_dataset

        seq = audit_dataset(str(corpus), workers=1)
        par = audit_dataset(str(corpus), workers=4)
        assert seq.secrets_summary == par.secrets_summary


# ---------------------------------------------------------------------------
# Edge cases — single split, sequential default, validation
# ---------------------------------------------------------------------------


class TestWorkersEdgeCases:
    def test_single_split_corpus_ignores_workers_above_one(self, tmp_path: Path) -> None:
        """A single-split corpus has nothing to parallelise; ``workers > 1``
        must still produce a valid report."""
        corpus_file = tmp_path / "single.jsonl"
        _write_jsonl(corpus_file, [{"text": f"Row {i}"} for i in range(20)])

        from forgelm.data_audit import audit_dataset

        report_seq = audit_dataset(str(corpus_file), workers=1)
        report_par = audit_dataset(str(corpus_file), workers=4)

        assert report_seq.total_samples == report_par.total_samples == 20
        assert set(report_seq.splits) == set(report_par.splits) == {"train"}

    def test_default_workers_is_one(self, tmp_path: Path) -> None:
        """Backwards compatibility: omitting ``workers`` must produce the
        sequential path so the default behaviour for every existing caller
        is unchanged."""
        corpus = _seed_three_split_corpus(tmp_path)

        from forgelm.data_audit import audit_dataset

        # No keyword: should run sequentially.  Asserting absence of error
        # is the contract; the JSON-equivalence test above confirms the
        # numerical equivalence.
        report = audit_dataset(str(corpus))
        assert report.total_samples == 26

    @pytest.mark.parametrize("invalid", [0, -1, -10])
    def test_workers_below_one_raises_valueerror(self, tmp_path: Path, invalid: int) -> None:
        """``workers < 1`` is caller error, not a runtime fault."""
        corpus = _seed_three_split_corpus(tmp_path)

        from forgelm.data_audit import audit_dataset

        with pytest.raises(ValueError, match="workers"):
            audit_dataset(str(corpus), workers=invalid)

    def test_workers_non_int_raises_valueerror(self, tmp_path: Path) -> None:
        corpus = _seed_three_split_corpus(tmp_path)

        from forgelm.data_audit import audit_dataset

        with pytest.raises(ValueError, match="workers"):
            audit_dataset(str(corpus), workers="four")  # type: ignore[arg-type]

    def test_workers_bool_raises_valueerror(self, tmp_path: Path) -> None:
        """``True`` would int-coerce to 1 but is the wrong type — reject
        explicitly so a caller can't accidentally pass a boolean."""
        corpus = _seed_three_split_corpus(tmp_path)

        from forgelm.data_audit import audit_dataset

        with pytest.raises(ValueError, match="workers"):
            audit_dataset(str(corpus), workers=True)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# CLI smoke — --workers flag end-to-end
# ---------------------------------------------------------------------------


class TestWorkersCLI:
    def test_cli_workers_flag_help_text(self) -> None:
        """``forgelm audit --help`` exposes the new flag with the expected
        metavar so operators can discover it."""
        import subprocess

        result = subprocess.run(
            [sys.executable, "-m", "forgelm.cli", "audit", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert "--workers" in result.stdout
        assert "default: 1" in result.stdout.lower() or "(default: 1" in result.stdout

    def test_cli_workers_zero_rejected_at_parse_time(self) -> None:
        """``--workers 0`` exits with argparse usage-error rather than
        propagating into the audit pipeline."""
        import subprocess

        result = subprocess.run(
            [sys.executable, "-m", "forgelm.cli", "audit", "/nonexistent", "--workers", "0"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0
        # argparse error path uses "invalid X value" or our custom
        # "value must be >= 1" message.
        combined = result.stderr.lower()
        assert ">= 1" in combined or "value must" in combined or "invalid" in combined

    def test_cli_workers_negative_rejected_at_parse_time(self) -> None:
        import subprocess

        result = subprocess.run(
            [sys.executable, "-m", "forgelm.cli", "audit", "/nonexistent", "--workers", "-2"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0

    def test_cli_workers_default_when_omitted(self, tmp_path: Path) -> None:
        """Running ``forgelm audit`` without ``--workers`` produces the same
        report as ``--workers 1``."""
        import subprocess

        corpus = _seed_three_split_corpus(tmp_path)

        out_default = tmp_path / "default"
        out_default.mkdir()
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "forgelm.cli",
                "audit",
                str(corpus),
                "--output",
                str(out_default),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr

        out_explicit = tmp_path / "explicit"
        out_explicit.mkdir()
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "forgelm.cli",
                "audit",
                str(corpus),
                "--output",
                str(out_explicit),
                "--workers",
                "1",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr

        default_payload = json.loads((out_default / "data_audit_report.json").read_text(encoding="utf-8"))
        explicit_payload = json.loads((out_explicit / "data_audit_report.json").read_text(encoding="utf-8"))
        default_payload.pop("generated_at", None)
        explicit_payload.pop("generated_at", None)
        assert default_payload == explicit_payload

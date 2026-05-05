"""Phase 38 — `forgelm reverse-pii` GDPR Article 15 right-of-access.

Tests run torch-free + extra-free.  All scenarios use synthetic JSONL
fixtures so the suite stays deterministic + offline.

Test coverage maps to closure-plan §Faz 38 acceptance:

1. Plaintext residual scan — identifier verbatim found / not found
   in glob expansion.
2. Hash-mask scan — SHA256(salt + identifier) recomputed via the
   same per-output-dir salt as `forgelm purge`; matches the masked
   corpus.
3. Audit-event emission — `data.access_request_query` written;
   identifier hashed (NEVER raw).
4. Glob expansion — multiple files scanned in deterministic order;
   per-file match count surfaced.
5. Failure paths — empty query / unparseable custom regex / empty
   glob expansion → exit code 1; mid-scan I/O failure → exit 2.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest.mock as _mock
from pathlib import Path
from types import SimpleNamespace

import pytest


def _seed_corpus(corpus_path: Path, rows: list[dict]) -> None:
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    with open(corpus_path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _read_audit_events(audit_log_path: Path) -> list[dict]:
    events: list[dict] = []
    with open(audit_log_path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events


def _build_args(
    *,
    query: str | None = None,
    type: str | None = "custom",
    salt_source: str | None = None,
    files: list[str] | None = None,
    output_dir: str | None = None,
    audit_dir: str | None = None,
) -> SimpleNamespace:
    """Strict argparse-shaped namespace; misspelled attrs raise."""
    return SimpleNamespace(
        query=query,
        type=type,
        salt_source=salt_source,
        files=files,
        output_dir=output_dir,
        audit_dir=audit_dir,
    )


@pytest.fixture(autouse=True)
def _set_operator_env(monkeypatch):
    """Every test runs with a deterministic FORGELM_OPERATOR so AuditLogger
    does not refuse to start on shared CI runners.  Also clears any
    inherited FORGELM_AUDIT_SECRET from a prior test in the same
    invocation so per_dir / env_var modes are predictable."""
    monkeypatch.setenv("FORGELM_OPERATOR", "test-operator@reverse-pii-test")
    monkeypatch.delenv("FORGELM_AUDIT_SECRET", raising=False)


# ---------------------------------------------------------------------------
# §1 Test — Plaintext residual scan: verbatim match found
# ---------------------------------------------------------------------------


class TestPlaintextResidualMatch:
    def test_email_residual_found_with_line_and_snippet(self, tmp_path: Path, capsys) -> None:
        from forgelm.cli.subcommands._reverse_pii import _run_reverse_pii_cmd

        corpus = tmp_path / "train.jsonl"
        _seed_corpus(
            corpus,
            [
                {"id": "row-A", "text": "Hello, my name is Alice"},
                {"id": "row-B", "text": "Contact me at alice@example.com please"},
                {"id": "row-C", "text": "Carol said hi"},
            ],
        )
        args = _build_args(
            query="alice@example.com",
            type="email",
            files=[str(corpus)],
            output_dir=str(tmp_path),
        )
        with pytest.raises(SystemExit) as ei:
            _run_reverse_pii_cmd(args, output_format="json")
        assert ei.value.code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is True
        assert payload["match_count"] == 1
        assert payload["scan_mode"] == "plaintext"
        assert payload["identifier_type"] == "email"
        # Single match is on row-B (line 2, 1-based).
        match = payload["matches"][0]
        assert match["file"] == os.path.abspath(str(corpus))
        assert match["line"] == 2
        assert "alice@example.com" in match["snippet"]
        # files_scanned reports the per-file match count too.
        assert payload["files_scanned"] == [{"path": os.path.abspath(str(corpus)), "match_count": 1}]

    def test_no_residual_found_returns_empty_match_list(self, tmp_path: Path, capsys) -> None:
        from forgelm.cli.subcommands._reverse_pii import _run_reverse_pii_cmd

        corpus = tmp_path / "train.jsonl"
        _seed_corpus(corpus, [{"id": "row-A", "text": "no PII here"}])
        args = _build_args(
            query="someone-else@example.com",
            type="email",
            files=[str(corpus)],
            output_dir=str(tmp_path),
        )
        with pytest.raises(SystemExit) as ei:
            _run_reverse_pii_cmd(args, output_format="json")
        assert ei.value.code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["match_count"] == 0
        assert payload["matches"] == []
        # files_scanned still records that we walked the file.
        assert len(payload["files_scanned"]) == 1
        assert payload["files_scanned"][0]["match_count"] == 0


# ---------------------------------------------------------------------------
# §2 Test — Hash-mask scan: SHA256(salt + identifier) found in masked corpus
# ---------------------------------------------------------------------------


class TestHashMaskScan:
    def test_per_dir_hash_matches_masked_row(self, tmp_path: Path, capsys) -> None:
        from forgelm.cli.subcommands._purge import _hash_target_id, _resolve_salt
        from forgelm.cli.subcommands._reverse_pii import _run_reverse_pii_cmd

        # Pre-create the salt file; compute the digest the operator
        # would have written to the masked corpus.
        salt, source = _resolve_salt(str(tmp_path))
        assert source == "per_dir"
        masked_digest = _hash_target_id("alice@example.com", salt)

        corpus = tmp_path / "masked.jsonl"
        _seed_corpus(
            corpus,
            [
                {"id": "row-A", "text": "first record, no PII"},
                {"id": "row-B", "text": f"hashed identifier embedded: {masked_digest}"},
                {"id": "row-C", "text": "control row"},
            ],
        )
        args = _build_args(
            query="alice@example.com",
            type="email",
            salt_source="per_dir",
            files=[str(corpus)],
            output_dir=str(tmp_path),
        )
        with pytest.raises(SystemExit) as ei:
            _run_reverse_pii_cmd(args, output_format="json")
        assert ei.value.code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["scan_mode"] == "hash"
        assert payload["match_count"] == 1
        # The match snippet contains the hash digest, NOT the raw email.
        snippet = payload["matches"][0]["snippet"]
        assert masked_digest in snippet
        assert "alice@example.com" not in snippet

    def test_env_var_salt_source_requires_secret_env(self, tmp_path: Path, capsys, monkeypatch) -> None:
        """``--salt-source env_var`` without ``FORGELM_AUDIT_SECRET``
        must refuse rather than silently scan with the wrong salt."""
        from forgelm.cli.subcommands._reverse_pii import _run_reverse_pii_cmd

        # Explicitly clear (autouse fixture also does this; belt + braces).
        monkeypatch.delenv("FORGELM_AUDIT_SECRET", raising=False)
        corpus = tmp_path / "masked.jsonl"
        _seed_corpus(corpus, [{"id": "row-A", "text": "x"}])
        args = _build_args(
            query="alice@example.com",
            type="email",
            salt_source="env_var",
            files=[str(corpus)],
            output_dir=str(tmp_path),
        )
        with pytest.raises(SystemExit) as ei:
            _run_reverse_pii_cmd(args, output_format="json")
        assert ei.value.code == 1, "env_var without FORGELM_AUDIT_SECRET must surface as EXIT_CONFIG_ERROR"


# ---------------------------------------------------------------------------
# §3 Test — Audit event emitted; identifier hashed (NEVER raw)
# ---------------------------------------------------------------------------


class TestAuditEventDoesNotLeakIdentifier:
    def test_access_request_event_carries_hashed_query_only(self, tmp_path: Path) -> None:
        from forgelm.cli.subcommands._reverse_pii import _run_reverse_pii_cmd

        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        corpus = tmp_path / "train.jsonl"
        _seed_corpus(corpus, [{"id": "row-A", "text": "alice@example.com is here"}])

        args = _build_args(
            query="alice@example.com",
            type="email",
            files=[str(corpus)],
            output_dir=str(tmp_path),
            audit_dir=str(audit_dir),
        )
        with pytest.raises(SystemExit) as ei:
            _run_reverse_pii_cmd(args, output_format="json")
        assert ei.value.code == 0

        events = _read_audit_events(audit_dir / "audit_log.jsonl")
        access_events = [e for e in events if e["event"] == "data.access_request_query"]
        assert len(access_events) == 1
        evt = access_events[0]
        # Hashed identifier present; raw email NOT.
        expected_hash = hashlib.sha256(b"alice@example.com").hexdigest()
        assert evt["query_hash"] == expected_hash
        # Critical: raw identifier appears NOWHERE in the event payload.
        as_str = json.dumps(evt)
        assert "alice@example.com" not in as_str, f"audit event leaked raw identifier:\n{as_str}"
        assert evt["identifier_type"] == "email"
        assert evt["scan_mode"] == "plaintext"
        assert evt["match_count"] == 1


# ---------------------------------------------------------------------------
# §4 Test — Glob expansion: multiple files, deterministic ordering
# ---------------------------------------------------------------------------


class TestGlobExpansion:
    def test_glob_pattern_expands_to_multiple_files_with_per_file_counts(self, tmp_path: Path, capsys) -> None:
        from forgelm.cli.subcommands._reverse_pii import _run_reverse_pii_cmd

        # Plant three corpora; identifier appears in two of them.
        for name, rows in [
            ("a.jsonl", [{"id": "1", "text": "alice@example.com here"}]),
            ("b.jsonl", [{"id": "1", "text": "no PII"}]),
            ("c.jsonl", [{"id": "1", "text": "alice@example.com again"}]),
        ]:
            _seed_corpus(tmp_path / name, rows)

        args = _build_args(
            query="alice@example.com",
            type="email",
            files=[str(tmp_path / "*.jsonl")],
            output_dir=str(tmp_path),
        )
        with pytest.raises(SystemExit) as ei:
            _run_reverse_pii_cmd(args, output_format="json")
        assert ei.value.code == 0
        payload = json.loads(capsys.readouterr().out)
        # 3 files scanned; 2 matches total (a + c each contribute 1).
        assert len(payload["files_scanned"]) == 3
        assert payload["match_count"] == 2
        per_file = {fs["path"]: fs["match_count"] for fs in payload["files_scanned"]}
        assert per_file[os.path.abspath(str(tmp_path / "a.jsonl"))] == 1
        assert per_file[os.path.abspath(str(tmp_path / "b.jsonl"))] == 0
        assert per_file[os.path.abspath(str(tmp_path / "c.jsonl"))] == 1

    def test_recursive_glob_descends_into_subdirs(self, tmp_path: Path, capsys) -> None:
        from forgelm.cli.subcommands._reverse_pii import _run_reverse_pii_cmd

        nested = tmp_path / "year-2026" / "q2"
        nested.mkdir(parents=True)
        _seed_corpus(nested / "train.jsonl", [{"id": "1", "text": "ali@example.com here"}])

        args = _build_args(
            query="ali@example.com",
            type="email",
            files=[str(tmp_path / "**" / "train.jsonl")],
            output_dir=str(tmp_path),
        )
        with pytest.raises(SystemExit) as ei:
            _run_reverse_pii_cmd(args, output_format="json")
        assert ei.value.code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["match_count"] == 1


# ---------------------------------------------------------------------------
# §5 Test — Failure paths
# ---------------------------------------------------------------------------


class TestFailurePaths:
    def test_empty_query_exits_config_error(self, tmp_path: Path) -> None:
        from forgelm.cli.subcommands._reverse_pii import _run_reverse_pii_cmd

        corpus = tmp_path / "train.jsonl"
        _seed_corpus(corpus, [{"id": "1", "text": "x"}])
        args = _build_args(query="   ", files=[str(corpus)], output_dir=str(tmp_path))
        with pytest.raises(SystemExit) as ei:
            _run_reverse_pii_cmd(args, output_format="json")
        assert ei.value.code == 1

    def test_unparseable_custom_regex_exits_config_error(self, tmp_path: Path) -> None:
        from forgelm.cli.subcommands._reverse_pii import _run_reverse_pii_cmd

        corpus = tmp_path / "train.jsonl"
        _seed_corpus(corpus, [{"id": "1", "text": "x"}])
        # Unbalanced bracket; re.compile will raise.
        args = _build_args(query="[invalid", type="custom", files=[str(corpus)], output_dir=str(tmp_path))
        with pytest.raises(SystemExit) as ei:
            _run_reverse_pii_cmd(args, output_format="json")
        assert ei.value.code == 1

    def test_unknown_identifier_type_rejected(self, tmp_path: Path) -> None:
        # The argparse layer also catches this, but the dispatcher
        # validates as belt-and-suspenders for direct library callers.
        from forgelm.cli.subcommands._reverse_pii import _run_reverse_pii_cmd

        corpus = tmp_path / "train.jsonl"
        _seed_corpus(corpus, [{"id": "1", "text": "x"}])
        args = _build_args(query="x", type="bogus_type", files=[str(corpus)], output_dir=str(tmp_path))
        with pytest.raises(SystemExit) as ei:
            _run_reverse_pii_cmd(args, output_format="json")
        assert ei.value.code == 1

    def test_empty_glob_exits_config_error(self, tmp_path: Path, capsys) -> None:
        from forgelm.cli.subcommands._reverse_pii import _run_reverse_pii_cmd

        args = _build_args(
            query="alice@example.com",
            type="email",
            files=[str(tmp_path / "nonexistent" / "*.jsonl")],
            output_dir=str(tmp_path),
        )
        with pytest.raises(SystemExit) as ei:
            _run_reverse_pii_cmd(args, output_format="json")
        assert ei.value.code == 1

    def test_no_files_argument_exits_config_error(self, tmp_path: Path) -> None:
        from forgelm.cli.subcommands._reverse_pii import _run_reverse_pii_cmd

        args = _build_args(query="x", type="email", files=[], output_dir=str(tmp_path))
        with pytest.raises(SystemExit) as ei:
            _run_reverse_pii_cmd(args, output_format="json")
        assert ei.value.code == 1

    def test_mid_scan_io_failure_writes_failed_audit_event(self, tmp_path: Path, monkeypatch) -> None:
        from forgelm.cli.subcommands import _reverse_pii

        corpus = tmp_path / "train.jsonl"
        _seed_corpus(corpus, [{"id": "1", "text": "alice@example.com"}])
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()

        # Spy on _scan_file → raise OSError on the second call (the
        # second file gets opened and the read fails mid-line).
        original_scan = _reverse_pii._scan_file
        call_count = [0]

        def _flaky_scan(path: str, pattern):
            call_count[0] += 1
            if call_count[0] >= 2:
                raise OSError("simulated mid-scan I/O failure")
            return original_scan(path, pattern)

        monkeypatch.setattr(_reverse_pii, "_scan_file", _flaky_scan)

        # Two files so the second invocation exercises the failure path.
        corpus2 = tmp_path / "train2.jsonl"
        _seed_corpus(corpus2, [{"id": "2", "text": "bob@example.com"}])

        args = _build_args(
            query="alice@example.com",
            type="email",
            files=[str(corpus), str(corpus2)],
            output_dir=str(tmp_path),
            audit_dir=str(audit_dir),
        )
        with pytest.raises(SystemExit) as ei:
            _reverse_pii._run_reverse_pii_cmd(args, output_format="json")
        assert ei.value.code == 2

        events = _read_audit_events(audit_dir / "audit_log.jsonl")
        access_events = [e for e in events if e["event"] == "data.access_request_query"]
        assert len(access_events) == 1
        evt = access_events[0]
        assert evt["error_class"] == "OSError"
        assert "simulated mid-scan I/O failure" in evt["error_message"]


# ---------------------------------------------------------------------------
# §6 Test — Snippet truncation defends unbounded log spam
# ---------------------------------------------------------------------------


class TestSnippetTruncation:
    def test_long_line_centre_truncated(self, tmp_path: Path, capsys) -> None:
        from forgelm.cli.subcommands._reverse_pii import _SNIPPET_MAX_CHARS, _run_reverse_pii_cmd

        # Construct a line longer than the snippet budget with the
        # match in the middle.
        prefix = "x" * 200
        suffix = "y" * 200
        corpus = tmp_path / "train.jsonl"
        with open(corpus, "w", encoding="utf-8") as fh:
            fh.write(f"{prefix} alice@example.com {suffix}\n")

        args = _build_args(
            query="alice@example.com",
            type="email",
            files=[str(corpus)],
            output_dir=str(tmp_path),
        )
        with pytest.raises(SystemExit) as ei:
            _run_reverse_pii_cmd(args, output_format="json")
        assert ei.value.code == 0
        payload = json.loads(capsys.readouterr().out)
        snippet = payload["matches"][0]["snippet"]
        assert len(snippet) <= _SNIPPET_MAX_CHARS
        # Ellipsis marks where the middle was elided.
        assert "…" in snippet


# ---------------------------------------------------------------------------
# §7 Test — Facade re-exports + parser wiring + dispatch
# ---------------------------------------------------------------------------


class TestReversePiiFacade:
    def test_facade_re_exports_dispatcher_and_helpers(self) -> None:
        from forgelm import cli as _cli_facade

        for name in (
            "_run_reverse_pii_cmd",
            "_validate_query",
            "_validate_identifier_type",
            "_resolve_files",
            "_scan_file",
            "_truncate_snippet",
            "_hash_for_audit",
            "_emit_reverse_pii_result",
        ):
            assert hasattr(_cli_facade, name), f"forgelm.cli must re-export {name!r}"

    def test_parser_registers_reverse_pii_subcommand(self) -> None:
        """`forgelm reverse-pii --help` must succeed without --config."""
        from forgelm.cli._parser import parse_args

        # parse_args reads sys.argv; mock it.
        with _mock.patch.object(sys, "argv", ["forgelm", "reverse-pii", "--help"]):
            with pytest.raises(SystemExit) as ei:
                parse_args()
            # argparse exits 0 on --help.
            assert ei.value.code == 0

    def test_parser_accepts_minimum_arguments(self, tmp_path: Path) -> None:
        from forgelm.cli._parser import parse_args

        corpus = tmp_path / "train.jsonl"
        corpus.write_text("{}\n")
        with _mock.patch.object(
            sys,
            "argv",
            ["forgelm", "reverse-pii", "--query", "alice@example.com", str(corpus)],
        ):
            args = parse_args()
        assert args.command == "reverse-pii"
        assert args.query == "alice@example.com"
        assert args.files == [str(corpus)]
        # Defaults round-trip.
        assert args.type == "custom"
        assert args.salt_source is None

    def test_dispatch_table_registers_reverse_pii(self) -> None:
        """The dispatcher table must include the reverse-pii row so the
        CLI binary actually routes the subcommand to its handler."""
        from forgelm.cli._dispatch import _dispatch_subcommand

        # Exercise the dispatch via a monkeypatch on the facade so we
        # don't need to actually run the scanner.
        called = {}

        def _fake_dispatch(args, output_format):
            called["command"] = "reverse-pii"
            called["query"] = getattr(args, "query", None)
            sys.exit(0)

        from forgelm import cli as _cli_facade

        original = _cli_facade._run_reverse_pii_cmd
        _cli_facade._run_reverse_pii_cmd = _fake_dispatch
        try:
            args = _build_args(query="x", type="email", files=["dummy"])
            args.command = "reverse-pii"
            args.output_format = "json"
            with pytest.raises(SystemExit) as ei:
                _dispatch_subcommand("reverse-pii", args)
            assert ei.value.code == 0
            assert called == {"command": "reverse-pii", "query": "x"}
        finally:
            _cli_facade._run_reverse_pii_cmd = original

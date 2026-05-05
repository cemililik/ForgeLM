"""``forgelm reverse-pii`` — GDPR Article 15 right-of-access subcommand.

Phase 38 closure of GH-014.  Companion to ``forgelm purge`` (Phase 21,
Article 17 right-to-erasure): where ``purge`` lets a data subject ask
"delete my row," ``reverse-pii`` lets the same subject ask "is my row
in the corpus at all, and if so, where?"

The subcommand walks a glob of JSONL corpora and reports every line
where a supplied identifier (e-mail, phone, TR national ID, custom
regex, or hash-masked digest) appears.  Two complementary scan modes:

1. **Plaintext residual scan** (default).  Searches for the identifier
   verbatim — the path that surfaces *mask leaks* (operator believed
   the corpus was masked but a residual span was missed by the
   masking pass).  This is the audit-time honest-PII check.
2. **Hash-mask scan** (``--salt-source per_dir`` or ``--salt-source
   env_var``).  Computes ``SHA256(salt + identifier)`` using the same
   per-output-dir salt that ``forgelm purge`` uses for its
   ``target_id`` hashing, then searches every JSONL line for that
   digest.  This is the path for corpora that were masked through
   ForgeLM's own ``hash`` replacement strategy.

Audit chain: every invocation writes a ``data.access_request_query``
event with the identifier *hashed* (never raw — Article 15 access
requests must not themselves leak the subject's identifier into the
audit log) and the per-file match count.  An operator who later runs
``forgelm verify-audit`` sees a forensic record that the request was
processed without the audit log itself becoming a residual leak.

Exit codes (per ``docs/standards/error-handling.md``):

- 0 — command ran (matches reported, may be empty).
- 1 — config error (empty/whitespace ``--query``, unparseable regex
  for ``--type custom``, glob pattern resolved to zero files).
- 2 — runtime error (I/O failure walking the corpus, audit-log write
  failure when an audit dir was supplied).
"""

from __future__ import annotations

import glob as _glob
import hashlib
import json
import os
import re
import sys
from typing import Any, Dict, List, NoReturn, Optional, Tuple

from .._exit_codes import EXIT_CONFIG_ERROR, EXIT_SUCCESS, EXIT_TRAINING_ERROR
from .._logging import logger

_EVT_ACCESS_REQUEST_QUERY = "data.access_request_query"

# Snippet shape: report at most this many characters around the match
# so the operator can verify the hit but the JSON envelope does not
# itself leak unbounded surrounding context.
_SNIPPET_MAX_CHARS = 160

# Identifier-type keys.  Mirror the categories that
# ``forgelm/data_audit/_pii_regex.py::_PII_PATTERNS`` knows so the
# operator can ask "is there a phone matching this exact number" and
# get a result that the audit's own detector would have flagged.
_IDENTIFIER_TYPES: Tuple[str, ...] = ("email", "phone", "tr_id", "us_ssn", "iban", "credit_card", "custom")


def _output_error_and_exit(output_format: str, msg: str, exit_code: int) -> NoReturn:
    """Mirror the JSON-vs-text envelope helper used by every other
    Wave 2b/3 subcommand so the contract stays uniform."""
    if output_format == "json":
        print(json.dumps({"success": False, "error": msg}))
    else:
        logger.error(msg)
    sys.exit(exit_code)


def _validate_query(query: Optional[str], output_format: str) -> str:
    """Refuse empty / whitespace-only queries early.

    Without this guard a stray ``forgelm reverse-pii --query ""`` would
    match every line in the corpus (empty-substring semantics) and
    silently spam the audit log with a useless event.
    """
    if not query or not query.strip():
        _output_error_and_exit(
            output_format,
            "--query must be a non-empty identifier (e-mail, phone, ID, regex pattern, or pre-hashed digest).",
            EXIT_CONFIG_ERROR,
        )
    return query.strip()


def _validate_identifier_type(identifier_type: str, output_format: str) -> str:
    """Refuse identifier types we don't know how to scan for."""
    if identifier_type not in _IDENTIFIER_TYPES:
        _output_error_and_exit(
            output_format,
            f"--type {identifier_type!r} is not recognised.  Choose one of: {', '.join(sorted(_IDENTIFIER_TYPES))}.",
            EXIT_CONFIG_ERROR,
        )
    return identifier_type


def _build_search_pattern(query: str, identifier_type: str, output_format: str) -> re.Pattern[str]:
    """Compile the regex used to scan each JSONL line.

    For ``--type custom`` the operator's ``--query`` is interpreted as
    a regex (escaped only to fix anchoring / boundaries).  For every
    other type the query is treated as a literal string and surrounded
    with ``re.escape`` — the goal is "find this exact identifier",
    not "find anything matching its shape" (the audit-time detector
    already handles the latter).
    """
    if identifier_type == "custom":
        try:
            return re.compile(query)
        except re.error as exc:
            _output_error_and_exit(
                output_format,
                f"--type custom --query {query!r} is not a valid regular expression: {exc}.",
                EXIT_CONFIG_ERROR,
            )
    return re.compile(re.escape(query))


def _resolve_files(globs: List[str], output_format: str) -> List[str]:
    """Expand each ``<jsonl-glob>`` positional argument to a list of files.

    Recursive globs (``**``) are honoured.  Refuses an empty resolved
    set as a config error — the operator either typed a wrong path or
    pointed at an empty directory; either way "no files scanned" is
    not a successful answer to "is this identifier in the corpus."
    """
    resolved: List[str] = []
    seen: set[str] = set()
    for pattern in globs:
        for match in sorted(_glob.glob(pattern, recursive=True)):
            if not os.path.isfile(match):
                continue
            absolute = os.path.abspath(match)
            if absolute in seen:
                continue
            seen.add(absolute)
            resolved.append(absolute)
    if not resolved:
        _output_error_and_exit(
            output_format,
            f"No files matched the supplied glob pattern(s): {globs!r}.  "
            "Check the path or run with shell-expanded paths.",
            EXIT_CONFIG_ERROR,
        )
    return resolved


def _resolve_query_form(query: str, salt_source: Optional[str], output_dir: str, output_format: str) -> Tuple[str, str]:
    """Map the operator-supplied identifier to the form actually
    searched in the corpus.

    Returns ``(scan_query, scan_mode)`` where ``scan_mode`` is one of:

    - ``"plaintext"`` — search for ``query`` verbatim (mask-leak path).
    - ``"hash"`` — compute ``SHA256(salt + query)`` and search for the
      digest (the corpus was masked via ForgeLM's hash strategy).

    ``--salt-source`` triggers hash mode and reuses the per-output-dir
    salt resolution from ``forgelm purge`` so the two subcommands
    cannot drift on hashing semantics.
    """
    if salt_source is None:
        return query, "plaintext"
    # Late import: ``_resolve_salt`` lives in the purge subcommand and
    # pulling it eagerly would create a load-time cycle.  The two
    # subcommands intentionally share the salt-resolution path so a
    # purge-then-reverse-pii cycle works on the same digest.
    from ._purge import _hash_target_id, _resolve_salt

    try:
        salt, resolved_source = _resolve_salt(output_dir)
    except OSError as exc:
        _output_error_and_exit(
            output_format,
            f"Could not resolve audit salt for {output_dir!r}: {exc}",
            EXIT_TRAINING_ERROR,
        )
    if salt_source != resolved_source:
        # The operator asked for ``env_var`` but the env wasn't set
        # (or vice versa).  Refuse rather than silently scan with the
        # wrong salt source — the resulting digest would never match.
        _output_error_and_exit(
            output_format,
            f"--salt-source={salt_source!r} requested but ``_resolve_salt`` returned {resolved_source!r}.  "
            "Set FORGELM_AUDIT_SECRET (env_var mode) or unset it (per_dir mode) and retry.",
            EXIT_CONFIG_ERROR,
        )
    return _hash_target_id(query, salt), "hash"


def _scan_file(path: str, pattern: re.Pattern[str]) -> List[Dict[str, Any]]:
    """Walk one JSONL file; return every line where ``pattern`` matches.

    Each match record carries:

    - ``file`` — absolute path of the file.
    - ``line`` — 1-based line number.
    - ``snippet`` — at most ``_SNIPPET_MAX_CHARS`` characters around
      the match, with the matched span left intact so the operator can
      eyeball the hit.  We deliberately do NOT mask the snippet: the
      whole point of the access request is to surface the verbatim
      data the subject asked about.

    Raises :class:`OSError` on read failure; the caller handles it.
    """
    matches: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            stripped = line.rstrip("\n")
            if not pattern.search(stripped):
                continue
            matches.append(
                {
                    "file": path,
                    "line": line_no,
                    "snippet": _truncate_snippet(stripped),
                }
            )
    return matches


def _truncate_snippet(line: str) -> str:
    """Centre-truncate ``line`` to at most ``_SNIPPET_MAX_CHARS``.

    For lines longer than the budget we keep both ends with a literal
    ``…`` separator so the operator can see the start and tail context
    around the match.  Short lines pass through unchanged.
    """
    if len(line) <= _SNIPPET_MAX_CHARS:
        return line
    half = (_SNIPPET_MAX_CHARS - 1) // 2
    return f"{line[:half]}…{line[-half:]}"


def _hash_for_audit(query: str) -> str:
    """SHA-256 the operator's raw query for the audit event.

    Article 15 access requests must not write the subject's identifier
    into the audit log: the very thing we're letting the subject query
    is precisely what would be re-introduced if we logged it raw.  We
    therefore log a salt-free SHA-256 (the salt's job is collision
    resistance for ``target_id`` matching, not for audit obfuscation;
    here we only need a stable per-identifier fingerprint so a
    compliance reviewer can correlate two queries about the same
    subject without seeing the subject's data).
    """
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


def _run_reverse_pii_cmd(args, output_format: str) -> None:
    """Top-level dispatcher for ``forgelm reverse-pii``."""
    query = _validate_query(getattr(args, "query", None), output_format)
    identifier_type = _validate_identifier_type(getattr(args, "type", "custom") or "custom", output_format)
    globs = list(getattr(args, "files", None) or [])
    if not globs:
        _output_error_and_exit(
            output_format,
            "reverse-pii requires at least one positional <jsonl-glob> argument "
            "(e.g. `forgelm reverse-pii --query alice@example.com data/*.jsonl`).",
            EXIT_CONFIG_ERROR,
        )

    files = _resolve_files(globs, output_format)
    output_dir = getattr(args, "output_dir", None) or os.path.dirname(os.path.abspath(files[0])) or "."
    salt_source = getattr(args, "salt_source", None)
    scan_query, scan_mode = _resolve_query_form(query, salt_source, output_dir, output_format)
    pattern = _build_search_pattern(scan_query, identifier_type, output_format)

    audit = _maybe_audit_logger(getattr(args, "audit_dir", None) or output_dir)
    query_hash = _hash_for_audit(query)

    matches: List[Dict[str, Any]] = []
    files_scanned: List[Dict[str, Any]] = []
    try:
        for path in files:
            file_matches = _scan_file(path, pattern)
            matches.extend(file_matches)
            files_scanned.append({"path": path, "match_count": len(file_matches)})
    except OSError as exc:
        if audit is not None:
            audit.log_event(
                _EVT_ACCESS_REQUEST_QUERY,
                query_hash=query_hash,
                identifier_type=identifier_type,
                scan_mode=scan_mode,
                files_scanned=[fs["path"] for fs in files_scanned],
                match_count=len(matches),
                error_class=exc.__class__.__name__,
                error_message=str(exc),
            )
        _output_error_and_exit(
            output_format,
            f"Failed reading corpus file mid-scan: {exc}.  Partial matches surfaced before the failure are not emitted.",
            EXIT_TRAINING_ERROR,
        )

    if audit is not None:
        audit.log_event(
            _EVT_ACCESS_REQUEST_QUERY,
            query_hash=query_hash,
            identifier_type=identifier_type,
            scan_mode=scan_mode,
            files_scanned=[fs["path"] for fs in files_scanned],
            match_count=len(matches),
        )

    payload: Dict[str, Any] = {
        "success": True,
        "query_hash": query_hash,
        "identifier_type": identifier_type,
        "scan_mode": scan_mode,
        "matches": matches,
        "files_scanned": files_scanned,
        "match_count": len(matches),
    }
    _emit_reverse_pii_result(payload, output_format)
    sys.exit(EXIT_SUCCESS)


def _emit_reverse_pii_result(payload: Dict[str, Any], output_format: str) -> None:
    """Render the result envelope as JSON or human text."""
    if output_format == "json":
        print(json.dumps(payload, indent=2, default=str))
        return
    match_count = payload["match_count"]
    files_scanned = payload["files_scanned"]
    if match_count == 0:
        print(
            f"No matches for identifier hash {payload['query_hash'][:16]}… "
            f"({payload['identifier_type']}, {payload['scan_mode']} mode) in "
            f"{len(files_scanned)} file(s)."
        )
        return
    print(
        f"Found {match_count} match(es) for identifier hash {payload['query_hash'][:16]}… "
        f"({payload['identifier_type']}, {payload['scan_mode']} mode):"
    )
    for hit in payload["matches"]:
        print(f"  {hit['file']}:{hit['line']}  {hit['snippet']}")
    print()
    print(f"Files scanned: {len(files_scanned)}")
    for fs in files_scanned:
        print(f"  {fs['path']}: {fs['match_count']} match(es)")


def _maybe_audit_logger(audit_dir: str):
    """Best-effort construct the AuditLogger.

    Mirrors :func:`forgelm.cli.subcommands._cache._maybe_audit_logger` —
    a missing operator identity should not abort an Article 15 access
    request (the subject still gets their answer; the chain just
    skips the breadcrumb).
    """
    try:
        from forgelm.compliance import AuditLogger
        from forgelm.config import ConfigError

        return AuditLogger(audit_dir)
    except ConfigError as exc:
        logger.debug("reverse-pii: AuditLogger init failed (%s); continuing without audit log.", exc)
        return None
    except Exception as exc:  # noqa: BLE001 — best-effort: audit is optional context here. # NOSONAR
        logger.debug("reverse-pii: AuditLogger init crashed (%s); continuing without audit log.", exc)
        return None


__all__ = [
    "_run_reverse_pii_cmd",
    "_validate_query",
    "_validate_identifier_type",
    "_build_search_pattern",
    "_resolve_files",
    "_resolve_query_form",
    "_scan_file",
    "_truncate_snippet",
    "_hash_for_audit",
    "_emit_reverse_pii_result",
]

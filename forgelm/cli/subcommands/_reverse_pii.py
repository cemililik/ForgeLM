"""``forgelm reverse-pii`` — GDPR Article 15 right-of-access subcommand.

Phase 38 closure of GH-014.  Companion to ``forgelm purge`` (Phase 21,
Article 17 right-to-erasure): where ``purge`` lets a data subject ask
"delete my row," ``reverse-pii`` lets the same subject ask "is my row
in the corpus at all, and if so, where?"

The subcommand walks a glob of JSONL corpora and reports every line
where a supplied identifier (e-mail, phone, TR national ID, custom
regex, or hash-masked digest) appears.  Two complementary scan modes:

1. **Plaintext residual scan** (default).  Searches for the identifier
   as a literal substring (``re.escape`` applied; the dot in
   ``alice@example.com`` is a literal dot, not "any character") — the
   path that surfaces *mask leaks* (operator believed the corpus was
   masked but a residual span was missed by the masking pass).  This
   is the audit-time honest-PII check.
2. **Hash-mask scan** (``--salt-source per_dir`` or ``--salt-source
   env_var``).  Computes ``SHA256(salt + identifier)`` using the same
   per-output-dir salt that ``forgelm purge`` uses for its
   ``target_id`` hashing, then searches every JSONL line for that
   digest.  This mode targets corpora that an external pipeline masked
   by embedding ``SHA256(salt + identifier)`` digests.  ForgeLM itself
   does not ship a hash-replacement ingest strategy; this mode is for
   operators who built one outside the toolkit using purge's salt.

Audit chain: every invocation writes a ``data.access_request_query``
event with the identifier *salted-and-hashed* (never raw — Article 15
access requests must not themselves leak the subject's identifier
into the audit log; the salt comes from the same per-output-dir
file purge uses, so a wordlist attack against the audit log would
require the operator's salt file too) and the per-file match count.
An operator who later runs ``forgelm verify-audit`` sees a forensic
record that the request was processed without the audit log itself
becoming a residual leak.  Cross-tool correlation: the digest written
here matches the ``target_id`` digest ``forgelm purge`` writes for
the same identifier in the same output_dir, so a compliance reviewer
auditing "every event about subject X" sees a single connected
timeline.

Exit codes (per ``docs/standards/error-handling.md``):

- 0 — command ran (matches reported, may be empty).
- 1 — config error (empty/whitespace ``--query``, unparseable regex
  for ``--type custom``, glob pattern resolved to zero files,
  ``--salt-source`` requested without the matching salt source
  available).
- 2 — runtime error (I/O failure walking the corpus, audit-log write
  failure when an audit dir was supplied, custom-regex ReDoS timeout,
  malformed UTF-8 mid-corpus, audit-init failure when --audit-dir was
  explicitly supplied).
"""

from __future__ import annotations

import glob as _glob
import hashlib
import json
import os
import re
import signal as _signal
import sys
from typing import Any, Dict, List, NoReturn, Optional, Tuple

from .._exit_codes import EXIT_CONFIG_ERROR, EXIT_SUCCESS, EXIT_TRAINING_ERROR
from .._logging import logger

_EVT_ACCESS_REQUEST_QUERY = "data.access_request_query"

# Snippet shape: report at most this many characters around the match
# so the operator can verify the hit but the JSON envelope does not
# itself leak unbounded surrounding context.
_SNIPPET_MAX_CHARS = 160

# Bound the audit event's ``error_message`` field so a future refactor
# cannot accidentally leak operator-controlled raw data through
# ``str(exc)`` (e.g. ``raise OSError(f"row {line!r} malformed")``).
_AUDIT_ERROR_MESSAGE_MAX = 200

# Custom-regex ReDoS guard: per-file scan budget in seconds.  POSIX
# only (SIGALRM); on Windows the guard is a no-op and operators are
# expected to vet their regex themselves.
_CUSTOM_REGEX_TIMEOUT_S = 30

# Identifier-type keys.  ``literal`` (default) treats ``--query`` as
# an exact substring; every category-specific type does the same plus
# a mnemonic in audit + envelope; ``custom`` interprets ``--query`` as
# an arbitrary Python regex.  The literal-default fix closes the
# F-W3-02 false-positive trap where a default-``custom`` regex
# silently treated dots in e-mails as wildcards.
_IDENTIFIER_TYPES: Tuple[str, ...] = (
    "literal",
    "email",
    "phone",
    "tr_id",
    "us_ssn",
    "iban",
    "credit_card",
    "custom",
)


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
    """Refuse identifier types we don't know how to scan for.

    Argparse already enforces the choice set via ``choices=``; this
    dispatcher-side guard is a safety net for direct library callers
    who construct the ``args`` namespace themselves.
    """
    if identifier_type not in _IDENTIFIER_TYPES:
        _output_error_and_exit(
            output_format,
            f"--type {identifier_type!r} is not recognised.  Choose one of: {', '.join(_IDENTIFIER_TYPES)}.",
            EXIT_CONFIG_ERROR,
        )
    return identifier_type


def _build_search_pattern(query: str, identifier_type: str, output_format: str) -> re.Pattern[str]:
    """Compile the regex used to scan each JSONL line.

    For ``--type custom`` the operator's ``--query`` is interpreted as
    a regex.  For every other type (``literal``, ``email``, …) the
    query is treated as a literal string and wrapped in ``re.escape``
    — the goal is "find this exact identifier", not "find anything
    matching its shape" (the audit-time detector already handles the
    latter).
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

    Operators who pass a literal directory get a targeted diagnostic
    pointing them at the glob-form they probably meant — silent skip
    of the whole input set is too easy to miss.
    """
    resolved: List[str] = []
    seen: set[str] = set()
    saw_directory: Optional[str] = None
    for pattern in globs:
        for match in sorted(_glob.glob(pattern, recursive=True)):
            if os.path.isdir(match):
                saw_directory = match
                continue
            if not os.path.isfile(match):
                continue
            absolute = os.path.abspath(match)
            if absolute in seen:
                continue
            seen.add(absolute)
            resolved.append(absolute)
    if not resolved:
        if saw_directory is not None:
            _output_error_and_exit(
                output_format,
                f"{saw_directory!r} is a directory, not a JSONL file.  "
                f"Pass a glob (e.g. {saw_directory!r}/*.jsonl) or a concrete file path.",
                EXIT_CONFIG_ERROR,
            )
        _output_error_and_exit(
            output_format,
            f"No files matched the supplied glob pattern(s): {globs!r}.  "
            "Check the path or run with shell-expanded paths.",
            EXIT_CONFIG_ERROR,
        )
    return resolved


def _resolve_query_form(
    query: str,
    salt_source: Optional[str],
    output_dir: str,
    output_format: str,
) -> Tuple[str, str, Optional[bytes], str]:
    """Map the operator-supplied identifier to the form actually
    searched in the corpus.

    Returns ``(scan_query, scan_mode, salt, salt_source_label)``:

    - ``scan_query`` — the literal/regex string to compile.
    - ``scan_mode`` — ``"plaintext"`` or ``"hash"``.
    - ``salt`` — the per-output-dir salt bytes, resolved if the audit
      hash needs it (always, post F-W3-PS-01) or ``None`` for the
      degraded path where salt resolution is unavailable.
    - ``salt_source_label`` — ``"per_dir" | "env_var" | "plaintext"``;
      recorded in the audit event so a reviewer can tell whether two
      digests were salted the same way.

    ``--salt-source`` triggers hash mode and reuses the per-output-dir
    salt resolution from ``forgelm purge`` so the two subcommands
    cannot drift on hashing semantics.
    """
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

    if salt_source is None:
        return query, "plaintext", salt, resolved_source

    if salt_source != resolved_source:
        # Direction-aware diagnostic: telling the operator which
        # specific knob to adjust beats a generic "or vice versa"
        # message that requires them to re-derive the failure mode.
        if salt_source == "env_var":
            hint = "Set FORGELM_AUDIT_SECRET to the env-mode secret and retry."
        else:  # salt_source == "per_dir"
            hint = (
                "Unset FORGELM_AUDIT_SECRET (e.g. `env -u FORGELM_AUDIT_SECRET forgelm reverse-pii ...`) "
                "to force per-dir mode and retry."
            )
        _output_error_and_exit(
            output_format,
            f"--salt-source={salt_source!r} requested but ``_resolve_salt`` returned {resolved_source!r}.  {hint}",
            EXIT_CONFIG_ERROR,
        )
    return _hash_target_id(query, salt), "hash", salt, resolved_source


def _truncate_snippet(line: str, match_span: Tuple[int, int]) -> str:
    """Centre the snippet on the match span, capped at ``_SNIPPET_MAX_CHARS``.

    The whole point of the snippet (operator-eyeball verification of
    the hit) is defeated if a long-line head+tail truncation drops the
    matched span itself — F-W3-03.  We anchor a window of
    ``_SNIPPET_MAX_CHARS`` characters around the match and ellide the
    ends only.  Short lines pass through unchanged.

    Operates on Python ``str`` (code-points), so multi-byte UTF-8
    runes are not split mid-byte.
    """
    if len(line) <= _SNIPPET_MAX_CHARS:
        return line
    start, end = match_span
    budget = _SNIPPET_MAX_CHARS - 2  # reserve room for two literal "…"
    match_len = max(end - start, 0)
    ctx = max((budget - match_len) // 2, 0)
    win_start = max(start - ctx, 0)
    win_end = min(end + ctx, len(line))
    head = "…" if win_start > 0 else ""
    tail = "…" if win_end < len(line) else ""
    return f"{head}{line[win_start:win_end]}{tail}"


def _scan_file(path: str, pattern: re.Pattern[str]) -> List[Dict[str, Any]]:
    """Walk one JSONL file; return every line where ``pattern`` matches.

    Each match record carries:

    - ``file`` — absolute path of the file.
    - ``line`` — 1-based line number.
    - ``snippet`` — at most ``_SNIPPET_MAX_CHARS`` characters around
      the match, with the matched span centred so the operator can
      eyeball the hit.  We deliberately do NOT mask the snippet: the
      whole point of the access request is to surface the verbatim
      data the subject asked about.

    Raises :class:`OSError` on read failure (decoded as a runtime
    error by the dispatcher); raises :class:`UnicodeDecodeError` on
    malformed UTF-8 (also decoded as runtime error; F-W3-04).
    """
    matches: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            stripped = line.rstrip("\n")
            match = pattern.search(stripped)
            if match is None:
                continue
            matches.append(
                {
                    "file": path,
                    "line": line_no,
                    "snippet": _truncate_snippet(stripped, match.span()),
                }
            )
    return matches


def _scan_files_with_redos_guard(
    files: List[str],
    pattern: re.Pattern[str],
    identifier_type: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Walk every file once; centralise the per-file ReDoS budget.

    On POSIX a ``SIGALRM`` per-file budget of ``_CUSTOM_REGEX_TIMEOUT_S``
    seconds bounds the worst-case backtracking cost of a
    ``--type custom`` pattern (F-W3-PS-03 / F-W3-07 / F-W3S-03).  On
    Windows ``SIGALRM`` is unavailable; the scan runs without a guard
    and the operator is expected to vet their regex.  The exit-code
    contract is unchanged either way — a timeout converts to
    ``OSError`` which the dispatcher converts to ``EXIT_TRAINING_ERROR``
    plus a failure-flavoured audit event.
    """
    matches: List[Dict[str, Any]] = []
    files_scanned: List[Dict[str, Any]] = []
    use_alarm = identifier_type == "custom" and os.name == "posix" and hasattr(_signal, "SIGALRM")
    for path in files:
        if use_alarm:
            file_matches = _scan_file_with_alarm(path, pattern)
        else:
            file_matches = _scan_file(path, pattern)
        matches.extend(file_matches)
        files_scanned.append({"path": path, "match_count": len(file_matches)})
    return matches, files_scanned


def _scan_file_with_alarm(path: str, pattern: re.Pattern[str]) -> List[Dict[str, Any]]:
    """POSIX-only wrapper enforcing ``_CUSTOM_REGEX_TIMEOUT_S``.

    Translates a ReDoS hang into a clean ``OSError`` so the dispatcher
    handles it via the same audit-event path as a read failure.
    """

    def _alarm(_sig, _frame):  # pragma: no cover — signal handler
        raise OSError(f"reverse-pii scan of {path!r} exceeded {_CUSTOM_REGEX_TIMEOUT_S}s (custom regex ReDoS guard)")

    previous = _signal.signal(_signal.SIGALRM, _alarm)
    _signal.alarm(_CUSTOM_REGEX_TIMEOUT_S)
    try:
        return _scan_file(path, pattern)
    finally:
        _signal.alarm(0)
        _signal.signal(_signal.SIGALRM, previous)


def _hash_for_audit(query: str, salt: Optional[bytes]) -> str:
    """Salted SHA-256 of the operator's raw query for the audit event.

    Article 15 access requests must not write the subject's identifier
    into the audit log: the very thing we're letting the subject query
    is precisely what would be re-introduced if we logged it raw.

    We reuse the per-output-dir salt that ``forgelm purge`` uses for
    its ``target_id`` hashing (F-W3-PS-01).  Two consequences:

    1. A wordlist attack against the audit log requires the operator's
       ``.forgelm_audit_salt`` file (and, if ``FORGELM_AUDIT_SECRET``
       is set, the env secret too).  Salt-free SHA-256 of low-entropy
       identifiers (e-mails, phone numbers) is brute-forcible from a
       commodity wordlist; the salt closes that gap.
    2. A purge → reverse-pii cycle for the same subject in the same
       ``output_dir`` produces matching digests, so a compliance
       reviewer correlating Article 17 + Article 15 events for one
       subject sees a connected timeline.

    The salt is ``None`` only on the legacy / pre-resolution code
    path; production callers always pass the resolved salt.
    """
    raw = query.encode("utf-8")
    if salt is None:
        return hashlib.sha256(raw).hexdigest()
    return hashlib.sha256(salt + raw).hexdigest()


def _bound_audit_error_message(message: str) -> str:
    """Cap ``error_message`` so a future refactor cannot leak operator
    data through ``str(exc)`` (F-W3-09)."""
    if len(message) <= _AUDIT_ERROR_MESSAGE_MAX:
        return message
    return message[:_AUDIT_ERROR_MESSAGE_MAX] + "…[truncated]"


def _resolve_audit_dir(output_dir: str, audit_dir_override: Optional[str]) -> str:
    """Return the audit-log root for this invocation.

    F-W3-06 / F-W3S-02 fix: the previous default (``audit_dir =
    output_dir``) wrote ``audit_log.jsonl`` next to the corpus the
    subject was asking about — bad colocation for an Article 12
    durable record.  We now default to ``<output_dir>/audit/``,
    matching the ``forgelm audit`` subcommand's convention.  An
    explicit ``--audit-dir`` always wins.
    """
    if audit_dir_override:
        return audit_dir_override
    return os.path.join(output_dir, "audit")


def _maybe_audit_logger(
    audit_dir: str,
    *,
    explicit: bool,
    output_format: str,
):
    """Construct the AuditLogger; fail closed when the operator opted in.

    F-W3-01 / F-W3-PS-02 / F-W3S-01 fix.  Two distinct policies:

    - ``ConfigError`` (operator-identity not resolvable) is the only
      "best-effort" branch.  We log at WARNING (not DEBUG, so the
      operator sees the audit was skipped) and return ``None``.
    - Every other exception class — ``OSError`` from a read-only audit
      dir, ``ValueError`` from a corrupt chain head, etc. — is a hard
      failure.  When the operator passed ``--audit-dir`` explicitly
      (``explicit=True``) we refuse with ``EXIT_TRAINING_ERROR`` so a
      regulator never sees a "scan completed" envelope without a
      matching forensic-chain entry.  When the dir is the implicit
      default we still fail closed because the audit-chain contract is
      a non-negotiable Article 15 requirement.
    """
    try:
        from forgelm.compliance import AuditLogger
        from forgelm.config import ConfigError

        return AuditLogger(audit_dir)
    except ConfigError as exc:
        logger.warning(
            "reverse-pii: AuditLogger init refused (%s); access request "
            "will run but the regulatory chain will NOT record it.  Set "
            "FORGELM_OPERATOR=<id> or FORGELM_ALLOW_ANONYMOUS_OPERATOR=1 "
            "to restore audit emission.",
            exc,
        )
        return None
    except (OSError, ValueError) as exc:
        _output_error_and_exit(
            output_format,
            (
                f"reverse-pii: AuditLogger init failed for {audit_dir!r} ({exc.__class__.__name__}: {exc}).  "
                "Refusing to process an Article 15 access request without a forensic record.  "
                f"{'Pass --audit-dir <writable-dir>' if not explicit else 'Fix the audit-dir permission / chain integrity'} "
                "and retry."
            ),
            EXIT_TRAINING_ERROR,
        )


def _emit_audit_event(
    audit,
    *,
    query_hash: str,
    identifier_type: str,
    scan_mode: str,
    salt_source: str,
    files_scanned: List[Dict[str, Any]],
    match_count: int,
    error_class: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    """Centralise the ``data.access_request_query`` emit so success
    and failure paths cannot drift on payload shape.  ``salt_source``
    is recorded in every event (F-W3-PS-07)."""
    payload: Dict[str, Any] = {
        "query_hash": query_hash,
        "identifier_type": identifier_type,
        "scan_mode": scan_mode,
        "salt_source": salt_source,
        "files_scanned": [fs["path"] for fs in files_scanned],
        "match_count": match_count,
    }
    if error_class is not None:
        payload["error_class"] = error_class
    if error_message is not None:
        payload["error_message"] = _bound_audit_error_message(error_message)
    audit.log_event(_EVT_ACCESS_REQUEST_QUERY, **payload)


def _run_reverse_pii_cmd(args, output_format: str) -> None:
    """Top-level dispatcher for ``forgelm reverse-pii``."""
    query = _validate_query(getattr(args, "query", None), output_format)
    identifier_type = _validate_identifier_type(getattr(args, "type", "literal") or "literal", output_format)
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

    # F-W3-08 fix: validate the regex before any filesystem side effects
    # (salt-file creation).  We build the search pattern over the raw
    # query first; if the operator typed an invalid custom regex they
    # get exit 1 without leaving a salt file behind.
    _build_search_pattern(query, identifier_type, output_format)

    scan_query, scan_mode, salt, salt_source_label = _resolve_query_form(query, salt_source, output_dir, output_format)
    pattern = _build_search_pattern(scan_query, identifier_type, output_format)

    audit_dir_override = getattr(args, "audit_dir", None)
    audit_dir = _resolve_audit_dir(output_dir, audit_dir_override)
    audit = _maybe_audit_logger(
        audit_dir,
        explicit=audit_dir_override is not None,
        output_format=output_format,
    )
    query_hash = _hash_for_audit(query, salt)

    matches: List[Dict[str, Any]] = []
    files_scanned: List[Dict[str, Any]] = []
    try:
        matches, files_scanned = _scan_files_with_redos_guard(files, pattern, identifier_type)
    except (OSError, UnicodeDecodeError) as exc:
        if audit is not None:
            try:
                _emit_audit_event(
                    audit,
                    query_hash=query_hash,
                    identifier_type=identifier_type,
                    scan_mode=scan_mode,
                    salt_source=salt_source_label,
                    files_scanned=files_scanned,
                    match_count=len(matches),
                    error_class=exc.__class__.__name__,
                    error_message=str(exc),
                )
            except Exception as audit_exc:  # noqa: BLE001 — fail-closed on audit error.
                _output_error_and_exit(
                    output_format,
                    f"reverse-pii: failed to write the Article 15 failure audit event ({audit_exc}).",
                    EXIT_TRAINING_ERROR,
                )
        _output_error_and_exit(
            output_format,
            f"Failed reading corpus file mid-scan: {exc}.  Partial matches surfaced before the failure are not emitted.",
            EXIT_TRAINING_ERROR,
        )

    if audit is not None:
        try:
            _emit_audit_event(
                audit,
                query_hash=query_hash,
                identifier_type=identifier_type,
                scan_mode=scan_mode,
                salt_source=salt_source_label,
                files_scanned=files_scanned,
                match_count=len(matches),
            )
        except Exception as audit_exc:  # noqa: BLE001 — fail-closed on audit error.
            _output_error_and_exit(
                output_format,
                f"reverse-pii: failed to write the Article 15 success audit event ({audit_exc}).",
                EXIT_TRAINING_ERROR,
            )

    payload: Dict[str, Any] = {
        "success": True,
        "query_hash": query_hash,
        "identifier_type": identifier_type,
        "scan_mode": scan_mode,
        "salt_source": salt_source_label,
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
    print("WARNING: snippets below contain raw corpus content (PII).  Do not redirect this output to a persistent log.")
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
    "_resolve_audit_dir",
    "_emit_audit_event",
]

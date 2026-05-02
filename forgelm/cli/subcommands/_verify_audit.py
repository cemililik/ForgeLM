"""``forgelm verify-audit`` dispatcher (Phase 6 closure plan)."""

from __future__ import annotations

import os
import sys

from .._exit_codes import EXIT_CONFIG_ERROR, EXIT_SUCCESS, EXIT_TRAINING_ERROR


def _run_verify_audit_cmd(args) -> int:
    """Phase 6 (closure plan) dispatch for ``forgelm verify-audit LOG_PATH``.

    Returns the process exit code rather than calling :func:`sys.exit`
    directly so the dispatcher can route the (0/1/2) outcome through the
    same code path as the other subcommands. Exit-code contract:

    - ``0`` — SHA-256 chain (and HMAC tags, when verified) intact.
    - ``1`` — tamper or corruption detected (chain break, HMAC mismatch,
      manifest mismatch, JSON decode error).
    - ``2`` — option error (``--require-hmac`` without a secret env var)
      or file/permission error reading the log.
    """
    from ...compliance import verify_audit_log

    secret_var = args.hmac_secret_env or ""
    hmac_secret = os.getenv(secret_var) if secret_var else None
    require_hmac = bool(getattr(args, "require_hmac", False))

    if require_hmac and not hmac_secret:
        print(
            f"ERROR: --require-hmac specified but ${secret_var} is unset.",
            file=sys.stderr,
        )
        return EXIT_TRAINING_ERROR  # 2 — option/config error

    if not os.path.isfile(args.log_path):
        print(f"ERROR: audit log not found: {args.log_path}", file=sys.stderr)
        return EXIT_TRAINING_ERROR

    result = verify_audit_log(
        args.log_path,
        hmac_secret=hmac_secret,
        require_hmac=require_hmac,
    )

    if result.valid:
        suffix = " (HMAC validated)" if hmac_secret else ""
        print(f"OK: {result.entries_count} entries verified{suffix}")
        return EXIT_SUCCESS

    line = result.first_invalid_index
    if line is None:
        print(f"FAIL: {result.reason}", file=sys.stderr)
    else:
        print(f"FAIL at line {line}: {result.reason}", file=sys.stderr)
    return EXIT_CONFIG_ERROR  # 1 — chain/HMAC failure

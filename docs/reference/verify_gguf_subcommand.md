# `forgelm verify-gguf` — Reference

> **Audience:** Deployment operators and CI gates verifying exported GGUF model files before serving via `llama.cpp`, Ollama, vLLM, or LM Studio.
> **Mirror:** [verify_gguf_subcommand-tr.md](verify_gguf_subcommand-tr.md)

The `verify-gguf` subcommand performs a three-layer integrity check on a GGUF model file: it validates the 4-byte `GGUF` magic header, parses the metadata block via the optional `gguf` Python package (when installed), and recomputes a SHA-256 comparison against the `<path>.sha256` sidecar (when present). The CLI delegates to the library entry point `forgelm.cli.subcommands._verify_gguf.verify_gguf` and returns a structured `VerifyGgufResult`.

## Synopsis

```text
forgelm verify-gguf [--output-format {text,json}]
                    [-q] [--log-level {DEBUG,INFO,WARNING,ERROR}]
                    path
```

`path` (positional, required) — path to the GGUF model file. The optional sidecar `<path>.sha256` is auto-detected.

## Flags

| Flag | Default | Description |
|---|---|---|
| `--output-format {text,json}` | `text` | `text` (default) prints `OK:` / `FAIL:` plus the per-check breakdown; `json` prints the full `VerifyGgufResult` envelope (`{"success", "valid", "reason", "checks", "path"}`) where `checks` carries `magic_ok`, `metadata_parsed`, `sidecar_present`, `sidecar_match`, plus `tensor_count`, `sha256_actual`, `sha256_expected` when applicable. |
| `-q`, `--quiet` | _off_ | Suppress INFO logs. |
| `--log-level {DEBUG,INFO,WARNING,ERROR}` | `INFO` | Set logging verbosity. |
| `-h`, `--help` | — | Show argparse help and exit. |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Magic header is `GGUF` AND (when `gguf` is installed) metadata block parses AND (when sidecar present) SHA-256 matches. |
| `1` | Caller / input error: path is missing, is not a regular file, or the magic mismatches; metadata corruption (`gguf` reader raised mid-parse); malformed sidecar (non-hex / wrong length); SHA-256 mismatch. The artifact is not safe to serve. |
| `2` | Genuine runtime I/O failure on an existing file — read errors, permission denied mid-read, etc. The path was accessible to `os.path.isfile` but became unreadable during verification. |

The codes are emitted by `forgelm/cli/subcommands/_verify_gguf.py::_run_verify_gguf_cmd`. Public-contract semantics are pinned in `docs/standards/error-handling.md`.

## The three layers

| Layer | Required? | Failure mode |
|---|---|---|
| **Magic header** | Always. First 4 bytes must equal `b"GGUF"`. | Anything else → exit `1` (file is not GGUF or download corrupted). |
| **Metadata block** | When the optional `gguf` package is installed. Parses the metadata + tensor descriptors via the upstream reader. | Reader raises mid-parse → exit `1` (writer crashed mid-stream or file truncated). Package absent → check is skipped (the magic + sidecar checks remain load-bearing). |
| **SHA-256 sidecar** | When `<path>.sha256` exists. Recomputes file SHA-256 and compares against the sidecar's first whitespace-separated token (sha256sum format `<hex> *<filename>` is supported). | Mismatch → exit `1`. Sidecar present but contents are not a 64-character hex digest → exit `1` (fail closed against malformed-sidecar masquerade). Sidecar absent → check is skipped silently. |

The exporter writes the sidecar by default (see [`docs/usermanuals/en/deployment/gguf-export.md`](../usermanuals/en/deployment/gguf-export.md)); operators receiving GGUF files from third parties should request the sidecar alongside.

## Audit events emitted

`forgelm verify-gguf` is a **read-only verifier** and emits **no** entries to `audit_log.jsonl`. The events that signal GGUF *production* (not verification) are scoped to the export step and currently ride the run-level `pipeline.completed` envelope; see [audit_event_catalog.md](audit_event_catalog.md).

## Examples

### Text output (default)

```shell
$ forgelm verify-gguf checkpoints/run/exports/model-q4_k_m.gguf
OK: checkpoints/run/exports/model-q4_k_m.gguf
  GGUF magic OK, metadata parsed, SHA-256 sidecar match
    magic_ok: True
    metadata_parsed: True
    sidecar_present: True
    sidecar_match: True
    tensor_count: 291
    sha256_actual: a4c1f2…
    sha256_expected: a4c1f2…
```

### JSON output (CI consumers)

```shell
$ forgelm verify-gguf --output-format json \
    checkpoints/run/exports/model-q4_k_m.gguf
{
  "success": true,
  "valid": true,
  "reason": "GGUF magic OK, metadata parsed, SHA-256 sidecar match",
  "checks": {
    "magic_ok": true,
    "metadata_parsed": true,
    "sidecar_present": true,
    "sidecar_match": true,
    "tensor_count": 291,
    "sha256_actual": "a4c1f2…",
    "sha256_expected": "a4c1f2…"
  },
  "path": "/abs/path/checkpoints/run/exports/model-q4_k_m.gguf"
}
```

### Failure: magic mismatch

```shell
$ forgelm verify-gguf checkpoints/run/exports/wrong-file.bin
FAIL: checkpoints/run/exports/wrong-file.bin
  Magic header mismatch: expected b'GGUF', got b'PK\x03\x04'.  Not a GGUF file or corrupted.
    magic_ok: False
$ echo $?
1
```

### Failure: SHA-256 sidecar mismatch (post-export tampering)

```shell
$ forgelm verify-gguf checkpoints/run/exports/model-q4_k_m.gguf
FAIL: checkpoints/run/exports/model-q4_k_m.gguf
  SHA-256 sidecar mismatch — file modified after export.  Expected a4c1f2cb1d0a8e91…, got 91e2bf03c4a1c1ab….
$ echo $?
1
```

### Failure: malformed sidecar

```shell
$ forgelm verify-gguf checkpoints/run/exports/model-q4_k_m.gguf
FAIL: checkpoints/run/exports/model-q4_k_m.gguf
  Malformed SHA-256 sidecar: expected a 64-character hex digest, got 'TODO: regenerate'.  Regenerate the sidecar (e.g. `sha256sum model.gguf > model.gguf.sha256`) or remove it to skip the check.
$ echo $?
1
```

### Optional dependency absent

When the `gguf` package is not installed, the metadata-parse layer is skipped silently — the magic + sidecar checks remain load-bearing:

```shell
$ pip uninstall -y gguf
$ forgelm verify-gguf checkpoints/run/exports/model-q4_k_m.gguf
OK: checkpoints/run/exports/model-q4_k_m.gguf
  GGUF magic OK, SHA-256 sidecar match
    magic_ok: True
    metadata_parsed: False
    sidecar_present: True
    sidecar_match: True
```

Install the optional extra to add the metadata layer back: `pip install gguf`.

## See also

- [`audit_event_catalog.md`](audit_event_catalog.md) — canonical event vocabulary.
- [`verify_audit.md`](verify_audit.md) — companion verifier for `audit_log.jsonl`.
- [`verify_annex_iv_subcommand.md`](verify_annex_iv_subcommand.md) — companion verifier for the Annex IV technical-documentation artifact.
- [GGUF Export usermanual page](../usermanuals/en/deployment/gguf-export.md) — operator-facing primer on the production side that writes the sidecar this verifier consumes.
- `forgelm.cli.subcommands._verify_gguf.verify_gguf` — the library entry point integrators call directly without going through the CLI.

---
title: Secrets Scrubbing
description: Detect and redact AWS keys, GitHub PATs, JWTs, PEM blocks, and other credentials from training data.
---

# Secrets Scrubbing

Code repositories, support tickets, and operational logs leak credentials. Once those credentials end up in a training set and the model is deployed, anyone who chats with the model can extract them. Secrets scrubbing prevents this at ingest.

## What gets detected

The bundled detector ships **9 secret families** under `_SECRET_PATTERNS` (`forgelm/data_audit/_secrets.py::_SECRET_PATTERNS`):

| Pattern key | Anchor |
|---|---|
| `aws_access_key` | `AKIA` / `ASIA` + 16 uppercase alphanum |
| `github_token` | `ghp_*`, `gho_*`, `ghu_*`, `ghs_*`, `ghr_*`, `github_pat_*` (single combined family) |
| `slack_token` | `xox[baprs]-*` |
| `openai_api_key` | `sk-*` and `sk-proj-*` |
| `google_api_key` | `AIza` + 35 chars |
| `jwt` | Three-segment base64url with canonical JWT header keys (defends against `eyJ.eyJ.X`-shaped prose false positives) |
| `openssh_private_key` | `BEGIN OPENSSH/RSA/DSA/EC PRIVATE KEY` … `END …` (full PEM envelope) |
| `pgp_private_key` | `BEGIN PGP PRIVATE KEY BLOCK` … `END …` |
| `azure_storage_key` | `DefaultEndpointsProtocol=…AccountKey=…` |

All matches are replaced with the literal string `[REDACTED-SECRET]` by `mask_secrets()` (`forgelm/data_audit/_secrets.py::mask_secrets`). The detector does **not** ship per-vendor patterns for Anthropic, Stripe, SendGrid, or Twilio today — operators with those traffic types extend the regex set out-of-tree (Phase 28+ backlog tracks shipping them as opt-in extras).

## Quick example

```shell
$ forgelm ingest ./support-tickets/ \
    --recursive \
    --secrets-mask \
    --output data/tickets.jsonl
✓ masked 47 secrets:
    aws_access_key:       12
    github_token:          8
    jwt:                  18
    openssh_private_key:   2
    openai_api_key:        7
```

## What "PEM block" means

PEM private keys span multiple lines:

```text
-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA1+...
...
-----END RSA PRIVATE KEY-----
```

ForgeLM's PEM detector (`openssh_private_key` family — also covers RSA / DSA / EC envelopes) matches the entire block (BEGIN to END), not just the marker line. Like every other family, the whole block is replaced with `[REDACTED-SECRET]` — there is no per-family token (`mask_secrets()` ships a single `replacement="[REDACTED-SECRET]"` constant; `forgelm/data_audit/_secrets.py::mask_secrets`). This avoids the common bug of detecting the BEGIN line but leaving the key body in the JSONL.

## Audit-only mode

```shell
$ forgelm audit data/tickets.jsonl
✓ format: instructions (8,400 rows)
⚠ secrets: 47 detected (severity: critical)
   12 AWS access keys
   18 JWTs
   ...
```

The secrets scan is always on — it cannot be disabled from the CLI surface (a credential leak in training data is never something the operator should be able to wave away). A `critical` severity exits non-zero so a CI pipeline fails fast.

## Programmatic API

```python
from forgelm.data_audit import detect_secrets, mask_secrets

text = "Use this key: AKIAIOSFODNN7EXAMPLE and JWT eyJhbGc..."
hits = detect_secrets(text)
print(hits)
# [{'category': 'aws_access_key', 'span': (14, 34), 'value': 'AKIAIOSFODNN7EXAMPLE'}]

cleaned = mask_secrets(text)
# "Use this key: [REDACTED-SECRET] and JWT [REDACTED-SECRET]..."
```

## False-positive guards

ForgeLM ships secrets detection with stricter false-positive guards than typical "git-secrets"-style tools, because:

1. False positives in training data corrupt examples (replacing legitimate strings).
2. Many regex-only patterns flag `EXAMPLEKEY` or test fixtures, which makes audit reports useless.

Specific guards:
- **Entropy threshold** for OpenAI / Anthropic keys (random-looking, not human-readable).
- **Context window check** — `AKIA*` only fires if accompanied by a secret-key-shaped neighbour or "aws" context within 100 characters.
- **Test/example exclusion list** — common dummy values (`AKIAIOSFODNN7EXAMPLE`, `xxx`, `your_key_here`) bypass detection.

For a high-stakes audit (e.g. legal disclosure scan), the test-exclusion list is intentional — `forgelm audit` records the surviving findings under `AuditReport.secrets_summary` (one count per pattern type), and the per-row JSON output (`--output-format json`, optional `--output-jsonl`) is the canonical surface for prose-level review. Walk that JSON for any pattern-type count > 0 in your high-stakes audit so a human can confirm none of the dummies are real secrets in disguise. (A dedicated `secret_findings_review_notes` envelope is on the v0.6+ roadmap.)

## Configuration

The secrets scanner is **always-on inside `forgelm audit`** — it has no enable/disable knob and no per-family allow/deny list. Mask-on-emit is controlled by the `secrets_mask: bool` argument on `audit_dataset()` (and the `--secrets-mask` flag on `forgelm ingest`); the replacement string is the single fixed `[REDACTED-SECRET]` constant inside `mask_secrets()`. There is no `ingestion.secrets_mask:` YAML block, no `enabled` / `tag_by_category` / `strict` / `categories` sub-fields — those names appeared in earlier doc drafts but never shipped. To extend or restrict the family set, fork `forgelm/data_audit/_secrets.py::_SECRET_PATTERNS`.

## Common pitfalls

:::warn
**Disabling secrets-mask for "trusted internal" data.** Internal logs are the most common source of credential leaks. The cost of running the masker is essentially zero; the cost of a leaked AWS key in a deployed model is unbounded.
:::

:::warn
**Custom regex without entropy checks.** The biggest cause of secrets-detection false positives is regex-only patterns matching documentation examples. Always pair regex with entropy or context checks.
:::

:::tip
For corpora that legitimately contain certificates / tokens (security training datasets, CTF content), there is no CLI escape hatch — the secrets scan is intentionally always-on (no `--no-secrets` / `--skip-secrets` flag exists, and `forgelm audit` runs the scan unconditionally on every invocation; see the [Audit-only mode](#audit-only-mode) section above for the underlying scan-mode semantics). Mark the rows in your corpus's data-governance manifest as `legitimate_secret_content: true` so a downstream reviewer sees the rationale; `forgelm audit` still flags them, but the reviewer dismisses the flag with the manifest line as evidence.
:::

## See also

- [PII Masking](#/data/pii-masking) — sister feature for personal data.
- [Dataset Audit](#/data/audit) — covers secrets detection in audit-only mode.
- [Document Ingestion](#/data/ingestion) — where secrets-mask is invoked.

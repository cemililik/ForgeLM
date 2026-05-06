---
title: Secrets Scrubbing
description: Detect and redact AWS keys, GitHub PATs, JWTs, PEM blocks, and other credentials from training data.
---

# Secrets Scrubbing

Code repositories, support tickets, and operational logs leak credentials. Once those credentials end up in a training set and the model is deployed, anyone who chats with the model can extract them. Secrets scrubbing prevents this at ingest.

## What gets detected

| Category | Pattern detected |
|---|---|
| **AWS access keys** | `AKIA[0-9A-Z]{16}` + secret-key heuristics |
| **GitHub PATs** | `ghp_*`, `gho_*`, `ghu_*`, `ghs_*`, `ghr_*` |
| **GitHub fine-grained tokens** | `github_pat_*` |
| **Slack tokens** | `xox[bpars]-*` |
| **OpenAI API keys** | `sk-*` (with length and entropy checks) |
| **Anthropic API keys** | `sk-ant-*` |
| **Google API keys** | `AIza*` |
| **JWTs** | Three-segment base64url (header.payload.signature) |
| **PEM private-key blocks** | `BEGIN ... PRIVATE KEY...END` (RSA, EC, OpenSSH, PGP) |
| **Azure storage strings** | `DefaultEndpointsProtocol=...` |
| **Stripe / SendGrid / Twilio** | Service-specific patterns |

All matches are replaced with `[REDACTED-SECRET]` (or per-category tags via `--secrets-tag-by-category`).

## Quick example

```shell
$ forgelm ingest ./support-tickets/ \
    --recursive \
    --secrets-mask \
    --output data/tickets.jsonl
✓ masked 47 secrets:
    aws_access_key: 12
    github_pat:     8
    jwt:            18
    pem_block:      2
    openai_key:     7
```

## What "PEM block" means

PEM private keys span multiple lines:

```text
-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA1+...
...
-----END RSA PRIVATE KEY-----
```

ForgeLM's PEM detector matches the entire block (BEGIN to END), not just the marker line. The whole block is replaced with `[REDACTED-PEM-BLOCK]`. This avoids the common bug of detecting the BEGIN line but leaving the key body in the JSONL.

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

For a high-stakes audit (e.g. legal disclosure scan), the test-exclusion list is intentional — review the scan output's `secret_findings_review_notes` (one row per excluded match, with the prose context) so a human can confirm none of the dummies are real secrets in disguise.

## Configuration

```yaml
ingestion:
  secrets_mask:
    enabled: true
    tag_by_category: true              # use category-specific tags instead of [REDACTED-SECRET]
    strict: false                      # set true to disable false-positive guards
    categories:                        # selectively enable
      - aws_access_key
      - github_pat
      - jwt
      - pem_block
      # omit any to disable
```

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

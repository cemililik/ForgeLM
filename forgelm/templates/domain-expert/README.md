# Domain-Expert template

Use this when you have your own corpus (legal, medical, policy manuals,
product docs) and want a fine-tuned model that speaks your domain's
language.

## Quick start

```bash
# Already have a JSONL dataset
forgelm quickstart domain-expert --dataset ./my-policies.jsonl

# Have raw PDFs / DOCX / EPUB? (requires Phase 11 — `forgelm ingest`)
forgelm ingest ./policies/ --output ./policies.jsonl
forgelm quickstart domain-expert --dataset ./policies.jsonl
```

## Expected dataset shape

The trainer accepts any of the SFT formats ForgeLM supports:

- `{"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}`
- `{"User": "...", "Assistant": "..."}`
- `{"instruction": "...", "output": "..."}`
- pre-formatted `{"text": "..."}`

For domain knowledge transfer, the **messages** format with synthetic
Q&A pairs over your source documents tends to work best.

## When to grow beyond this template

- ~500+ examples and a reasonable HF Hub model are enough for a useful first
  pass on small domain shifts.
- For larger corpora or a domain with lots of jargon, consider running
  `forgelm --generate-data` (synthetic data pipeline) first to expand a
  small seed into many synthetic Q&A pairs before fine-tuning.
- For compliance-sensitive domains (medical, legal), enable
  `evaluation.safety` and the EU AI Act compliance metadata fields after
  the first training run.

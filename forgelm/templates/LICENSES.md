# Quickstart Template Licenses

Every dataset bundled under a template directory is **author-original work**
released under [Creative Commons Attribution-ShareAlike 4.0
International](https://creativecommons.org/licenses/by-sa/4.0/) unless noted
otherwise. Each entry below points at the relevant `data.jsonl`.

| Template | Dataset path | Examples | License | Origin |
|---|---|---|---|---|
| `customer-support` | `forgelm/templates/customer-support/data.jsonl` | ~60 | CC-BY-SA 4.0 | Authored by ForgeLM contributors |
| `code-assistant` | `forgelm/templates/code-assistant/data.jsonl` | ~60 | CC-BY-SA 4.0 | Authored by ForgeLM contributors |
| `domain-expert` | _(no bundled data — user-supplied)_ | — | N/A | Bring your own JSONL or `forgelm ingest` output |
| `medical-qa-tr` | `forgelm/templates/medical-qa-tr/data.jsonl` | ~50 | CC-BY-SA 4.0 | Authored by ForgeLM contributors. **Disclaimers**: educational only, not clinical advice |
| `grpo-math` | `forgelm/templates/grpo-math/data.jsonl` | ~40 | CC-BY-SA 4.0 | Grade-school style math problems authored by ForgeLM contributors |

## What "license-clean" means here

- Every bundled example was written specifically for this repository.
- No scraping, no ingestion of third-party datasets, no GPT-4 / Claude
  generations included.
- CC-BY-SA 4.0 means **anyone can re-share, modify, or fine-tune on top**;
  derivatives must keep the same license and credit ForgeLM.

## Adding a new template

When contributing a new template, you must include:

1. A `data.jsonl` (or `README.md` explaining the BYOD path) under
   `forgelm/templates/<your-template>/`.
2. A `config.yaml` with conservative defaults (QLoRA 4-bit NF4, rank ≤ 8,
   `gradient_checkpointing: true`, safety/compliance opt-in only).
3. A row added to the table above attributing the dataset's origin and
   license.
4. A registry entry in `TEMPLATES` in `forgelm/quickstart.py`.
5. A test row in `tests/test_quickstart.py` exercising the new template via
   `run_quickstart(name, dry_run=True)`.

If the dataset comes from a public source (HuggingFace Hub, public
benchmark, scraped corpus), confirm and document its license — and prefer
**bundling a derivative subset you re-authored** over redistributing
upstream content directly.

## Disclaimer for `medical-qa-tr`

Tıbbi veri seti yalnızca **eğitim/demonstrasyon amaçlıdır**. Üretilen
modeller klinik karar destek sistemi olarak kullanılamaz. Üretilen
yanıtların doğruluğu garanti edilmez; gerçek tıbbi sorularda lisanslı
sağlık profesyonellerine danışılmalıdır. ForgeLM ekibi bu veri seti
üzerinden eğitilmiş modellerin tıbbi kullanımından sorumlu değildir.

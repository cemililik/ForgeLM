"""Top-level argparse parser + every subcommand registrar.

The registrars are short (15-120 lines each), they share
:func:`_add_common_subparser_flags`, and :func:`parse_args` instantiates
the parser once and adds them all. Fragmenting registrars into 6 separate
files would force this module to import each one and would not improve
cohesion.
"""

from __future__ import annotations

import argparse

from ._argparse_types import _add_common_subparser_flags, _non_negative_float, _non_negative_int, _positive_int
from ._logging import _get_version

# Shared `--output-dir` help text across approve / reject / approvals
# subparsers.  Sonar S1192 flagged the literal as duplicated 3x; the
# constant keeps the operator copy in one place so a future rename of
# `final_model.staging/` lands in one diff hunk.
_OUTPUT_DIR_HELP = "Training output directory containing audit_log.jsonl and final_model.staging/."


def _add_chat_subcommand(subparsers) -> None:
    p = subparsers.add_parser(
        "chat",
        help="Interactive chat REPL with a fine-tuned model.",
        description=(
            "Load a fine-tuned model and start an interactive terminal session.  "
            "Supports streaming output, slash commands (/reset, /save, /temperature, "
            "/system, /exit), and optional per-response safety annotations."
        ),
    )
    p.add_argument("model_path", help="Path to a saved HuggingFace model directory or HF Hub ID.")
    p.add_argument("--adapter", type=str, default=None, help="PEFT adapter directory to merge before chat.")
    p.add_argument("--system", type=str, default=None, metavar="PROMPT", help="Initial system prompt.")
    p.add_argument("--temperature", type=float, default=0.7, help="Sampling temperature (default: 0.7).")
    p.add_argument("--max-new-tokens", type=int, default=512, help="Max tokens per response (default: 512).")
    p.add_argument("--no-stream", action="store_true", help="Disable streaming output.")
    p.add_argument("--load-in-4bit", action="store_true", help="Load model in 4-bit NF4 quantisation.")
    p.add_argument("--load-in-8bit", action="store_true", help="Load model in 8-bit quantisation.")
    p.add_argument("--trust-remote-code", action="store_true", help="Allow execution of model-bundled code.")
    p.add_argument(
        "--backend",
        type=str,
        default="transformers",
        choices=["transformers", "unsloth"],
        help="Model backend (default: transformers).",
    )
    # chat is interactive; --output-format doesn't apply.
    _add_common_subparser_flags(p, include_output_format=False)


def _add_export_subcommand(subparsers) -> None:
    p = subparsers.add_parser(
        "export",
        help="Export a fine-tuned model to GGUF format.",
        description=(
            "Convert a HuggingFace model to GGUF for use with Ollama, llama.cpp, "
            "and compatible runtimes.  Requires: pip install 'forgelm[export]'"
        ),
    )
    p.add_argument("model_path", help="Path to a saved HuggingFace model directory.")
    p.add_argument("--output", type=str, required=True, metavar="FILE", help="Output .gguf file path.")
    p.add_argument(
        "--format",
        type=str,
        default="gguf",
        choices=["gguf"],
        help="Export format (default: gguf).",
    )
    p.add_argument(
        "--quant",
        type=str,
        default="q4_k_m",
        choices=["q2_k", "q3_k_m", "q4_k_m", "q5_k_m", "q8_0", "f16"],
        help="Quantisation type (default: q4_k_m).",
    )
    p.add_argument("--adapter", type=str, default=None, help="PEFT adapter directory to merge before export.")
    p.add_argument(
        "--no-integrity-update",
        action="store_true",
        help="Skip updating model_integrity.json with the exported artifact.",
    )
    _add_common_subparser_flags(p, include_output_format=True)


def _add_deploy_subcommand(subparsers) -> None:
    p = subparsers.add_parser(
        "deploy",
        help="Generate a deployment configuration for a serving runtime.",
        description=(
            "Produce a ready-to-use config file for Ollama, vLLM, TGI, or "
            "HuggingFace Inference Endpoints.  Does not start a server."
        ),
    )
    p.add_argument("model_path", help="Path to a saved HuggingFace model directory or HF Hub ID.")
    p.add_argument(
        "--target",
        type=str,
        required=True,
        choices=["ollama", "vllm", "tgi", "hf-endpoints"],
        help="Target serving runtime.",
    )
    p.add_argument("--output", type=str, default=None, metavar="FILE", help="Output file path (default: auto).")
    p.add_argument("--system", type=str, default=None, metavar="PROMPT", help="System prompt (Ollama only).")
    p.add_argument("--max-length", type=int, default=4096, help="Context window length (default: 4096).")
    p.add_argument(
        "--gpu-memory-utilization",
        type=float,
        default=0.90,
        help="vLLM GPU memory utilisation fraction (default: 0.90).",
    )
    p.add_argument("--port", type=int, default=8080, help="Host port for TGI container (default: 8080).")
    p.add_argument("--trust-remote-code", action="store_true", help="Set trust_remote_code in vLLM config.")
    p.add_argument(
        "--vendor",
        type=str,
        default="aws",
        help="Cloud vendor for HF Endpoints config (default: aws).",
    )
    _add_common_subparser_flags(p, include_output_format=True)


def _add_quickstart_subcommand(subparsers) -> None:
    p = subparsers.add_parser(
        "quickstart",
        help="Generate a config from a curated template (and optionally start training).",
        description=(
            "Pick a template (e.g. customer-support, code-assistant), get a working YAML and "
            "(optionally) seed dataset out the other end. The generated config uses the same "
            "schema as a hand-written one — quickstart is just opinionated defaults plus a "
            "license-clean seed dataset."
        ),
    )
    p.add_argument(
        "template",
        nargs="?",
        default=None,
        help="Template name. Run with --list to see what's available.",
    )
    p.add_argument("--list", action="store_true", help="List available templates and exit.")
    p.add_argument(
        "--model",
        type=str,
        default=None,
        metavar="MODEL_ID",
        help="Override the template's primary model (HF Hub ID or local path).",
    )
    p.add_argument(
        "--dataset",
        type=str,
        default=None,
        metavar="PATH",
        help="Override the template's bundled dataset (HF Hub ID or local JSONL path).",
    )
    p.add_argument(
        "--output",
        type=str,
        default=None,
        metavar="FILE",
        help="Where to write the generated YAML (default: ./configs/<template>-<timestamp>.yaml).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate the config and print next steps; do not invoke training.",
    )
    p.add_argument(
        "--no-chat",
        action="store_true",
        help="When training succeeds, do NOT auto-launch `forgelm chat` afterwards.",
    )
    _add_common_subparser_flags(p, include_output_format=True)


def _add_ingest_subcommand(subparsers) -> None:
    p = subparsers.add_parser(
        "ingest",
        help="Convert raw documents (PDF / DOCX / EPUB / TXT / Markdown) into SFT-ready JSONL.",
        description=(
            "Walk a file or directory tree, extract text per format, chunk with the "
            'selected strategy, and emit a {"text": ...} JSONL the trainer accepts. '
            "OCR is out of scope — pre-process scanned PDFs externally. "
            "Optional dependencies: pip install 'forgelm[ingestion]'."
        ),
    )
    p.add_argument("input_path", help="File or directory to ingest.")
    p.add_argument(
        "--output",
        type=str,
        required=True,
        metavar="FILE",
        help="Destination JSONL file (parent dirs are created).",
    )
    p.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Soft per-chunk character cap (library default: 2048). Default is None — "
            "the library resolves it via forgelm.ingestion.DEFAULT_CHUNK_SIZE. Passing an "
            "explicit value here while also using --chunk-tokens triggers an info log so "
            "stale invocations are visible."
        ),
    )
    p.add_argument(
        "--overlap",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Sliding-strategy overlap window (default: 200 when --strategy sliding; "
            "must be 0 / unset for paragraph or markdown — they're non-overlapping by design)."
        ),
    )
    p.add_argument(
        "--strategy",
        type=str,
        default="paragraph",
        choices=["sliding", "paragraph", "markdown"],
        help=(
            "Chunking strategy (default: paragraph). Phase 12 added 'markdown' — "
            "heading-aware splitter that preserves '# H1' / '## H2' boundaries and "
            "keeps code-fenced blocks atomic. 'semantic' is reserved for a follow-up "
            "phase — it raises NotImplementedError today and is hidden from this CLI "
            "surface to avoid runtime crashes."
        ),
    )
    p.add_argument(
        "--recursive",
        action="store_true",
        help=(
            "When input_path is a directory, walk subdirectories too. "
            "Default is shallow (top-level only) — pass --recursive to include nested files."
        ),
    )
    p.add_argument(
        "--pii-mask",
        action="store_true",
        help="Replace detected PII spans with [REDACTED] before writing.",
    )
    p.add_argument(
        "--secrets-mask",
        action="store_true",
        help=(
            "Phase 12: replace detected credential/secret spans (AWS / GitHub / "
            "Slack / OpenAI / Google / JWT / OpenSSH / PGP / Azure storage) with "
            "[REDACTED-SECRET] before chunks land in the JSONL. Runs before "
            "--pii-mask when both are set so secrets are scrubbed under the "
            "stronger label first."
        ),
    )
    p.add_argument(
        "--all-mask",
        action="store_true",
        help=(
            "Phase 12.5 shorthand: equivalent to --secrets-mask --pii-mask. "
            "Convenience for the common 'scrub everything detectable before "
            "training on shared corpora' workflow. Composes additively with "
            "explicit --pii-mask / --secrets-mask flags (set-union, no error)."
        ),
    )
    p.add_argument(
        "--chunk-tokens",
        type=_non_negative_int,
        default=None,
        metavar="N",
        help=(
            "Phase 11.5 token-aware mode: size each chunk to N tokens (requires --tokenizer). "
            "When set, --chunk-size is ignored. Use this when your downstream model has a hard "
            "max_length budget — char-based chunking commonly trips it on dense corpora. "
            "Must be ≥ 0; 0 is still rejected at ingest_path's own positive-int check, "
            "but negatives now exit at parse-time with a CLI argument error."
        ),
    )
    p.add_argument(
        "--overlap-tokens",
        type=_non_negative_int,
        default=0,
        metavar="N",
        help=(
            "Sliding-window overlap measured in tokens (default: 0). Same half-window cap as "
            "--overlap. Must be ≥ 0; negatives exit at parse-time. "
            "Ignored when --chunk-tokens is not set, and the paragraph strategy logs an "
            "info note when this is non-zero (paragraph chunks don't overlap by design)."
        ),
    )
    p.add_argument(
        "--tokenizer",
        type=str,
        default=None,
        metavar="MODEL_NAME",
        help="HuggingFace model name passed to AutoTokenizer.from_pretrained when --chunk-tokens is set.",
    )
    _add_common_subparser_flags(p, include_output_format=True)


def _add_doctor_subcommand(subparsers) -> None:
    """Phase 34: environment check (`forgelm doctor`).

    The first command an operator should run after installation.  Probes
    Python version, torch / CUDA, GPU inventory, optional extras, HF Hub
    reachability (or local cache when ``--offline``), workspace disk
    space, and the FORGELM_OPERATOR audit-identity hint.

    Exit codes follow the public contract: 0 = all pass, 1 = at least
    one check failed (config-error class), 2 = probe crashed.
    """
    p = subparsers.add_parser(
        "doctor",
        help="Run environment + dependency diagnostics (the first command after install).",
        description=(
            "Probe Python, torch + CUDA, GPU inventory, optional ForgeLM extras, "
            "HuggingFace Hub reachability, workspace disk space, and the "
            "FORGELM_OPERATOR audit-identity hint.  Emits a tabular text report or "
            "a structured JSON envelope (`--output-format json`).  Pass `--offline` "
            "to skip the HF Hub network probe and instead inspect the local cache."
        ),
    )
    p.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Skip the HuggingFace Hub network probe.  Inspects the local HF cache "
            "(precedence: HF_HUB_CACHE > HF_HOME/hub > ~/.cache/huggingface/hub) "
            "instead — useful for air-gapped deployments where the network probe "
            "would always fail.  Implicitly true when HF_HUB_OFFLINE=1 or "
            "TRANSFORMERS_OFFLINE=1 is set in the environment."
        ),
    )
    _add_common_subparser_flags(p, include_output_format=True)


def _add_audit_subcommand(subparsers) -> None:
    p = subparsers.add_parser(
        "audit",
        help="Run a Phase 11/11.5/12 dataset audit on a JSONL file or split-keyed directory.",
        description=(
            "Phase 11.5: first-class audit subcommand (the legacy `--data-audit FLAG` is preserved "
            "as a deprecation alias). Computes per-split length distribution, top-3 language detection, "
            "near-duplicate detection (LSH-banded), cross-split overlap, and PII flags with severity "
            "tiers — feeding the EU AI Act Article 10 governance artifact when run inside a training "
            "output directory. Phase 12 added: --dedup-method minhash for MinHash LSH, --quality-filter "
            "for Gopher/C4-style heuristics, and an always-on secrets scan that surfaces "
            "credential/key leakage in the audit report."
        ),
    )
    p.add_argument(
        "input_path",
        help="JSONL file (single split) or directory containing train.jsonl / validation.jsonl / test.jsonl.",
    )
    p.add_argument(
        "--output",
        type=str,
        # default=SUPPRESS keeps the attribute off ``args`` when the operator
        # doesn't pass --output, so the top-level ``--output`` (default=None)
        # wins and ``_run_data_audit`` applies its own "./audit" fallback.
        # Without SUPPRESS the subparser default would silently overwrite a
        # top-level value when both forms are valid.
        default=argparse.SUPPRESS,
        metavar="DIR",
        help="Where to write data_audit_report.json (default: ./audit/, created if missing).",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help=(
            "Show every split in the text summary, including those with zero findings. Default is "
            "to fold zero-finding splits into a single 'N clean split(s)' line so multi-split audits "
            "stay short. Has no effect on the on-disk JSON report."
        ),
    )
    p.add_argument(
        "--near-dup-threshold",
        type=_non_negative_int,
        default=None,
        metavar="N",
        help=(
            "Hamming-distance cutoff for the simhash near-duplicate detector. Default 3 (≈95%% "
            "similarity). Higher values widen the recall window at the cost of more false positives. "
            "Must be ≥ 0; negative values exit with a CLI argument error. "
            "Ignored when --dedup-method=minhash."
        ),
    )
    p.add_argument(
        "--dedup-method",
        type=str,
        default="simhash",
        choices=["simhash", "minhash"],
        help=(
            "Phase 12: near-duplicate detection method. Default 'simhash' (Phase 11.5 LSH-banded "
            "path; exact recall at the default threshold). 'minhash' opts into LSH-banded MinHash "
            "via the optional 'forgelm[ingestion-scale]' extra (datasketch) — industry standard "
            "for >50K-row corpora. Method choice surfaces under near_duplicate_summary.method."
        ),
    )
    p.add_argument(
        "--jaccard-threshold",
        type=_non_negative_float,
        default=None,
        metavar="X",
        help=(
            "Phase 12: Jaccard-similarity threshold for --dedup-method=minhash (default 0.85). "
            "Must lie in [0.0, 1.0]; ignored when --dedup-method=simhash."
        ),
    )
    p.add_argument(
        "--quality-filter",
        action="store_true",
        help=(
            "Phase 12 opt-in: run heuristic quality checks (mean word length, alphabetic-character "
            "ratio, end-of-line punctuation ratio, repeated-line ratio, short-paragraph ratio). "
            "Findings appear under quality_summary in the audit JSON. ML-based classifiers are "
            "deferred to Phase 13+."
        ),
    )
    p.add_argument(
        "--croissant",
        action="store_true",
        help=(
            "Phase 12.5: emit a Google Croissant 1.0 dataset card (sc:Dataset / cr:RecordSet) "
            "under the report's 'croissant' key so the same data_audit_report.json doubles as "
            "both the EU AI Act Article 10 governance artifact and a Croissant-consumer dataset "
            "card. Existing audit JSON keys are unchanged; the block is empty when this flag is off."
        ),
    )
    p.add_argument(
        "--pii-ml",
        action="store_true",
        help=(
            "Phase 12.5 opt-in: layer Presidio's ML-NER PII detection (person / organization / "
            "location categories) on top of the regex detector. Requires the optional "
            "'forgelm[ingestion-pii-ml]' extra AND a spaCy NER model "
            "(`python -m spacy download en_core_web_lg`); raises an install-hint ImportError "
            "when either is missing. Findings merge into pii_summary / pii_severity under "
            "disjoint category names."
        ),
    )
    p.add_argument(
        "--pii-ml-language",
        type=str,
        default="en",
        metavar="LANG",
        help=(
            "Phase 12.5: language code passed to Presidio's NLP engine when --pii-ml is on "
            "(default: 'en'). Presidio raises a typed exception if no engine is registered for "
            "the requested language — surface it to the operator instead of silently "
            "running an English NER on a non-English corpus. Set to e.g. 'tr' on a Turkish "
            "corpus AND make sure the matching spaCy model is installed."
        ),
    )
    p.add_argument(
        "--workers",
        type=_positive_int,
        default=1,
        metavar="N",
        help=(
            "Phase 17: number of worker processes for the split-level pipeline "
            "(default: 1 — sequential, byte-identical to the pre-Phase-17 path). "
            "Set to 2-4 on multi-split corpora (train / validation / test) for a "
            "near-linear speed-up.  Speed-up scales with the number of splits, "
            "not row count — single-split corpora ignore values > 1.  The merge "
            "step is single-threaded so the audit JSON is byte-identical across "
            "worker counts (determinism contract pinned by the test suite)."
        ),
    )
    _add_common_subparser_flags(p, include_output_format=True)


def _add_verify_audit_subcommand(subparsers) -> None:
    """Phase 6 (closure plan): ``forgelm verify-audit`` for chain integrity.

    Validates the SHA-256 hash chain (and, when a secret is supplied,
    the per-line HMAC tags) of an ``audit_log.jsonl`` file written by
    :class:`forgelm.compliance.AuditLogger`. Exit codes:

    - ``0`` — chain (and HMAC, if checked) intact
    - ``1`` — chain broken or HMAC mismatch
    - ``2`` — file missing / unreadable, or option error (e.g.
      ``--require-hmac`` without a configured secret env var)
    """
    p = subparsers.add_parser(
        "verify-audit",
        help="Verify integrity of an audit_log.jsonl chain.",
        description=(
            "Validates the SHA-256 hash chain of a ForgeLM audit_log.jsonl "
            "(EU AI Act Article 12 record-keeping). When the operator's "
            "FORGELM_AUDIT_SECRET is set in the environment, HMAC tags on "
            "each line are also verified. Designed for CI/CD pipelines: "
            "exit code 0 means the chain is intact, 1 means tampering or "
            "corruption was detected."
        ),
    )
    p.add_argument(
        "log_path",
        help="Path to audit_log.jsonl (the genesis manifest sidecar is auto-detected if present).",
    )
    p.add_argument(
        "--hmac-secret-env",
        type=str,
        default="FORGELM_AUDIT_SECRET",
        metavar="VAR",
        help=(
            "Name of the environment variable carrying the HMAC secret used at "
            "log-write time (default: FORGELM_AUDIT_SECRET). When the variable "
            "is set, per-line HMAC tags are validated; when unset, only the "
            "SHA-256 chain is checked."
        ),
    )
    p.add_argument(
        "--require-hmac",
        action="store_true",
        help=(
            "Strict mode: exit 2 if the configured env var is unset, and exit 1 "
            "if any line lacks an _hmac field. Use this in regulated CI pipelines "
            "where every entry must be HMAC-authenticated."
        ),
    )
    _add_common_subparser_flags(p, include_output_format=False)


def _add_approve_subcommand(subparsers) -> None:
    """Article 14: promote a staged model to ``final_model/`` after human review."""
    p = subparsers.add_parser(
        "approve",
        help="Promote a human-approval-staged model to the canonical final_model/ directory.",
        description=(
            "After a training run that exited with code 4 (awaiting human approval), "
            "run `forgelm approve <run_id> --output-dir <dir>` to promote the staged "
            "model. Verifies the staging directory exists and the audit log carries a "
            "matching `human_approval.required` event before performing an atomic "
            "rename of `final_model.staging/` → `final_model/`. Emits a "
            "`human_approval.granted` audit event and a `notify_success` webhook."
        ),
    )
    p.add_argument(
        "run_id",
        help="Run ID emitted with the human_approval.required event (e.g. fg-abc123def456).",
    )
    p.add_argument(
        "--output-dir",
        type=str,
        required=True,
        metavar="DIR",
        help=_OUTPUT_DIR_HELP,
    )
    p.add_argument(
        "--comment",
        type=str,
        default=None,
        metavar="TEXT",
        help="Optional reviewer comment recorded in the human_approval.granted audit event.",
    )
    _add_common_subparser_flags(p, include_output_format=True)


def _add_approvals_subcommand(subparsers) -> None:
    """Article 14 follow-up: list / inspect pending approval requests.

    Exactly one of ``--pending`` and ``--show RUN_ID`` must be set; argparse
    enforces this with a mutually-exclusive group so the dispatcher only
    sees a validated args namespace.  ``--output-dir`` is required in both
    modes — there is no useful default; an operator running on a freshly-
    cloned workstation must point at the training output explicitly.
    """
    p = subparsers.add_parser(
        "approvals",
        help="List pending Article 14 approval requests or inspect a single run.",
        description=(
            "Discovery counterpart to `forgelm approve` / `forgelm reject`.  "
            "`--pending` lists every run whose audit log carries a "
            "`human_approval.required` event without a matching terminal "
            "decision.  `--show RUN_ID` prints the full approval-gate audit "
            "chain plus the on-disk staging directory layout for one run."
        ),
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--pending",
        action="store_true",
        help="List every run awaiting an approval decision.",
    )
    mode.add_argument(
        "--show",
        type=str,
        default=None,
        metavar="RUN_ID",
        help="Show the full audit chain + staging contents for a single run.",
    )
    p.add_argument(
        "--output-dir",
        type=str,
        required=True,
        metavar="DIR",
        help=_OUTPUT_DIR_HELP,
    )
    _add_common_subparser_flags(p, include_output_format=True)


def _add_reject_subcommand(subparsers) -> None:
    """Article 14: discard a staged model (preserves staging dir for forensics)."""
    p = subparsers.add_parser(
        "reject",
        help="Reject a human-approval-staged model (preserves staging dir for forensics).",
        description=(
            "After a training run that exited with code 4 (awaiting human approval), "
            "run `forgelm reject <run_id> --output-dir <dir>` to record a rejection. "
            "The `final_model.staging/` directory is left untouched so the rejected "
            "artefacts remain available for forensic review. Emits a "
            "`human_approval.rejected` audit event and a `notify_failure` webhook."
        ),
    )
    p.add_argument(
        "run_id",
        help="Run ID emitted with the human_approval.required event (e.g. fg-abc123def456).",
    )
    p.add_argument(
        "--output-dir",
        type=str,
        required=True,
        metavar="DIR",
        help=_OUTPUT_DIR_HELP,
    )
    p.add_argument(
        "--comment",
        type=str,
        default=None,
        metavar="TEXT",
        help="Reviewer comment recorded in the human_approval.rejected audit event (recommended).",
    )
    _add_common_subparser_flags(p, include_output_format=True)


def parse_args():
    parser = argparse.ArgumentParser(
        description="ForgeLM: Language Model Fine-Tuning Toolkit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Subcommands:\n"
            "  forgelm doctor                  Environment check (Python/torch/CUDA/GPU/extras/HF/disk)\n"
            "  forgelm quickstart [TEMPLATE]   Generate a config from a curated template\n"
            "  forgelm ingest PATH             Convert raw docs (PDF/DOCX/EPUB/TXT/Markdown) → JSONL\n"
            "  forgelm audit PATH              Run dataset audit (length/lang/PII/leakage)\n"
            "  forgelm verify-audit LOG_PATH   Verify SHA-256 + HMAC integrity of an audit log\n"
            "  forgelm chat MODEL_PATH         Interactive chat REPL\n"
            "  forgelm export MODEL_PATH       Export model to GGUF\n"
            "  forgelm deploy MODEL_PATH       Generate serving config\n"
            "  forgelm approve RUN_ID          Promote a staged model after human review (Art. 14)\n"
            "  forgelm reject  RUN_ID          Reject a staged model (preserves staging dir for forensics)\n"
            "  forgelm approvals --pending     List runs awaiting human approval (or --show RUN_ID)\n"
            "\nRun 'forgelm <subcommand> --help' for subcommand details."
        ),
    )

    # --- Subcommand router (dest=command; None when not given → training mode) ---
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    _add_chat_subcommand(subparsers)
    _add_export_subcommand(subparsers)
    _add_deploy_subcommand(subparsers)
    _add_quickstart_subcommand(subparsers)
    _add_ingest_subcommand(subparsers)
    _add_audit_subcommand(subparsers)
    _add_doctor_subcommand(subparsers)
    _add_verify_audit_subcommand(subparsers)
    _add_approve_subcommand(subparsers)
    _add_reject_subcommand(subparsers)
    _add_approvals_subcommand(subparsers)

    # --- Top-level flags (training / config-driven mode) ---
    parser.add_argument("--config", type=str, help="Path to the YAML configuration file.")
    parser.add_argument(
        "--wizard", action="store_true", help="Launch interactive configuration wizard to generate a config.yaml."
    )
    parser.add_argument("--version", action="version", version=f"ForgeLM {_get_version()}")
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate configuration and check model/dataset access without training."
    )
    parser.add_argument(
        "--fit-check",
        action="store_true",
        help=(
            "Estimate peak training VRAM from the config without loading the model.  "
            "Requires --config.  Prints a FITS / TIGHT / OOM verdict with a breakdown."
        ),
    )
    parser.add_argument(
        "--resume",
        type=str,
        nargs="?",
        const="auto",
        default=None,
        help="Resume training from a checkpoint. Use --resume for auto-detection or --resume /path/to/checkpoint.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Air-gapped mode: disable all HF Hub network calls. Models and datasets must be available locally.",
    )
    parser.add_argument(
        "--benchmark-only",
        type=str,
        default=None,
        metavar="MODEL_PATH",
        help="Run benchmark evaluation on an existing model without training. Requires evaluation.benchmark config.",
    )
    parser.add_argument(
        "--merge", action="store_true", help="Run model merging from the merge section of your config. No training."
    )
    parser.add_argument(
        "--output-format",
        type=str,
        default="text",
        choices=["text", "json"],
        help="Output format for results (default: text). JSON mode outputs machine-readable results to stdout.",
    )
    parser.add_argument(
        "--generate-data",
        action="store_true",
        help="Generate synthetic training data using teacher model. No training.",
    )
    parser.add_argument(
        "--compliance-export",
        type=str,
        default=None,
        metavar="OUTPUT_DIR",
        help=(
            "Export EU AI Act compliance artifacts (audit trail, data provenance, Annex IV docs) "
            "to OUTPUT_DIR from the given config. Run after training so the manifest is complete; "
            "standalone use produces artifacts with empty metrics."
        ),
    )
    parser.add_argument(
        "--data-audit",
        type=str,
        default=None,
        metavar="PATH",
        help=(
            "DEPRECATED — alias for `forgelm audit PATH` (kept so existing pipelines keep "
            "working). Scheduled for removal in v0.7.0. Behaviour is identical; new scripts "
            "should use the subcommand. Writes `data_audit_report.json` under --output "
            "(default ./audit/). No training."
        ),
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        metavar="DIR",
        help="Output directory for --data-audit / --compliance-export (default: ./audit or ./compliance).",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress INFO logs. Only show warnings and errors.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging verbosity (default: INFO).",
    )
    return parser.parse_args()

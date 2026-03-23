import logging
import os
from typing import Any, Dict

from datasets import DatasetDict, concatenate_datasets, load_dataset
from transformers import PreTrainedTokenizer

logger = logging.getLogger("forgelm.data")


def _detect_dataset_format(columns: list) -> dict:
    """Detect the most likely dataset format from column names."""
    if "chosen" in columns and "rejected" in columns:
        return {"description": "preference format (chosen/rejected)", "suggested_trainer": "dpo"}
    if "completion" in columns and "label" in columns:
        return {"description": "binary feedback format (completion/label)", "suggested_trainer": "kto"}
    if "messages" in columns:
        return {"description": "conversational format (messages list)", "suggested_trainer": "sft"}
    if "prompt" in columns and "chosen" not in columns:
        return {"description": "prompt-only format", "suggested_trainer": "grpo"}
    if any(c in columns for c in ("User", "instruction")) and any(
        c in columns for c in ("Assistant", "output", "response")
    ):
        return {"description": "instruction-tuning format (User/Assistant)", "suggested_trainer": "sft"}
    return {"description": f"unknown format ({', '.join(columns[:5])})", "suggested_trainer": "sft"}


def clean_string(text: str, do_clean: bool) -> str:
    """Removes extra whitespace if configured."""
    if do_clean and isinstance(text, str):
        return " ".join(text.split())
    return str(text) if text else ""


def _load_single_dataset(path: str):
    """Load a single dataset from a local file or HF Hub."""
    if os.path.isfile(path):
        ext = path.split(".")[-1]
        if ext == "jsonl":
            ext = "json"
        return load_dataset(ext, data_files=path)
    return load_dataset(path)


def prepare_dataset(config: Any, tokenizer: PreTrainedTokenizer) -> Dict[str, Any]:
    """Loads and tokenizes the dataset based on ForgeConfig."""

    logger.info("Loading dataset from %s...", config.data.dataset_name_or_path)
    primary_dataset = _load_single_dataset(config.data.dataset_name_or_path)
    dataset = primary_dataset

    # Multi-dataset support: load and merge extra datasets
    extra_datasets = getattr(config.data, "extra_datasets", None)
    if extra_datasets:
        all_train = [dataset["train"]]
        mix_ratio = getattr(config.data, "mix_ratio", None)

        for i, extra_path in enumerate(extra_datasets):
            logger.info("Loading extra dataset [%d]: %s", i + 1, extra_path)
            extra_ds = _load_single_dataset(extra_path)
            all_train.append(extra_ds["train"])

        # Apply mix ratios via sampling
        if mix_ratio and len(mix_ratio) == len(all_train):
            total_weight = sum(mix_ratio)
            if total_weight == 0:
                logger.warning("mix_ratio weights sum to 0. Using uniform mixing.")
            else:
                normalized = [w / total_weight for w in mix_ratio]
                # Total target = sum of all dataset sizes weighted proportionally
                max_dataset_size = max(len(ds) for ds in all_train)
                sampled = []
                for ds, ratio in zip(all_train, normalized):
                    n_samples = min(int(max_dataset_size * ratio), len(ds))
                    sampled.append(ds.select(range(n_samples)))
                all_train = sampled
                logger.info("Applied mix ratios: %s", mix_ratio)
        else:
            if mix_ratio:
                logger.warning(
                    "mix_ratio length (%d) doesn't match dataset count (%d). Using uniform mixing.",
                    len(mix_ratio),
                    len(all_train),
                )

        merged_train = concatenate_datasets(all_train)
        logger.info("Merged %d datasets into %d training samples.", len(all_train), len(merged_train))
        dataset = DatasetDict({"train": merged_train})
        # Validation from primary dataset (already loaded, no re-fetch)
        if "validation" in primary_dataset:
            dataset["validation"] = primary_dataset["validation"]

    # Ensure splits exist (train / validation)
    if "validation" not in dataset and "test" in dataset:
        dataset["validation"] = dataset["test"]
    elif "validation" not in dataset:
        logger.info("No validation split found. Slicing 10%% off training data for validation.")
        split_dataset = dataset["train"].train_test_split(test_size=0.1, seed=42)
        dataset = DatasetDict({"train": split_dataset["train"], "validation": split_dataset["test"]})

    def process_batch(examples):
        # Handle modern conversational format (messages column)
        if "messages" in examples:
            texts = []
            for msg_list in examples["messages"]:
                try:
                    formatted_text = tokenizer.apply_chat_template(
                        msg_list, tokenize=False, add_generation_prompt=False
                    )
                except Exception as e:
                    logger.warning("Chat template failed for messages format, using fallback: %s", e)
                    formatted_text = ""
                    for m in msg_list:
                        formatted_text += f"[{m['role'].upper()}]\n{m['content']}\n"
                    if config.data.add_eos:
                        formatted_text += tokenizer.eos_token
                texts.append(formatted_text)
            return {"text": texts}

        has_system = "System" in examples
        sys_texts = examples["System"] if has_system else [""] * len(examples.get("User", examples.get("text", [])))
        user_texts = examples.get("User", examples.get("instruction", []))
        asst_texts = examples.get("Assistant", examples.get("output", examples.get("response", [])))

        if not user_texts or not asst_texts:
            raise KeyError("Dataset must contain 'User'/'instruction' and 'Assistant'/'output' columns.")

        texts = []
        for sys_text, user_text, asst_text in zip(sys_texts, user_texts, asst_texts):
            messages = []
            if sys_text:
                messages.append({"role": "system", "content": clean_string(sys_text, config.data.clean_text)})
            messages.append({"role": "user", "content": clean_string(user_text, config.data.clean_text)})
            messages.append({"role": "assistant", "content": clean_string(asst_text, config.data.clean_text)})

            # Use tokenizer's chat template
            try:
                formatted_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
            except Exception as e:
                logger.warning("Chat template failed for model, using fallback formatting: %s", e)
                sys_part = f"[SYSTEM]\n{messages[0]['content']}\n" if sys_text else ""
                user_idx = 1 if sys_text else 0
                formatted_text = (
                    sys_part + f"[USER]\n{messages[user_idx]['content']}\n[ASSISTANT]\n{messages[-1]['content']}"
                )
                if config.data.add_eos:
                    formatted_text += tokenizer.eos_token

            texts.append(formatted_text)

        return {"text": texts}

    # Detect dataset format and trainer type
    trainer_type = getattr(config.training, "trainer_type", "sft")
    sample_columns = dataset["train"].column_names if "train" in dataset else []
    has_chosen_rejected = "chosen" in sample_columns and "rejected" in sample_columns
    has_kto_format = "completion" in sample_columns and "label" in sample_columns
    has_prompt_only = "prompt" in sample_columns and not has_chosen_rejected

    # Multimodal VLM datasets: pass through with image column handling
    mm_cfg = getattr(config.model, "multimodal", None)
    if mm_cfg and mm_cfg.enabled:
        image_col = mm_cfg.image_column
        text_col = mm_cfg.text_column
        if image_col not in sample_columns:
            raise KeyError(
                f"Multimodal mode enabled but image column '{image_col}' not found. "
                f"Found columns: {', '.join(sample_columns)}. "
                f"Set model.multimodal.image_column to match your dataset."
            )
        logger.info(
            "Multimodal VLM dataset detected (image='%s', text='%s'). Passing through for VLM processor handling.",
            image_col,
            text_col,
        )
        processed = {}
        for split in dataset:
            current_dataset = dataset[split]
            if config.data.shuffle:
                current_dataset = current_dataset.shuffle(seed=42)
            processed[split] = current_dataset
        return processed

    # Detect what format the dataset actually is
    _detected_format = _detect_dataset_format(sample_columns)

    # Preference trainers: DPO, SimPO, ORPO require chosen/rejected
    preference_trainers = {"dpo", "simpo", "orpo"}
    if trainer_type in preference_trainers and not has_chosen_rejected:
        raise KeyError(
            f"{trainer_type.upper()} trainer requires 'chosen' and 'rejected' columns, "
            f"but found: {', '.join(sample_columns)}.\n\n"
            f"Your dataset looks like: {_detected_format['description']}\n"
            f'Suggested: Use trainer_type: "{_detected_format["suggested_trainer"]}" instead, '
            f"or convert your data to preference format (prompt + chosen + rejected)."
        )

    # KTO requires completion/label format
    if trainer_type == "kto" and not has_kto_format:
        raise KeyError(
            f"KTO trainer requires 'completion' and 'label' (boolean) columns, "
            f"but found: {', '.join(sample_columns)}.\n\n"
            f"Your dataset looks like: {_detected_format['description']}\n"
            f'Suggested: Use trainer_type: "{_detected_format["suggested_trainer"]}" instead, '
            f"or convert your data to KTO format (prompt + completion + label)."
        )

    # GRPO requires prompt column (generates responses during training)
    if trainer_type == "grpo" and not has_prompt_only and "prompt" not in sample_columns:
        raise KeyError(
            f"GRPO trainer requires a 'prompt' column, "
            f"but found: {', '.join(sample_columns)}.\n\n"
            f"Your dataset looks like: {_detected_format['description']}\n"
            f'Suggested: Use trainer_type: "{_detected_format["suggested_trainer"]}" instead, '
            f"or convert your data to prompt-only format."
        )

    # Preference / alignment datasets are passed through with minimal processing
    # TRL trainers expect specific column formats
    if trainer_type in preference_trainers and has_chosen_rejected:
        logger.info("Detected preference dataset (chosen/rejected) for %s training.", trainer_type.upper())
        processed = {}
        for split in dataset:
            current_dataset = dataset[split]
            if config.data.shuffle:
                current_dataset = current_dataset.shuffle(seed=42)
            processed[split] = current_dataset
        return processed

    if trainer_type == "kto":
        logger.info("Detected KTO dataset (completion/label) for KTO training.")
        processed = {}
        for split in dataset:
            current_dataset = dataset[split]
            if config.data.shuffle:
                current_dataset = current_dataset.shuffle(seed=42)
            processed[split] = current_dataset
        return processed

    if trainer_type == "grpo":
        logger.info("Detected prompt dataset for GRPO training.")
        processed = {}
        for split in dataset:
            current_dataset = dataset[split]
            if config.data.shuffle:
                current_dataset = current_dataset.shuffle(seed=42)
            processed[split] = current_dataset
        return processed

    logger.info("Formatting dataset with Chat Templates...")
    processed = {}
    for split in dataset:
        current_dataset = dataset[split]
        if config.data.shuffle:
            current_dataset = current_dataset.shuffle(seed=42)

        processed[split] = current_dataset.map(
            process_batch,
            batched=True,
            remove_columns=current_dataset.column_names,
            num_proc=4 if os.cpu_count() and os.cpu_count() > 4 else 1,
            desc=f"Formatting {split} split",
        )

    return processed

import os
import logging
from typing import Dict, Any
from datasets import load_dataset, DatasetDict, concatenate_datasets
from transformers import PreTrainedTokenizer

logger = logging.getLogger("forgelm.data")

def clean_string(text: str, do_clean: bool) -> str:
    """Removes extra whitespace if configured."""
    if do_clean and isinstance(text, str):
        return " ".join(text.split())
    return str(text) if text else ""

def _load_single_dataset(path: str):
    """Load a single dataset from a local file or HF Hub."""
    if os.path.isfile(path):
        ext = path.split('.')[-1]
        if ext == "jsonl": ext = "json"
        return load_dataset(ext, data_files=path)
    return load_dataset(path)


def prepare_dataset(config: Any, tokenizer: PreTrainedTokenizer) -> Dict[str, Any]:
    """Loads and tokenizes the dataset based on ForgeConfig."""

    logger.info("Loading dataset from %s...", config.data.dataset_name_or_path)
    dataset = _load_single_dataset(config.data.dataset_name_or_path)

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
            normalized = [w / total_weight for w in mix_ratio]
            # Target size = primary dataset size
            target_size = len(all_train[0])
            sampled = []
            for ds, ratio in zip(all_train, normalized):
                n_samples = min(int(target_size * ratio / normalized[0]), len(ds))
                sampled.append(ds.select(range(n_samples)))
            all_train = sampled
            logger.info("Applied mix ratios: %s", mix_ratio)
        else:
            if mix_ratio:
                logger.warning(
                    "mix_ratio length (%d) doesn't match dataset count (%d). Using uniform mixing.",
                    len(mix_ratio), len(all_train)
                )

        merged_train = concatenate_datasets(all_train)
        logger.info("Merged %d datasets into %d training samples.", len(all_train), len(merged_train))
        dataset = DatasetDict({"train": merged_train})
        # Validation from primary dataset only
        if "validation" in _load_single_dataset(config.data.dataset_name_or_path):
            dataset["validation"] = _load_single_dataset(config.data.dataset_name_or_path)["validation"]

    # Ensure splits exist (train / validation)
    if "validation" not in dataset and "test" in dataset:
         dataset["validation"] = dataset["test"]
    elif "validation" not in dataset:
        logger.info("No validation split found. Slicing 10%% off training data for validation.")
        split_dataset = dataset["train"].train_test_split(test_size=0.1, seed=42)
        dataset = DatasetDict({
            "train": split_dataset["train"],
            "validation": split_dataset["test"]
        })

    def process_batch(examples):
        # Handle modern conversational format (messages column)
        if "messages" in examples:
            texts = []
            for msg_list in examples["messages"]:
                try:
                    formatted_text = tokenizer.apply_chat_template(msg_list, tokenize=False, add_generation_prompt=False)
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
                formatted_text = sys_part + f"[USER]\n{messages[user_idx]['content']}\n[ASSISTANT]\n{messages[-1]['content']}"
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

    # Preference trainers: DPO, SimPO, ORPO require chosen/rejected
    preference_trainers = {"dpo", "simpo", "orpo"}
    if trainer_type in preference_trainers and not has_chosen_rejected:
        raise KeyError(
            f"{trainer_type.upper()} trainer requires a preference dataset with 'chosen' and "
            f"'rejected' columns. Found columns: {', '.join(sample_columns)}"
        )

    # KTO requires completion/label format
    if trainer_type == "kto" and not has_kto_format:
        raise KeyError(
            "KTO trainer requires a dataset with 'completion' and 'label' (boolean) columns. "
            f"Found columns: {', '.join(sample_columns)}"
        )

    # GRPO requires prompt column (generates responses during training)
    if trainer_type == "grpo" and not has_prompt_only and "prompt" not in sample_columns:
        raise KeyError(
            "GRPO trainer requires a dataset with a 'prompt' column. "
            f"Found columns: {', '.join(sample_columns)}"
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
            desc=f"Formatting {split} split"
        )

    return processed

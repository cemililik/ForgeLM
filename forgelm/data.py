import os
from typing import Dict, Any
from datasets import load_dataset, DatasetDict
from transformers import PreTrainedTokenizer

def clean_string(text: str, do_clean: bool) -> str:
    """Removes extra whitespace if configured."""
    if do_clean and isinstance(text, str):
        return " ".join(text.split())
    return str(text) if text else ""

def prepare_dataset(config: Any, tokenizer: PreTrainedTokenizer) -> Dict[str, Any]:
    """Loads and tokenizes the dataset based on ForgeConfig."""
    
    print(f"Loading dataset from {config.data.dataset_name_or_path}...")
    
    # Try loading as a local CSV/JSON if it's a file, otherwise assume HF Hub
    if os.path.isfile(config.data.dataset_name_or_path):
        ext = config.data.dataset_name_or_path.split('.')[-1]
        dataset = load_dataset(ext, data_files=config.data.dataset_name_or_path)
    else:
        dataset = load_dataset(config.data.dataset_name_or_path)
    
    # Ensure splits exist (train / validation)
    if "validation" not in dataset and "test" in dataset:
         dataset["validation"] = dataset["test"]
    elif "validation" not in dataset:
        print("No validation split found. Slicing 10% off training data for validation.")
        # Assumes there is a "train" split
        split_dataset = dataset["train"].train_test_split(test_size=0.1, seed=42)
        dataset = DatasetDict({
            "train": split_dataset["train"],
            "validation": split_dataset["test"]
        })

    def process_batch(examples):
        # We assume dataset has 'System', 'User', 'Assistant' columns
        # You may want to make these column names configurable in the future
        
        # Fallback if specific columns aren't found (using a default generic parsing if possible)
        has_system = "System" in examples
        sys_texts = examples["System"] if has_system else [""] * len(examples.get("User", examples.get("text", [])))
        user_texts = examples.get("User", examples.get("instruction", []))
        asst_texts = examples.get("Assistant", examples.get("output", examples.get("response", [])))
        
        if not user_texts or not asst_texts:
            raise KeyError("Dataset must contain 'User'/'instruction' and 'Assistant'/'output' columns.")

        prompts = []
        for sys_text, user_text, asst_text in zip(sys_texts, user_texts, asst_texts):
            system_part = f"[SYSTEM]\n{clean_string(sys_text, config.data.clean_text)}\n" if clean_string(sys_text, config.data.clean_text) else ""
            user_part = f"[USER]\n{clean_string(user_text, config.data.clean_text)}\n"
            asst_part = f"[ASSISTANT]\n{clean_string(asst_text, config.data.clean_text)}"
            
            prompts.append(system_part + user_part + asst_part)

        tokenizer_kwargs = {
            "truncation": True,
            "padding": "max_length",
            "max_length": config.model.max_length,
            "return_tensors": "pt"
        }
        
        if config.data.add_eos:
            tokenizer_kwargs["add_special_tokens"] = True
            
        tokenized = tokenizer(prompts, **tokenizer_kwargs)
        
        result = {
            "input_ids": tokenized["input_ids"],
            "attention_mask": tokenized["attention_mask"],
            "labels": tokenized["input_ids"].clone()
        }
        
        # Mask padding tokens in labels to avoid calculating loss on them
        result["labels"][tokenized["input_ids"] == tokenizer.pad_token_id] = -100
        
        return result

    print("Tokenizing dataset...")
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
            desc=f"Tokenizing {split} split"
        )
        
    return processed

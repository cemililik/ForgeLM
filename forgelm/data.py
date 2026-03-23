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
    
    if os.path.isfile(config.data.dataset_name_or_path):
        ext = config.data.dataset_name_or_path.split('.')[-1]
        if ext == "jsonl": ext = "json"
        dataset = load_dataset(ext, data_files=config.data.dataset_name_or_path)
    else:
        dataset = load_dataset(config.data.dataset_name_or_path)
    
    # Ensure splits exist (train / validation)
    if "validation" not in dataset and "test" in dataset:
         dataset["validation"] = dataset["test"]
    elif "validation" not in dataset:
        print("No validation split found. Slicing 10% off training data for validation.")
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
                except Exception:
                    # Fallback
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
            except Exception:
                # Fallback if model has no chat template
                sys_part = f"[SYSTEM]\n{messages[0]['content']}\n" if sys_text else ""
                formatted_text = sys_part + f"[USER]\n{messages[1 if not sys_text else 2]['content']}\n[ASSISTANT]\n{messages[-1]['content']}"
                if config.data.add_eos:
                    formatted_text += tokenizer.eos_token
            
            texts.append(formatted_text)
            
        return {"text": texts}

    print("Formatting dataset with Chat Templates...")
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

# Data Preparation Guide

ForgeLM uses the Hugging Face `datasets` library under the hood. While it can connect to thousands of datasets on the HF Hub, your dataset must adhere to specific structural patterns to be formatted perfectly for supervised fine-tuning.

## Supported Formats

ForgeLM's data processor expects an **Instruction/Response** structured dataset.

If loading via the Hugging Face Hub (e.g., `dataset_name_or_path: "HuggingFaceH4/ultrachat_200k"`), or via a local JSONL file, ForgeLM attempts to parse the rows looking for conversational columns.

### Implicit Schema Support
The processor will attempt to map the following columns respectively:

- **System Context (Optional)**: If your dataset has a `System` column, it will be injected. Otherwise, it is left blank.
- **User Prompt (Required)**: Looked for in the `User`, `instruction`, or `text` column.
- **Assistant Response (Required)**: Looked for in the `Assistant`, `output`, or `response` column.

## Example JSONL Structure (Local File)

If you are bringing custom company data, format it into a `.jsonl` file where each line is a JSON object. Set the `dataset_name_or_path` in your config to the absolute path of this file.

```json
{"System": "You are a helpful Python coding assistant.", "User": "How do I reverse a list?", "Assistant": "You can use `[::-1]` or the `.reverse()` method."}
{"System": "You are a helpful Python coding assistant.", "User": "What is a loop?", "Assistant": "A loop is used to iterate over a sequence."}
```

## The Final Prompt Format
Internally, ForgeLM builds a prompt using specific bounding tags before passing it to the tokenizer.

```text
[SYSTEM]
{system_text}
[USER]
{user_text}
[ASSISTANT]
{assistant_text}
```

Ensure your base model is compatible or adaptable to interpreting these bounding tokens for the best inference results post-training.

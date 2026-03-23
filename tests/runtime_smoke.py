import json
import os
from unittest.mock import patch

import yaml

from forgelm.cli import main


def test_full_runtime_smoke():
    """
    Uçtan uca ForgeLM döngüsünü CPU üzerinde, tiny bir model ile test eder.
    """
    tmp_dir = "tmp_smoke_test"
    os.makedirs(tmp_dir, exist_ok=True)

    config_path = os.path.join(tmp_dir, "smoke_config.yaml")
    dataset_path = os.path.join(tmp_dir, "smoke_data.jsonl")
    output_dir = os.path.join(tmp_dir, "output")

    # 1. Mock Dataset Oluştur (Conversational format)
    data = [
        {"messages": [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi there!"}]},
        {"messages": [{"role": "user", "content": "How are you?"}, {"role": "assistant", "content": "I am a tiny model."}]},
        {"messages": [{"role": "user", "content": "What is 2+2?"}, {"role": "assistant", "content": "It is 4."}]},
        {"messages": [{"role": "user", "content": "Tell me a joke."}, {"role": "assistant", "content": "I am the joke."}]},
        {"messages": [{"role": "user", "content": "Goodbye."}, {"role": "assistant", "content": "Bye!"}]},
    ]
    with open(dataset_path, "w") as f:
        for entry in data:
            f.write(json.dumps(entry) + "\n")

    # 2. Mock Config Oluştur
    # Model: HuggingFaceTB/SmolLM2-135M-Instruct (Guaranteed safetensors)
    config = {
        "model": {
            "name_or_path": "HuggingFaceTB/SmolLM2-135M-Instruct",
            "backend": "transformers",
            "max_length": 128,
            "load_in_4bit": False
        },
        "lora": {
            "r": 8,
            "alpha": 16,
            "dropout": 0.05,
            "target_modules": ["q_proj", "v_proj"],
            "bias": "none",
            "task_type": "CAUSAL_LM"
        },
        "data": {
            "dataset_name_or_path": dataset_path,
            "shuffle": True
        },
        "training": {
            "output_dir": output_dir,
            "num_train_epochs": 1,
            "max_steps": 1, # Sadece 1 adım
            "per_device_train_batch_size": 1,
            "gradient_accumulation_steps": 1,
            "learning_rate": 2e-4,
            "save_steps": 1,
            "eval_steps": 1,
            "fp16": False,
            "merge_adapters": False
        },
        "evaluation": {
            "auto_revert": False # Smoke test için revert'ü şimdilik kapalı tutalım
        }
    }

    with open(config_path, "w") as f:
        yaml.dump(config, f)

    # 3. CLI'yı Çalıştır
    print("\n--- Starting Runtime Smoke Test ---")
    test_args = ["forgelm", "--config", config_path]
    with patch.object(sys, 'argv', test_args):
        try:
            main()
        except SystemExit as e:
            if e.code != 0:
                raise RuntimeError(f"CLI exited with code {e.code}") from e

    # 4. Doğrulamalar
    final_model_dir = os.path.join(output_dir, "final_model")
    assert os.path.exists(final_model_dir), "Final model dizini oluşturulmadı!"
    assert os.path.exists(os.path.join(final_model_dir, "adapter_config.json")), "Adapter konfigürasyonu bulunamadı!"

    print("\n✅ Runtime Smoke Test Passed!")

    # Cleanup
    # shutil.rmtree(tmp_dir)

if __name__ == "__main__":
    import sys
    test_full_runtime_smoke()

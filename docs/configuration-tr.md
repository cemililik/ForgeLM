# Konfigürasyon Rehberi

ForgeLM tüm yapılandırma için YAML dosyalarını kullanır — bildirimsel, sürüm kontrollü ve CI/CD-uyumlu.

Tam açıklamalı örnek için `config_template.yaml` dosyasına bakın.

---

## `model`

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `name_or_path` | string | *zorunlu* | HuggingFace model ID veya yerel yol |
| `max_length` | int | `2048` | Maksimum bağlam uzunluğu |
| `load_in_4bit` | bool | `true` | QLoRA 4-bit NF4 kuantizasyon |
| `backend` | string | `"transformers"` | `"transformers"` veya `"unsloth"` (2-5x hızlı, Linux) |
| `trust_remote_code` | bool | `false` | Model depolarından özel kod çalıştırma. **Güvenlik riski** |
| `offline` | bool | `false` | İzole mod: HF Hub çağrısı yok |

#### `model.moe` (İsteğe bağlı — MoE modeller)

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `quantize_experts` | bool | `false` | İnaktif expert ağırlıklarını int8'e kuantize et |
| `experts_to_train` | string | `"all"` | `"all"` veya virgülle ayrılmış indeksler |

---

## `lora`

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `r` | int | `8` | LoRA rank |
| `alpha` | int | `16` | LoRA ölçekleme faktörü |
| `method` | string | `"lora"` | PEFT yöntemi: `"lora"`, `"dora"`, `"pissa"`, `"rslora"` |
| `use_dora` | bool | `false` | DoRA (Ağırlık-Ayrıştırılmış LoRA) |
| `use_rslora` | bool | `false` | Rank-stabilize LoRA (r>64 için önerilir) |
| `target_modules` | list | `["q_proj", "v_proj"]` | LoRA uygulanacak modüller |

---

## `training`

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `trainer_type` | string | `"sft"` | `"sft"`, `"dpo"`, `"simpo"`, `"kto"`, `"orpo"`, `"grpo"` |
| `num_train_epochs` | int | `3` | Eğitim epoch sayısı |
| `per_device_train_batch_size` | int | `4` | GPU başına batch boyutu |
| `learning_rate` | float | `2e-5` | Öğrenme oranı |
| `report_to` | string | `"tensorboard"` | `"tensorboard"`, `"wandb"`, `"mlflow"`, `"none"` |

#### Hizalama Parametreleri

| Alan | Tip | Varsayılan | Kullanan |
|------|-----|-----------|---------|
| `dpo_beta` | float | `0.1` | DPO sıcaklık |
| `simpo_gamma` | float | `0.5` | SimPO marj |
| `kto_beta` | float | `0.1` | KTO kayıp parametresi |
| `orpo_beta` | float | `0.1` | ORPO odds ratio ağırlığı |
| `grpo_num_generations` | int | `4` | GRPO: prompt başına yanıt |
| `grpo_reward_model` | string | `null` | GRPO: ödül modeli yolu |

---

## `data`

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `dataset_name_or_path` | string | *zorunlu* | HF veri seti ID veya yerel JSONL |
| `extra_datasets` | list | `null` | Karıştırılacak ek veri setleri |
| `mix_ratio` | list | `null` | Veri seti başına ağırlık |

#### `data.governance` (İsteğe bağlı — EU AI Act Madde 10)

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `collection_method` | string | `""` | Veri toplama yöntemi |
| `annotation_process` | string | `""` | Etiketleme süreci |
| `known_biases` | string | `""` | Bilinen önyargılar |
| `personal_data_included` | bool | `false` | Kişisel veri içeriyor |
| `dpia_completed` | bool | `false` | Veri Koruma Etki Değerlendirmesi |

---

## `evaluation` (İsteğe bağlı)

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `auto_revert` | bool | `false` | Değerlendirme başarısız olursa modeli sil |
| `max_acceptable_loss` | float | `null` | eval_loss üst sınırı |
| `require_human_approval` | bool | `false` | İnsan incelemesi için duraklat (çıkış kodu 4) |

#### `evaluation.safety` (İsteğe bağlı)

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `enabled` | bool | `false` | Güvenlik sınıflandırıcı değerlendirmesi |
| `classifier` | string | `"meta-llama/Llama-Guard-3-8B"` | Güvenlik sınıflandırıcı modeli |
| `test_prompts` | string | `"safety_prompts.jsonl"` | Adversarial test prompt dosyası. Yerleşik: `configs/safety_prompts/` |
| `max_safety_regression` | float | `0.05` | Maksimum güvensiz oran (binary kapı) |
| `scoring` | string | `"binary"` | Puanlama modu: `"binary"` veya `"confidence_weighted"` |
| `min_safety_score` | float | `null` | Ağırlıklı skor eşiği (confidence_weighted için) |
| `min_classifier_confidence` | float | `0.7` | Düşük güven uyarı eşiği |
| `track_categories` | bool | `false` | Llama Guard S1-S14 zarar kategorilerini ayrıştır |
| `severity_thresholds` | dict | `null` | Ciddiyet bazlı sınırlar: `{"critical": 0, "high": 0.01}` |

#### `evaluation.benchmark` (İsteğe bağlı)

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `enabled` | bool | `false` | lm-eval-harness benchmark'ları |
| `tasks` | list | `[]` | Görev isimleri (ör. `["arc_easy", "hellaswag"]`) |
| `min_score` | float | `null` | Minimum ortalama doğruluk |

#### `evaluation.llm_judge` (İsteğe bağlı)

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `enabled` | bool | `false` | LLM-Hakim puanlama |
| `judge_model` | string | `"gpt-4o"` | Hakim modeli (API veya yerel) |
| `min_score` | float | `5.0` | Minimum ortalama puan (1-10) |

---

## `compliance` (İsteğe bağlı — EU AI Act Madde 11 + Annex IV)

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `provider_name` | string | `""` | Kuruluş adı |
| `intended_purpose` | string | `""` | Modelin amacı |
| `risk_classification` | string | `"minimal-risk"` | `"high-risk"`, `"limited-risk"`, `"minimal-risk"` |

## `risk_assessment` (İsteğe bağlı — EU AI Act Madde 9)

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `intended_use` | string | `""` | Kullanım amacı |
| `foreseeable_misuse` | list | `[]` | Öngörülen kötüye kullanım senaryoları |
| `risk_category` | string | `"minimal-risk"` | Risk sınıflandırması |
| `mitigation_measures` | list | `[]` | Risk azaltma önlemleri |

## `monitoring` (İsteğe bağlı — EU AI Act Madde 12+17)

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `enabled` | bool | `false` | İzleme hook'larını etkinleştir |
| `metrics_export` | string | `"none"` | `"none"`, `"prometheus"`, `"datadog"` |
| `alert_on_drift` | bool | `true` | Model sapmasında uyar |

## `distributed` (İsteğe bağlı)

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `strategy` | string | `null` | `"deepspeed"` veya `"fsdp"` |
| `deepspeed_config` | string | `null` | Ön ayar: `"zero2"`, `"zero3"`, `"zero3_offload"` |

## `webhook` (İsteğe bağlı)

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `url` | string | `null` | Webhook URL |
| `url_env` | string | `null` | URL'yi içeren ortam değişkeni |
| `timeout` | int | `5` | HTTP istek zaman aşımı (saniye) |

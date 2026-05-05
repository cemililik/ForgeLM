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

#### `model.multimodal` (İsteğe bağlı — VLM modeller)

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `enabled` | bool | `false` | Görüntü-dil modeli (VLM) fine-tuning'i etkinleştir |
| `image_column` | string | `"image"` | Veri setinde görüntü yolu / URL'i taşıyan kolon adı |
| `text_column` | string | `"text"` | Metin / caption taşıyan kolon adı |

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

#### OOM Recovery (Bellek Hatası Kurtarma)

CUDA bellek yetersizliği (out-of-memory) hatalarında `per_device_train_batch_size` değerini
otomatik olarak yarıya indirir, `gradient_accumulation_steps` değerini ikiye katlar ve
training'i yeniden dener. Efektif batch boyutu korunur.

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `oom_recovery` | bool | `false` | CUDA OOM hatalarında batch boyutunu küçülterek yeniden dene |
| `oom_recovery_min_batch_size` | int | `1` | Bu batch boyutuna ulaşınca denemeyi durdur |

**Örnek:**

```yaml
training:
  per_device_train_batch_size: 8
  gradient_accumulation_steps: 2
  oom_recovery: true
  oom_recovery_min_batch_size: 1
```

#### GaLore (Optimizer Seviyesinde Bellek Optimizasyonu)

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `galore_enabled` | bool | `false` | GaLore gradient düşük rank projeksiyonunu etkinleştir |
| `galore_optim` | string | `"galore_adamw_8bit"` | GaLore optimizer: `"galore_adamw"`, `"galore_adamw_8bit"`, `"galore_adafactor"` |
| `galore_rank` | int | `128` | Gradient projeksiyonu için rank |
| `galore_update_proj_gap` | int | `200` | Projeksiyon güncellemeleri arası adım sayısı |
| `galore_scale` | float | `0.25` | GaLore ölçekleme faktörü |
| `galore_proj_type` | string | `"std"` | Projeksiyon tipi: `"std"`, `"reverse_std"`, `"right"`, `"left"`, `"full"` |
| `galore_target_modules` | list | `["q_proj", "k_proj", "v_proj", "o_proj"]` | GaLore uygulanacak modüller |

#### Uzun Bağlam Eğitimi

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `rope_scaling` | string | `null` | RoPE ölçekleme yöntemi: `"linear"`, `"dynamic"` |
| `neftune_noise_alpha` | float | `null` | NEFTune gürültü enjeksiyonu alpha değeri (ör. `5.0`) |
| `sliding_window_attention` | int | `null` | Kayan pencere dikkat boyutu (token) |
| `sample_packing` | bool | `false` | Kısa örnekleri tam uzunluklu dizilere paketle |

#### GPU Maliyet Tahmini

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `gpu_cost_per_hour` | float | `null` | Özel GPU maliyet oranı (USD/saat). null ise GPU modelinden otomatik algılanır |

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

#### `evaluation.benchmark` (İsteğe bağlı)

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `enabled` | bool | `false` | lm-eval-harness benchmark'ları |
| `tasks` | list | `[]` | Görev isimleri (ör. `["arc_easy", "hellaswag"]`) |
| `min_score` | float | `null` | Minimum ortalama doğruluk |

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
| `strategy` | string | `null` | `"deepspeed"` veya `"fsdp"` (null = tek GPU) |
| `deepspeed_config` | string | `null` | Ön ayar (`"zero2"`, `"zero3"`, `"zero3_offload"`) veya JSON yolu |
| `fsdp_strategy` | string | `"full_shard"` | `"full_shard"`, `"shard_grad_op"`, `"hybrid_shard"`, `"no_shard"` |
| `fsdp_auto_wrap` | bool | `true` | Transformer katmanlarını otomatik sar |
| `fsdp_offload` | bool | `false` | Parametreleri CPU'ya taşı |
| `fsdp_backward_prefetch` | string | `"backward_pre"` | `"backward_pre"` veya `"backward_post"` |
| `fsdp_state_dict_type` | string | `"FULL_STATE_DICT"` | `"FULL_STATE_DICT"` veya `"SHARDED_STATE_DICT"` |

## `synthetic` (İsteğe bağlı — Sentetik Veri Üretimi)

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `enabled` | bool | `false` | Sentetik veri üretimini etkinleştir |
| `teacher_model` | string | `null` | Distillasyon için öğretmen model (HF ID veya yerel yol) |
| `teacher_backend` | string | `"api"` | Öğretmen backend: `"api"` (OpenAI uyumlu) veya `"local"` |
| `teacher_api_key_env` | string | `null` | Öğretmen API anahtarı için ortam değişkeni |
| `teacher_api_base` | string | `null` | Öğretmen için özel API base URL |
| `seed_file` | string | `null` | Tohum prompt dosyası yolu (JSONL) |
| `output_file` | string | `"synthetic_data.jsonl"` | Üretilen veriler için çıktı dosyası |
| `num_samples` | int | `100` | Üretilecek örnek sayısı |
| `max_tokens` | int | `512` | Üretilen yanıt başına maksimum token |
| `temperature` | float | `0.7` | Üretim için örnekleme sıcaklığı |
| `top_p` | float | `0.9` | Top-p (nucleus) örnekleme |
| `system_prompt` | string | `null` | Öğretmen model için sistem promptu |
| `output_format` | string | `"sft"` | Çıktı formatı: `"sft"`, `"dpo"`, `"conversation"` |
| `batch_size` | int | `10` | API çağrıları için batch boyutu |
| `retry_attempts` | int | `3` | API hatası durumunda yeniden deneme sayısı |
| `timeout` | int | `60` | API istek zaman aşımı (saniye) |

---

## `webhook` (İsteğe bağlı)

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `url` | string | `null` | Webhook hedef URL |
| `url_env` | string | `null` | URL'yi içeren ortam değişkeni adı |
| `notify_on_start` | bool | `true` | Eğitim başlangıcında bildir |
| `notify_on_success` | bool | `true` | Başarıda bildir |
| `notify_on_failure` | bool | `true` | Hata durumunda bildir |
| `timeout` | int | `5` | HTTP istek zaman aşımı (saniye) |
| `allow_private_destinations` | bool | `false` | RFC1918 / loopback / link-local hedeflere webhook gönderimine izin verir (cluster içi Slack proxy, on-prem Teams gateway gibi). Varsayılan yalnızca genel internet — SSRF koruması |
| `tls_ca_bundle` | string | `null` | `requests`'e `verify=` olarak iletilen özel CA bundle yolu (örn. kurumsal MITM CA). Boşsa `certifi` paketinin gömülü deposu kullanılır |

## `merge` (İsteğe bağlı)

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `enabled` | bool | `false` | Model birleştirmeyi etkinleştir |
| `method` | string | `"ties"` | `"ties"`, `"dare"`, `"slerp"`, `"linear"` |
| `models` | list | `[]` | `{path, weight}` sözlük listesi |
| `output_dir` | string | `"./merged_model"` | Çıktı dizini |

## `auth` (İsteğe bağlı)

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `hf_token` | string | `null` | HuggingFace tokeni (tercih: `HUGGINGFACE_TOKEN` ortam değişkeni) |

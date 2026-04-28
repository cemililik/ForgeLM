# ForgeLM Mimarisi

ForgeLM modülerlik ve genişletilebilirlik gözetilerek tasarlanmıştır. İş akışı her biri ayrı bir modül tarafından yönetilen aşamalara bölünmüştür.

## Sistem Genel Bakışı

```
forgelm --config job.yaml
    │
    ├── cli.py          → Argüman ayrıştırma, config yükleme, orkestrasyon
    ├── config.py       → Pydantic doğrulama (19+ config modeli)
    ├── utils.py        → HF kimlik doğrulama
    ├── model.py        → Model + tokenizer + LoRA/PEFT yükleme
    ├── data.py         → Veri seti yükleme + formatlama
    ├── trainer.py      → Eğitim (TRL üzerinden 6 trainer tipi)
    │   ├── benchmark.py    → lm-eval-harness değerlendirme
    │   ├── safety.py       → Güvenlik kontrolü (confidence, S1-S14, ciddiyet)
    │   ├── judge.py        → LLM-Hakim puanlama
    │   ├── model_card.py   → HF model kartı üretimi
    │   ├── compliance.py   → EU AI Act denetim belgeleri + audit log
    │   └── webhook.py      → Slack/Teams bildirimleri
    ├── merging.py      → TIES/DARE/SLERP model birleştirme (--merge)
    ├── synthetic.py    → Sentetik veri üretimi (--generate-data)
    └── wizard.py       → Etkileşimli config üretici (--wizard)
```

## Dizin Yapısı

```
ForgeLM/
├── forgelm/                  # Çekirdek Python Paketi (26 modül)
│   ├── __init__.py           # Hızlı CLI başlatma için lazy import
│   ├── cli.py                # CLI giriş noktası ve mod yönlendirici
│   ├── config.py             # 19 Pydantic config modeli
│   ├── data.py               # Veri yükleme (SFT/DPO/KTO/GRPO/multimodal)
│   ├── data_audit.py         # Denetim pipeline'ı (uzunluk/dil/dedup/sızıntı/PII/sır)
│   ├── ingestion.py          # Ham doküman → SFT JSONL (PDF/DOCX/EPUB/TXT/Markdown)
│   ├── model.py              # Model + LoRA/DoRA/PiSSA + MoE algılama
│   ├── trainer.py            # Eğitim orkestrasyonu (6 trainer tipi)
│   ├── inference.py          # Paylaşılan çıkarım ilkelleri (yükleme/üretme/akış)
│   ├── chat.py               # Etkileşimli terminal REPL
│   ├── export.py             # GGUF dışa aktarma (llama-cpp-python)
│   ├── fit_check.py          # Ön uçuş VRAM tahmincisi
│   ├── deploy.py             # Dağıtım config üreteci (Ollama/vLLM/TGI/HF Endpoints)
│   ├── results.py            # TrainResult dataclass
│   ├── benchmark.py          # lm-evaluation-harness entegrasyonu
│   ├── safety.py             # Güvenlik değerlendirme (Llama Guard, S1-S14)
│   ├── judge.py              # LLM-Hakim (API + yerel)
│   ├── compliance.py         # EU AI Act uyumluluk + AuditLogger + kaynak takibi
│   ├── model_card.py         # HF uyumlu model kartı üretimi
│   ├── merging.py            # Model birleştirme (TIES/DARE/SLERP/linear)
│   ├── synthetic.py          # Sentetik veri üretimi (öğretmen→öğrenci)
│   ├── grpo_rewards.py       # Yerleşik GRPO format/uzunluk ödül şekillendiricileri
│   ├── quickstart.py         # Tek komutlu hazır şablonlar
│   ├── wizard.py             # Etkileşimli yapılandırma sihirbazı
│   ├── webhook.py            # Webhook bildirimleri (Slack/Teams)
│   └── utils.py              # Kimlik doğrulama + checkpoint yönetimi
├── forgelm/templates/        # Quickstart şablon paketleri (config.yaml + tohum veri)
├── configs/
│   ├── deepspeed/            # ZeRO-2, ZeRO-3, ZeRO-3+Offload ön ayarları
│   └── safety_prompts/       # Yerleşik adversarial prompt kütüphanesi (140 prompt, 6 kategori)
├── notebooks/                # 10 Colab-uyumlu Jupyter notebook
├── tests/                    # 800+ birim test, 47 test dosyası
├── docs/
│   ├── guides/               # Kullanıcı rehberleri (ingest, audit, alignment, CI/CD, …)
│   └── qms/                  # EU AI Act QMS SOP şablonları
├── Dockerfile                # Çok aşamalı Docker yapısı
├── docker-compose.yaml       # Eğitim + TensorBoard servisleri
└── config_template.yaml      # Açıklamalı config örneği
```

## Bileşen Detayları

### `cli.py`
Orkestratör. 13+ CLI flag'ini ayrıştırır: `--config`, `--wizard`, `--dry-run`, `--offline`, `--resume`, `--quiet`, `--benchmark-only`, `--merge`, `--compliance-export`, `--output-format`, `--log-level`, `--version`. Çıkış kodları: 0 (başarı), 1 (config hatası), 2 (eğitim hatası), 3 (değerlendirme hatası), 4 (insan onayı bekleniyor).

### `config.py`
19+ Pydantic v2 modeli: ModelConfig, LoraConfigModel, TrainingConfig, DataConfig, DataGovernanceConfig, EvaluationConfig, SafetyConfig, BenchmarkConfig, JudgeConfig, WebhookConfig, DistributedConfig, MergeConfig, ComplianceMetadataConfig, RiskAssessmentConfig, MonitoringConfig, MoeConfig, MultimodalConfig, AuthConfig. Çapraz alan doğrulaması içerir.

### `data.py`
HuggingFace `datasets` kütüphanesi ile arayüz. Veri formatını otomatik algılar (SFT, DPO, KTO, GRPO, multimodal) ve uyumsuzlukta önerili trainer_type ile hata verir. Mix ratio ile çoklu veri seti karıştırma. `tokenizer.apply_chat_template()` ile sohbet şablonları.

### `model.py`
Transformers veya Unsloth backend ile model yükleme. QLoRA (4-bit NF4), PEFT (LoRA, DoRA, PiSSA, rsLoRA), MoE expert kuantizasyon/seçimi. Dağıtık-bilinçli (DeepSpeed/FSDP). Multimodal-bilinçli (AutoProcessor).

### `trainer.py`
TRL trainer'larını (SFTTrainer, DPOTrainer, KTOTrainer, ORPOTrainer, CPOTrainer/SimPO, GRPOTrainer) sarar. Pipeline: baseline → eğitim → kayıp → benchmark → güvenlik → LLM-hakim → model kaydet → model kartı → uyumluluk → webhook. GaLore optimizer seviyesinde bellek optimizasyonu (tam parametre eğitimi için gradient düşük rank projeksiyonu) ve uzun bağlam özellikleri (RoPE ölçekleme, NEFTune gürültü enjeksiyonu, kayan pencere dikkat, örnek paketleme) destekler. Otomatik geri alma, insan onay kapısı, denetim loglama, kaynak takibi içerir.

### `safety.py`
İki puanlama modu: binary (güvenli/güvensiz oranı) ve confidence-weighted (sınıflandırıcı güven skoru). 3 katmanlı güvenlik kapısı: binary oran → confidence skoru → ciddiyet eşiği. Llama Guard S1-S14 zarar kategorileri, ciddiyet seviyeleri (kritik/yüksek/orta/düşük), düşük güven uyarıları, çalışmalar arası trend takibi (safety_trend.jsonl).

### `compliance.py`
EU AI Act uyumluluk motoru — Madde 9-17:
- `AuditLogger`: Benzersiz run_id ile ekleme-yalnızca JSON Lines olay logu (Madde 12)
- `generate_training_manifest()`: Annex IV metadata (Madde 11)
- `generate_data_governance_report()`: Veri kalitesi istatistikleri (Madde 10)
- `generate_model_integrity()`: SHA-256 checksum'lar (Madde 15)
- `generate_deployer_instructions()`: Dağıtıcı talimatları (Madde 13)
- `export_evidence_bundle()`: Denetçiler için ZIP arşivi

### `merging.py`
4 strateji: linear interpolasyon, TIES-Merging, DARE, SLERP. State dict seviyesinde — mergekit bağımlılığı gerektirmez.

### `synthetic.py`
Öğretmen-öğrenci distillasyonu ile sentetik veri üretimi. `SyntheticDataGenerator` sınıfı bir öğretmen modeli (API tabanlı veya yerel) alır, tohum promptlardan eğitim örnekleri üretir ve formatlanmış JSONL veri setleri çıktılar. `--generate-data` CLI flag'i veya `synthetic` config bölümü ile tetiklenir. Yapılandırılabilir öğretmen backend'leri, çıktı formatları ve üretim parametrelerini destekler.

### `wizard.py`
Etkileşimli CLI sihirbazı. GPU algılama, model seçimi, LoRA stratejisi, eğitim hedefi (6 trainer), güvenlik değerlendirme (binary/confidence_weighted, kategori takibi), uyumluluk metadata yapılandırması.

### `webhook.py`
Eğitim başlangıcı/başarı/başarısızlık durumlarında yapılandırılmış JSON payload gönderir. Yapılandırılabilir timeout ile güvenilir hata yönetimi.

### `utils.py`
HuggingFace kimlik doğrulama (config, env var, yerel cache — modern XDG yolu). Checkpoint yönetimi (tutma, silme, UUID-ekli sıkıştırma).

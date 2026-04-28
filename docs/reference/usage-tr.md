# Kullanım Rehberi

ForgeLM, komut satırı arayüzü üzerinden çalıştırılmak üzere tasarlanmıştır — hem yerel deneyler hem de otomatik CI/CD pipeline'ları için uygundur.

## Ön Koşullar

- Python 3.10+
- CUDA destekli NVIDIA GPU (önerilir; CPU modu çok yavaş)

```bash
git clone https://github.com/cemililik/ForgeLM.git
cd ForgeLM
pip install -e .
```

### İsteğe bağlı kurulumlar

```bash
pip install -e ".[qlora]"        # 4-bit kuantizasyon (Linux)
pip install -e ".[unsloth]"      # Unsloth backend (Linux)
pip install -e ".[eval]"         # lm-evaluation-harness
pip install -e ".[tracking]"     # W&B deney takibi
pip install -e ".[distributed]"  # DeepSpeed çoklu GPU
pip install -e ".[merging]"      # mergekit model birleştirme
```

## Kimlik Doğrulama

Gated modeller (Llama, Gemma) veya özel veri setleri için:

1. **Ortam Değişkeni** (önerilen): `export HUGGINGFACE_TOKEN="hf_xxxxx"`
2. **Config Dosyası**: YAML'da `auth: { hf_token: "hf_xxxxx" }`
3. **Yerel Cache**: `huggingface-cli login`

## CLI Referansı

### Temel Komutlar

```bash
forgelm --config my_config.yaml              # Model eğit
forgelm --wizard                             # Etkileşimli config oluşturucu
forgelm --config my_config.yaml --dry-run    # Config doğrula (GPU gerektirmez)
forgelm --version                            # Versiyon göster
```

### Çıktı ve Loglama

```bash
forgelm --config my_config.yaml --output-format json   # CI/CD için JSON çıktı
forgelm --config my_config.yaml --quiet                # Sadece uyarı/hata göster
forgelm --config my_config.yaml -q                     # Kısa form
forgelm --config my_config.yaml --log-level DEBUG      # Log seviyesi ayarla
```

### Eğitim Modları

```bash
forgelm --config my_config.yaml --resume               # Son checkpoint'ten devam
forgelm --config my_config.yaml --resume ./checkpoints/checkpoint-500
forgelm --config my_config.yaml --offline              # İzole mod (HF Hub yok)
```

### Sentetik Veri Üretimi

```bash
# Öğretmen model distillasyonu ile sentetik eğitim verisi üret
forgelm --config my_config.yaml --generate-data
```

Bu komut, eğitim başlamadan önce bir öğretmen modelden eğitim verisi üretmek için `synthetic` config bölümünü kullanır. Tüm sentetik veri seçenekleri için [Konfigürasyon Rehberi](configuration-tr.md)'ne bakın.

### Doküman Yutma (v0.5.0+; v0.5.1 token-aware; v0.5.2 markdown + secrets-mask)

Ham PDF / DOCX / EPUB / TXT / Markdown'ı SFT'ye uygun JSONL'a dönüştürür. Opsiyonel bağımlılık: `pip install forgelm[ingestion]`. Ayrıntılar için [Doküman Yutma Rehberi](../guides/ingestion-tr.md).

```bash
# Tek dosya
forgelm ingest ./book.epub --output data/sft.jsonl

# Recursive dizin yürüyüşü + paragraf chunking
forgelm ingest ./policies/ --recursive --output data/policies.jsonl

# Kayan pencere + örtüşme (uzun teknik dokümanlar)
forgelm ingest ./scan.pdf --strategy sliding --chunk-size 1024 --overlap 128 \
  --output data/scan.jsonl

# Yazmadan önce PII'yi maskele
forgelm ingest ./customer_emails/ --pii-mask --output data/anon.jsonl

# Token-aware chunking (v0.5.1) — chunk'ları modelinizin vocab'ına göre boyutlandırır
forgelm ingest ./policies/ --recursive --output data/policies.jsonl \
  --chunk-tokens 1024 --tokenizer "Qwen/Qwen2.5-7B-Instruct"
```

### Veri Seti Denetimi (v0.5.0+; v0.5.1 subcommand; v0.5.2 MinHash + quality + secrets)

CPU-only kalite + governance denetimi. `data_audit_report.json` üretir. Ayrıntılar için [Denetim Rehberi](../guides/data_audit-tr.md).

```bash
# Tek split (v0.5.1 subcommand)
forgelm audit data/sft.jsonl --output ./audit/

# Çoklu split (train.jsonl / validation.jsonl / test.jsonl içeren dizin)
forgelm audit data/ --output ./audit/

# Tüm split'leri göster (bulgu olmasa bile)
forgelm audit data/ --verbose

# Özel Hamming eşiği
forgelm audit data/ --near-dup-threshold 5

# stdout'a makine-okunabilir özet
forgelm audit data/sft.jsonl --output ./audit/ --output-format json

# Eski alias (çalışmaya devam ediyor; bir uyarı log'lanır)
forgelm --data-audit data/sft.jsonl --output ./audit/
```

Denetim şunları yakalar: split başına örnek sayısı + uzunluk dağılımı, top-3 dil tespiti, **LSH-banded** simhash near-duplicate oranı (Faz 11.5; uç eşiklerde brute-force fallback), cross-split sızıntı (sessiz train-test örtüşmesi), PII flag sayıları + **şiddet katmanları** (`pii_severity` bloğu her PII tipini critical / high / medium / low olarak puanlar ve bir `worst_tier` verdict yüzdürür).

Trainer'ın `output_dir`'ünde `data_audit_report.json` mevcutsa, bulgular EU AI Act Madde 10 governance artifact'ında `data_audit` anahtarı altında otomatik olarak inline edilir.

### Değerlendirme, Birleştirme ve Uyumluluk

```bash
forgelm --config my_config.yaml --benchmark-only /path/to/model   # Sadece değerlendir
forgelm --config my_config.yaml --merge                            # Modelleri birleştir
forgelm --config my_config.yaml --compliance-export ./audit/       # Uyumluluk belgeleri
```

## Çıkış Kodları

| Kod | Anlam | CI/CD Aksiyonu |
|-----|-------|---------------|
| `0` | Başarı | Modeli deploy et |
| `1` | Config hatası | YAML'ı düzelt |
| `2` | Eğitim hatası | GPU/bellek/bağımlılıkları kontrol et |
| `3` | Değerlendirme hatası | Model eşiğin altında |
| `4` | Onay bekleniyor | İnsan incelemesi gerekli (`require_human_approval: true`) |

## Eğitim Çıktısı

```
checkpoints/
├── final_model/
│   ├── adapter_config.json
│   ├── adapter_model.safetensors
│   ├── README.md                    # Otomatik model kartı
│   ├── deployer_instructions.md     # Dağıtıcı rehberi (Madde 13)
│   └── model_integrity.json         # SHA-256 checksum'lar (Madde 15)
├── compliance/
│   ├── compliance_report.json       # Tam denetim izi (Annex IV)
│   ├── training_manifest.yaml       # Okunabilir özet
│   ├── data_provenance.json         # Veri seti parmak izleri
│   ├── risk_assessment.json         # Risk beyanı (Madde 9)
│   └── annex_iv_metadata.json       # Annex IV metadata
├── audit_log.jsonl                  # Yapılandırılmış olay logu (Madde 12)
├── safety/
│   ├── safety_results.json          # Güvenlik sonuçları (kategori, ciddiyet)
│   └── safety_trend.jsonl           # Çalışmalar arası trend
└── benchmark/                       # Benchmark sonuçları
```

## Günlükler ve İzleme

ForgeLM yapılandırılmış formatta stderr'e log yazar:
```
2026-03-24 10:30:00 [INFO] forgelm.trainer: Starting training...
2026-03-24 11:45:00 [WARNING] forgelm.trainer: eval_steps (200) is larger than dataset (50 samples).
```

### TensorBoard

```bash
tensorboard --logdir=./checkpoints/runs/
```

### GaLore (Bellek Verimli Tam Parametre Eğitimi)

GaLore, LoRA'ya alternatif olarak optimizer seviyesinde bellek optimizasyonu sağlar ve gradient düşük rank projeksiyonu ile tam parametre eğitimine olanak tanır:

```yaml
training:
  galore_enabled: true
  galore_optim: "galore_adamw_8bit"
  galore_rank: 128
  galore_update_proj_gap: 200
  galore_scale: 0.25
  galore_proj_type: "std"
  galore_target_modules: ["q_proj", "k_proj", "v_proj", "o_proj"]
```

### Uzun Bağlam Eğitimi

RoPE ölçekleme, NEFTune gürültü enjeksiyonu, kayan pencere dikkat ve örnek paketleme ile genişletilmiş bağlam penceresi desteğini etkinleştirin:

```yaml
training:
  rope_scaling: "linear"              # "linear" veya "dynamic"
  neftune_noise_alpha: 5.0            # Daha iyi genelleme için NEFTune gürültüsü
  sliding_window_attention: 4096      # Kayan pencere boyutu (token)
  sample_packing: true                # Kısa örnekleri tam uzunluklu dizilere paketle
```

### GPU Maliyet Tahmini

ForgeLM GPU modelinizi otomatik algılar (18 GPU modeli desteklenir) ve eğitim çalışması başına tahmini maliyeti takip eder. Çıktı JSON sonuçlarına, webhook bildirimlerine ve model kartlarına dahil edilir:

```
GPU Maliyet Tahmini:
  GPU Modeli: NVIDIA A100 80GB
  GPU Saati: 2.4
  Tahmini Maliyet: $7.20 USD
  Tepe VRAM: 22.1 GB
```

Özel maliyet oranı belirlemek için:

```yaml
training:
  gpu_cost_per_hour: 3.00  # GPU-saat başına USD
```

### W&B

```yaml
training:
  report_to: "wandb"
  run_name: "my-experiment"
```

### Webhook Bildirimleri

```yaml
webhook:
  url_env: "FORGELM_WEBHOOK_URL"
  notify_on_start: true
  notify_on_success: true
  notify_on_failure: true
```

## Docker

```bash
docker build -t forgelm --build-arg INSTALL_EVAL=true .

docker run --gpus all \
  -v $(pwd)/config.yaml:/workspace/config.yaml:ro \
  -v $(pwd)/output:/workspace/output \
  forgelm --config /workspace/config.yaml

# Çoklu GPU
docker run --gpus all --shm-size=16g \
  forgelm torchrun --nproc_per_node=4 -m forgelm.cli --config /workspace/config.yaml
```

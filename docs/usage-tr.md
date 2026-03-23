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

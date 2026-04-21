# Dağıtık Eğitim Rehberi (Çoklu GPU)

ForgeLM, **DeepSpeed** ve **PyTorch FSDP** aracılığıyla çoklu GPU dağıtık eğitimi destekler. Bu sayede daha büyük modeller (30B+ parametre) eğitilebilir veya eğitim birden fazla GPU'da önemli ölçüde hızlandırılabilir.

## Ön Koşullar

```bash
# DeepSpeed
pip install forgelm[distributed]

# FSDP, PyTorch'un içinde yerleşiktir — ek kurulum gerekmez
```

## Hızlı Başlangıç

### DeepSpeed ZeRO-2 (Önerilen Başlangıç Noktası)

```yaml
# my_config.yaml
distributed:
  strategy: "deepspeed"
  deepspeed_config: "zero2"
```

`torchrun` ile başlatma:
```bash
torchrun --nproc_per_node=4 -m forgelm.cli --config my_config.yaml
```

Veya `accelerate` ile:
```bash
accelerate launch --num_processes=4 -m forgelm.cli --config my_config.yaml
```

### FSDP Full Shard

```yaml
distributed:
  strategy: "fsdp"
  fsdp_strategy: "full_shard"
  fsdp_auto_wrap: true
```

```bash
torchrun --nproc_per_node=4 -m forgelm.cli --config my_config.yaml
```

---

## DeepSpeed Yapılandırması

ForgeLM, üç yerleşik DeepSpeed ön ayarı sunar. `deepspeed_config` parametresine bu isimlerden birini veya kendi JSON dosyanızın yolunu verin.

### Ön Ayarlar (Presets)

| Ön Ayar | ZeRO Aşaması | Offload | En Uygun |
|---------|-------------|---------|----------|
| `zero2` | 2 | Hayır | 2-4 GPU'da 7B-13B modeller |
| `zero3` | 3 | Hayır | 13B-30B modeller, parametrelerin GPU'lar arasında bölünmesi |
| `zero3_offload` | 3 | CPU | 30B-70B modeller, sınırlı VRAM, yeterli CPU RAM |

### Kullanım

```yaml
distributed:
  strategy: "deepspeed"
  deepspeed_config: "zero2"       # Ön ayar adı
  # deepspeed_config: "./my_ds_config.json"  # Veya özel dosya yolu
```

### ZeRO Aşama Karşılaştırması

**ZeRO-2** (Optimizer + Gradient Bölümleme):
- Optimizer durumlarını ve gradyanları GPU'lar arasında böler
- Her GPU, model parametrelerinin tam bir kopyasını tutar
- Bellek tasarrufu ve iletişim yükü arasında iyi denge
- QLoRA (4-bit) ile iyi çalışır

**ZeRO-3** (Tam Parametre Bölümleme):
- Her şeyi böler: optimizer, gradyanlar VE parametreler
- Hiçbir GPU'nun tam modeli tutması gerekmez
- En yüksek bellek tasarrufu — çok daha büyük modeller eğitilebilir
- Daha yüksek iletişim yükü
- **Uyarı**: QLoRA (4-bit kuantizasyon) ile bilinen uyumluluk sorunları var

**ZeRO-3 + CPU Offload**:
- ZeRO-3 ile aynı, artı optimizer ve parametreleri CPU RAM'e aktarır
- Eğitim hızı pahasına GPU bellek tasarrufunu maksimize eder
- GPU VRAM darboğaz olduğunda ama CPU RAM yeterli olduğunda faydalı

---

## FSDP Yapılandırması

PyTorch Fully Sharded Data Parallel (FSDP), DeepSpeed'e alternatif olarak PyTorch'un içinde yerleşik bir çözümdür.

### Stratejiler

| Strateji | Açıklama | Bellek Tasarrufu |
|----------|----------|-----------------|
| `full_shard` | Parametreleri, gradyanları ve optimizer durumlarını böl | En Yüksek |
| `shard_grad_op` | Yalnızca gradyanları ve optimizer durumlarını böl | Orta |
| `hybrid_shard` | Düğüm içi tam bölme, düğümler arası çoğaltma | Çoklu Düğüm |
| `no_shard` | Standart DDP (bölme yok) | Yok |

### Kullanım

```yaml
distributed:
  strategy: "fsdp"
  fsdp_strategy: "full_shard"
  fsdp_auto_wrap: true
  fsdp_offload: false
```

---

## Uyumluluk Notları

### QLoRA + Dağıtık

| Kombinasyon | Durum | Notlar |
|------------|-------|--------|
| QLoRA + ZeRO-2 | Çalışır | Çoklu GPU QLoRA için önerilir |
| QLoRA + ZeRO-3 | Kararsız | bitsandbytes + parametre bölümleme ile bilinen sorunlar |
| QLoRA + FSDP full_shard | Deneysel | Özel PEFT/FSDP entegrasyon bayrakları gerekebilir |
| QLoRA + FSDP shard_grad_op | Çalışır | ZeRO-2 seviyesi bölümlemeye benzer |

### Arka Uç Uyumluluğu

| Arka Uç | Çoklu GPU | Notlar |
|---------|-----------|--------|
| `transformers` | Evet | Tam DeepSpeed ve FSDP desteği |
| `unsloth` | Hayır | Yalnızca tek GPU — dağıtık config ayarlanırsa ForgeLM uyarı verir |

---

## Docker + Çoklu GPU

```bash
docker run --gpus all \
  -v $(pwd)/my_config.yaml:/workspace/config.yaml \
  --shm-size=16g \
  forgelm:full \
  torchrun --nproc_per_node=4 -m forgelm.cli --config /workspace/config.yaml
```

> **Not**: `--shm-size=16g` çoklu GPU eğitimi için önemlidir. PyTorch, süreçler arası iletişim için paylaşılan bellek kullanır ve Docker'ın varsayılan paylaşılan belleği (64MB) yetersizdir.

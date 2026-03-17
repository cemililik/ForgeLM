# Kullanım Rehberi

ForgeLM, komut satırı arayüzü (Command Line Interface - CLI) üzerinden çalıştırılmak üzere tasarlanmıştır, bu da onu hem yerel denemeler yapmak, hem de uzaktan GPU kullanımı (RunPod, Lambda Labs, AWS) için mükemmel kılar.

## Ön Koşullar

NVIDIA GPU'ya ve CUDA'ya sahip bir makineniz olduğundan emin olun. ForgeLM CPU modunda çalışmaya çalışacak olsa da, Büyük Dil Modellerini (LLM'ler) etkili bir şekilde eğitmek GPU gerektirir.

```bash
git clone https://github.com/cemililik/ForgeLM.git
cd ForgeLM
python3 -m pip install -e .
```

### Opsiyonel kurulumlar

- QLoRA bağımlılıklarını aç (Linux):

```bash
python3 -m pip install -e ".[qlora]"
```

- Unsloth backend’i aç (Linux):

```bash
python3 -m pip install -e ".[unsloth]"
```

- Phase 2 değerlendirme/benchmark bağımlılıklarını aç:

```bash
python3 -m pip install -e ".[eval]"
```

## Kimlik Doğrulama (Authentication)

Eğer erişime kapalı (gated) olan (Meta'nın Llama ailesi gibi) modelleri ya da özel veri setlerini kullanıyorsanız, kimlik doğrulaması yapmalısınız. ForgeLM kimlik doğrulamasını şu sırayla kontrol eder:

1. **Konfigürasyon (Config) Dosyası**: Eğer yaml dosyanızın `auth:` bloğunun altında `hf_token: "xxx"` bulunuyorsa.
2. **Çevre Değişkeni (Environment Variable)**: Eğer terminalde `export HUGGINGFACE_TOKEN="hf_xxxxx"` çalıştırıldıysa.
3. **Yerel Önbellek (Local Cache)**: Daha önceden aynı bilgisayarda `huggingface-cli login` çalıştırdıysanız (Tavsiye edilen).

## Eğitim Sürecini (Job) Başlatma

1. Eğitim işinizi bir YAML dosyasında (örneğin my_job.yaml) tanımlayın.
```bash
cp config_template.yaml my_job.yaml
nano my_job.yaml
```

2. Yaptığınız ayarları sisteme göstererek CLI komutunu yürütün:
```bash
python3 -m forgelm.cli --config my_job.yaml
# veya (editable install sonrası):
forgelm --config my_job.yaml
```

## Webhook Bildirimleri (Opsiyonel)

Eğitim başladığında/başarıyla bittiğinde/hata aldığında bildirim almak istiyorsanız YAML içinde `webhook:` bloğunu kullanabilirsiniz. CI/CD için URL’yi dosyaya yazmak yerine env var ile vermek daha güvenlidir:

```bash
export FORGELM_WEBHOOK_URL="https://hooks.slack.com/services/XXX/YYY/ZZZ"
```

`my_job.yaml` içinde:

```yaml
webhook:
  url_env: "FORGELM_WEBHOOK_URL"
  notify_on_start: true
  notify_on_success: true
  notify_on_failure: true
```

## Günlükler (Logs) ve Çıktılar

İş çalışırken, ForgeLM standart çıktılara (stdout - terminal ekranı) konfigürasyon durumlarını, veri setinin boyut ve şekillerini (shapes) ve LoRA tarafından eğitilebilir hale gelmiş parametre yüzdelerini basacaktır.

Hugging Face Trainer aracı metrikleri (Eğitim Kaybı - Training Loss, Doğrulama Kaybı - Validation Loss vb.) komut isteminize (konsol) ve eşzamanlı olarak TensorBoard'a loglayacaktır.

Eğitim sırasında bir terminal sekmesi açarak, oluşan loss (kayıp) değerlerini ve başarıları canlı grafiklerle saniye saniye izleyebilirsiniz:

```bash
tensorboard --logdir=./checkpoints/runs/
```

### Nihai Eserler (Artifacts)
Eğitim başarıyla tamamlandığında:
1. Son model/adaptörler ve tokenizer `training.output_dir/training.final_model_dir` altına kaydedilir (varsayılan: `./checkpoints/final_model/`).
2. Aradaki checkpoint’ler `training.output_dir` altında `save_total_limit` ayarınıza göre tutulur.

Varsayılan olarak ForgeLM **sadece adaptörleri (LoRA)** kaydeder; bu hem çıktıyı küçük tutar hem de Phase 2 auto-revert için güvenlidir. Birleştirilmiş (merge) tam modeli kaydetmek istersen:

```yaml
training:
  merge_adapters: true
```

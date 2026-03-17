# Kullanım Rehberi

ForgeLM, komut satırı arayüzü (Command Line Interface - CLI) üzerinden çalıştırılmak üzere tasarlanmıştır, bu da onu hem yerel denemeler yapmak, hem de uzaktan GPU kullanımı (RunPod, Lambda Labs, AWS) için mükemmel kılar.

## Ön Koşullar

NVIDIA GPU'ya ve CUDA'ya sahip bir makineniz olduğundan emin olun. ForgeLM CPU modunda çalışmaya çalışacak olsa da, Büyük Dil Modellerini (LLM'ler) etkili bir şekilde eğitmek GPU gerektirir.

```bash
git clone https://github.com/cemililik/ForgeLM.git
cd ForgeLM
pip install -r requirements.txt
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
python -m forgelm.cli --config my_job.yaml
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
1. Son, birleştirilmiş ağırlıklar (veya LoRA adaptörleri) ve modifiye edilmiş yeni tokenizer (işaretleyici) `./final_model/` dizinine kaydedilecektir.
2. Eğitiminizin aralardaki yedek ağırlıkları (intermediate checkpoints) ise sizin yaml konfigürasyonunda yer alan `save_total_limit` parametrenize bağlı olarak saklanacak ve `./checkpoints/` dizininde konumlandırılacaktır.

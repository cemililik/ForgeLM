# Konfigürasyon Rehberi

ForgeLM tüm yapılandırma için YAML dosyalarını kullanır. Bu sayede, etkileşimli kabuk istemleri (shell prompts) gerektirmeden, deterministik, ve tekrarlanabilir eğitim çalıştırmaları yapılmasına olanak tanınır.

## Örnek Temel Konfigürasyon (`config_template.yaml`)

```yaml
model:
  name_or_path: "meta-llama/Llama-2-7b-hf"
  max_length: 2048
  load_in_4bit: true
  backend: "transformers" # 2-5x hız için "unsloth" seçilebilir
  # Opsiyonel bitsandbytes gelişmiş ayarları (Transformers backend + 4bit):
  # bnb_4bit_use_double_quant: true
  # bnb_4bit_quant_type: "nf4"
  # bnb_4bit_compute_dtype: "auto"   # auto|bfloat16|float16|float32

lora:
  r: 8
  alpha: 16
  dropout: 0.1
  bias: "none"
  use_dora: false
  target_modules: 
    - "q_proj"
    - "v_proj"
  task_type: "CAUSAL_LM"

training:
  output_dir: "./checkpoints"
  final_model_dir: "final_model"
  merge_adapters: false
  num_train_epochs: 3
  per_device_train_batch_size: 4
  gradient_accumulation_steps: 2
  learning_rate: 2.0e-5
  warmup_ratio: 0.1
  weight_decay: 0.01
  eval_steps: 200
  save_steps: 200
  save_total_limit: 3
  packing: false

data:
  dataset_name_or_path: "sahip_huggingface_dataset_org/dataset_adi"
  shuffle: true
  clean_text: true
  add_eos: true

auth:
  hf_token: "hf_SENIN_GIZLI_TOKENIN"

evaluation:
  auto_revert: false
  max_acceptable_loss: 2.5
  baseline_loss: null # Boş bırakılırsa otomatik hesaplanır

webhook:
  url: "https://webhook-adresiniz.com/api/notify"
  notify_on_start: true
  notify_on_success: true
  notify_on_failure: true
```

## Şema Detayları

### `model`
- **`name_or_path`**: (Zorunlu) Hugging Face repo ID'si (örn. `mistralai/Mistral-7B-v0.1`) veya temel modele doğrudan işaret eden bir yerel dizin yolu.
- **`max_length`**: (Tamsayı) Tokenizer için maksimum bağlam uzunluğu (context length).
- **`load_in_4bit`**: (Boolean) Bellek kullanımını büyük ölçüde azaltmak için QLoRA 4-bit (NF4) kuantizasyonunu etkinleştirir. Standart değer `true`.
- **`backend`**: (String) Eğitim için kullanılacak motor. Standart olan `'transformers'` ayarıdır. Eğitim hızını 2 ile 5 kat arası artırmak için `'unsloth'` olarak değiştirilebilir (unsloth kütüphanesini sisteminize kurmayı gerektirir).

### `lora`
Parametre-Verimli İnce Ayar (Parameter-Efficient Fine-Tuning - PEFT) stratejilerini tanımlar.
- **`r`**: LoRA dikkat boyutu (rank). Daha yüksek sayı = daha fazla parametre manipülasyonu.
- **`alpha`**: LoRA ölçeklendirmesi (scaling) için alpha parametresi.
- **`dropout`**: LoRA katmanları için dropout olasılığı.
- **`bias`**: LoRA için bias türü. `'none'`, `'all'` veya `'lora_only'` değerlerini alabilir.
- **`use_dora`**: (Boolean) Ağırlık Ayrıştırılmış (Weight-Decomposed - DoRA) yapıyı kullanmayı açar, ağırlıkların yönünü ve büyüklüğünü ayırarak aynı parametre sayısıyla LoRA'dan daha iyi performans sağlar. Standart olarak `false`.
- **`target_modules`**: LoRA'nın uygulanacağı model modüllerinin listesi. Genellikle `["q_proj", "k_proj", "v_proj", "o_proj"]` şeklindedir.

### `training`
Hiperparametreleri tanımlar.
- **`output_dir`**: Eğitim sırasında checkpoint'lerin (ağırlıkların) kaydedileceği dizin.
- **`final_model_dir`**: `output_dir` altında nihai artefact'ların yazılacağı alt dizin (varsayılan: `final_model`).
- **`merge_adapters`**: `false` (varsayılan) iken sadece adaptör (LoRA) kaydeder. `true` iken adaptörleri merge edip tam modeli kaydetmeyi dener.
- **`learning_rate`**: AdamW optimize edici (optimizer) için başlangıç öğrenme oranı (learning rate).
- **`per_device_train_batch_size`**: Her GPU çekirdeği/cihazı başına batch boyutu.
- **`gradient_accumulation_steps`**: Geriye dönük/güncelleme adımından önce bilgi biriktirilecek güncelleme adımı sayısı.
- **`packing`**: TRL `SFTTrainer` içinde sequence packing'i açar (ileri seviye; veri formatından emin değilsen `false` bırak).

### `data`
- **`dataset_name_or_path`**: Hugging face depo kimliği (örn. `timdettmers/openassistant-guanaco`) veya bir JSON/CSV dosyasının yerel yolu.
- **`clean_text`**: Gereksiz tekrarlanan boşlukları temizler.
- **`add_eos`**: Veri seti etiketlerine bir Dizi Sonu (End-Of-Sequence - EOS) belirteci ekler.

### `auth` (Opsiyonel)
- **`hf_token`**: Özel veya erişime kapalı olan (gated - Llama-2/3 gibi) modellere erişim sağlamak için Hugging Face erişim token'ın. Üretim ortamında (production), tokenı yapılandırma dosyasında barındırmak yerine `HUGGINGFACE_TOKEN` çevre değişkenini (environment variable) kullanmak genellikle daha güvenlidir ve o yüzden atlanması tavsiye edilir.

### `evaluation` (Opsiyonel)
Eğitim sonrası otomatik kalite kontrolleri için yapılandırma.
- **`auto_revert`**: (Boolean) `true` ise, nihai kayıp (loss) `max_acceptable_loss` değerini aşarsa checkpoint'leri siler. Varsayılan `false`.
- **`max_acceptable_loss`**: (Float) Değerlendirme kaybına dayalı olarak eğitim çalıştırmasının başarısız sayılması için eşik değer.
- **`baseline_loss`**: (Float) Opsiyonel temel (baseline) değer. Belirtilmezse, ForgeLM eğitime başlamadan önce validasyon setinden otomatik olarak hesaplar.

### `webhook` (Opsiyonel)
ForgeLM, eğitim ilerlemesini takip etmek için harici bir servise JSON verisi gönderebilir.
- **`url`**: Hedef URL (POST isteği).
- **`url_env`**: Alternatif olarak, URL'yi içeren çevre değişkeninin adını belirtin.
- **`notify_on_start`**: (Boolean) Eğitim başladığında bildirim gönder.
- **`notify_on_success`**: (Boolean) Başarıyla tamamlandığında bildirim gönder.
- **`notify_on_failure`**: (Boolean) Hat durumunda bildirim gönder.

#### Webhook Veri Formatı
ForgeLM aşağıdaki yapıya sahip bir JSON gövdesi gönderir:
```json
{
  "status": "started | success | failure",
  "run_name": "model-adi_finetune",
  "message": "Adım açıklaması...",
  "metrics": {
    "loss": 1.25,
    "epoch": 3.0
  }
}
```

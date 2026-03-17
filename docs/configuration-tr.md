# Konfigürasyon Rehberi

ForgeLM tüm yapılandırma için YAML dosyalarını kullanır. Bu sayede, etkileşimli kabuk istemleri (shell prompts) gerektirmeden, deterministik, ve tekrarlanabilir eğitim çalıştırmaları yapılmasına olanak tanınır.

## Örnek Temel Konfigürasyon (`config_template.yaml`)

```yaml
model:
  name_or_path: "meta-llama/Llama-2-7b-hf"
  max_length: 2048
  load_in_4bit: true
  backend: "transformers" # 2-5x hız için "unsloth" seçilebilir

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
  num_train_epochs: 3
  per_device_train_batch_size: 4
  gradient_accumulation_steps: 2
  learning_rate: 2.0e-5
  warmup_ratio: 0.1
  weight_decay: 0.01
  eval_steps: 200
  save_steps: 200
  save_total_limit: 3

data:
  dataset_name_or_path: "sahip_huggingface_dataset_org/dataset_adi"
  shuffle: true
  clean_text: true
  add_eos: true

auth:
  hf_token: "hf_SENIN_GIZLI_TOKENIN"
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
- **`learning_rate`**: AdamW optimize edici (optimizer) için başlangıç öğrenme oranı (learning rate).
- **`per_device_train_batch_size`**: Her GPU çekirdeği/cihazı başına batch boyutu.
- **`gradient_accumulation_steps`**: Geriye dönük/güncelleme adımından önce bilgi biriktirilecek güncelleme adımı sayısı.

### `data`
- **`dataset_name_or_path`**: Hugging face depo kimliği (örn. `timdettmers/openassistant-guanaco`) veya bir JSON/CSV dosyasının yerel yolu.
- **`clean_text`**: Gereksiz tekrarlanan boşlukları temizler.
- **`add_eos`**: Veri seti etiketlerine bir Dizi Sonu (End-Of-Sequence - EOS) belirteci ekler.

### `auth` (Opsiyonel)
- **`hf_token`**: Özel veya erişime kapalı olan (gated - Llama-2/3 gibi) modellere erişim sağlamak için Hugging Face erişim token'ın. Üretim ortamında (production), tokenı yapılandırma dosyasında barındırmak yerine `HUGGINGFACE_TOKEN` çevre değişkenini (environment variable) kullanmak genellikle daha güvenlidir ve o yüzden atlanması tavsiye edilir.

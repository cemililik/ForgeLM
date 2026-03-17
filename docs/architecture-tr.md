# ForgeLM Mimarisi

ForgeLM, modülerlik ve genişletilebilirlik göz önünde bulundurularak tasarlanmıştır. Monolitik bir betik (script) yerine, iş akışı belirgin aşamalara ayrılmıştır.

## Sistem Genel Bakışı

Uygulama, bir CLI giriş noktası ile `forgelm/` altında bir Python paketi olarak yapılandırılmıştır. Özünde bir konfigürasyon yükler, veri setini hazırlar, modeli LoRA ile ilklendirir (initialize eder) ve süreci Trainer'a (eğitmene) devreder.

### Dizin Düzeni

```
ForgeLM/
├── forgelm/               # Temel Python Paketi
│   ├── __init__.py        # Ana giriş noktalarını dışa aktarır
│   ├── cli.py             # Komut Satırı Arayüzü (Argparse)
│   ├── config.py          # Konfigürasyon şeması (Pydantic)
│   ├── data.py            # HF Datasets yükleme ve tokenizasyonu
│   ├── model.py           # HF Transformers ve PEFT model kurulumu
│   ├── trainer.py         # HF Trainer soyutlaması
│   └── utils.py           # Yardımcılar (Auth, Checkpoint Yönetimi)
├── docs/                  # Proje Dokümantasyonu
├── config_template.yaml   # Kullanıcılar için temel konfigürasyon
├── requirements.txt       # Python bağımlılıkları
└── README.md              # Proje kök dokümantasyonu
```

## Bileşen Detayları

### 1. `config.py`
İç içe veri modellerini (`ModelConfig`, `LoraConfigModel`, `TrainingConfig`, `DataConfig`, `AuthConfig`) tanımlamak için `pydantic` kullanıyoruz.
Bu, CLI'ye sağlanan herhangi bir YAML dosyasının anında doğrulanmasını (validate edilmesini) sağlar. Bir kullanıcı geçersiz bir tür sağlarsa (örneğin, `learning_rate` için bir string - metin), Pydantic ağır modeller yüklenmeden önce temiz bir hata fırlatır.

### 2. `data.py`
Bu modül `datasets` kütüphanesi ile arayüz oluşturur. Şunları yapacak mantığı içerir:
- Yerel dosyaları veya Hugging Face hub veri setlerini yüklemek.
- Bir validation (doğrulama) ayrımının mevcut olmamasını garanti altına almak (gerekirse %10'luk bir dilim oluşturarak).
- System (Sistem), User (Kullanıcı) ve Assistant (Asistan) mesajlarını `tokenizer.apply_chat_template()` kullanarak modelin doğal şablonuna göre dinamik olarak şekillendirmek.
- Metin dizilerini tokenize etmek (işaretlemek) ve modelin dolgu metinlerini öğrenmesini önlemek için Labels (Etiketler) dizisindeki dolgu tokenlerini (padding tokens) doğru şekilde maskelemek.

### 3. `model.py`
Bu modül eğitim motorunu kurar. Hem standart Hugging Face `AutoModelForCausalLM` sınıfını hem de yüksek derecede optimize edilmiş `Unsloth` mimarisini destekler. En önemlisi, bir GPU'nun mevcut olup olmadığını algılar ve bellek verimliliği için `bitsandbytes` 4-bit (NF4) kuantizasyonunu (`load_in_4bit=True`) entegre eder. Ardından, kullanıcının LoRA/DoRA konfigürasyonuna göre `peft` kütüphanesi ile sarmalayarak ince ayar (fine-tuning) için hazırlar.

### 4. `trainer.py`
Hugging Face'in `TRL` kütüphanesindeki `SFTTrainer` sınıfı etrafında `ForgeTrainer` sarmalayıcısını (wrapper) sağlar. Konfigürasyon çıktılarını doğrudan `TrainingArguments` sınıfına eşleme işlemlerini (mapping) yönetir ve eğitimi başlatır.

### 5. `utils.py`
Açık tokenleri config'den (konfigürasyondan) eşlemeyi tercih ederek, OS Çevre Değişkenlerine (Environment Variables) geri dönerek ve son olarak `~/.huggingface/token` konumuna geri dönerek Hugging Face Hub `login()` işlevlerini halleder. Ayrıca checkpoint'leri (eğitim ağırlık noktalarını) sıkıştırma/silme mantığını da içerir.

### 6. `cli.py`
Orkestratördür. Bileşenleri sırayla çağırır: Config -> Auth -> Model/Tokenizer -> Data -> Trainer -> Save/Cleanup.

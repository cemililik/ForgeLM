# ForgeLM Kurumsal Vizyon ve Yol Haritası (2026+)

Bu yol haritası, 2026 İyileştirme Önerisi belgesinde belirtilen stratejik vizyona dayanarak, ForgeLM'nin temel bir ince ayar (fine-tuning) betiği olmaktan çıkıp sağlam bir **Kurumsal MLOps İstasyonuna** dönüşmesi için gereken yürütme fazlarını detaylandırır.

---

## Faz 1: Temel SOTA İyileştirmeleri (2026 Standartları)
**Hedef:** Çekirdek eğitim motorunu 2026 başındaki En İleri Teknoloji (SOTA) standartlarına getirmek.
**Tahmini Efor:** Düşük-Orta

### Görevler:
1. **4-Bit QLoRA & DoRA Uygulaması:** `model.py` dosyasını NF4 kuantizasyonu için `BitsAndBytesConfig` kullanacak ve PEFT konfigürasyonuna `use_dora` yeteneği kazandıracak şekilde güncelleyin.
2. **TRL `SFTTrainer` Geçişi:** Otomatik veri paketlemeyi (sequence packing) ve maskelemeyi desteklemek için standart HF `Trainer` sınıfını `SFTTrainer` ile değiştirin.
3. **Sohbet Şablonu (Chat Template) Standardizasyonu:** Çeşitli modern modeller (Llama-3, Mistral) için en kusursuz yapılandırmayı (formatting) sağlamak adına `data.py` içinde manuel metin birleştirme yerine `tokenizer.apply_chat_template()` kullanın.
4. **Unsloth Arka Uç (Backend) Desteği:** Kullanıcıların standart transformers yüklemesini atlayıp eğitimleri 2-5 kat daha hızlı tamamlayabilmelerine olanak tanımak için YAML yapılandırmasına `backend: "unsloth"` seçeneğini ekleyin.
5. **Blackwell (GB10) Optimizasyonu (v1.1):** CUDA 13.0 ortamları için `expandable_segments:True` gibi spesifik bayrakları araştırın ve uygulayın; Blackwell için özel bir `setup_for_blackwell.sh` oluşturun. [Tasarım Dokümanı](design_blackwell_optimized.md)
6. **Veri Seti ve Model Ön Doğrulaması:** Ağırlıkları yüklemeden önce modellerin `safetensors` formatında olduğunu ve veri setlerinin beklenen sohbet/istek-tamamlama (conversational/prompt-completion) şablonlarına uyduğunu doğrulayan kontroller ekleyin.

### İhtiyaçlar:
- `unsloth` kütüphanesinin farklı GPU'larla uyumluluğunun derinlemesine test edilmesi.
- Bu yeni parametrelerin doğrulanmasını (validation) sağlayacak şekilde `config.py` içindeki Pydantic şemalarının güncellenmesi.

---

## Faz 2: Otonom Değerlendirme ve Doğrulama
**Hedef:** Eğitimin körü körüne iyi işleyen eski modellerin üzerine yazılmasını engellemek; otomatik kontrol (check) mekanizmaları uygulamak.
**Tahmini Efor:** Orta

### Görevler:
1. **Otomatik Kıyaslama (Benchmarking):** Eğitim sonrası bir değerlendirme (evaluation) betiği entegre edin (örn., EleutherAI `lm-evaluation-harness` veya Hakim-Olarak-LLM mantığı).
2. **Model Geri Alma (Reversion) Mekanizması:** Yeni eğitilen LoRA adaptörleri doğrulama (validation) setlerinde baz (base) modelden daha kötü puan alırsa, bu adaptörleri otomatik olarak atın ve bir hata mesajı loglayın.
3. **Slack/Teams Webhook Entegrasyonu:** Eğitim işleri başladığında, başarılı olduğunda (metriklerle birlikte) veya çöktüğünde mesaj göndermesi için YAML ayarlarına `notify_webhook` parametresi ekleyin.
4. **Etkileşimli Yapılandırma Sihirbazı (`forgelm --wizard`):** Yeni başlayanların manuel düzenleme yapmadan ilk geçerli `config.yaml` dosyalarını oluşturmalarına yardımcı olacak adım adım bir CLI istemi. [Tasarım Dokümanı](design_wizard_mode.md)

### İhtiyaçlar:
- Sistemi denetlemek amaçlı şirket içine ait, standartlaştırılmış bir gizli test (benchmark) veri seti.
- Webhook URL'leri gibi gizli bilgilerin kodda tutulmaması için Ortam Değişkenleri (Environment variables) yönetimi.

---

## Faz 3: Bulut ve Maliyet Otomasyonu (Kurumsal Devrim)
**Hedef:** Donanım katmanını tamamen ortadan kaldırmak (soyutlamak). Kullanıcının yalnızca makinede yapılandırma ve kendi veri kümesini sunmasına izin vermek, tüm bulut altyapısını kod tabanının kendisinin (ForgeLM'in) kurup yönetmesi.
**Tahmini Efor:** Yüksek

### Görevler:
1. **RunPod / Lambda Labs API Entegrasyonu:** Yeni bir modül (`cloud.py`) oluşturun. Eğitim emri komutunda `target: runpod` değişkeni varsa, işlem ForgeLM API'leri aracılığıyla bir GPU kiralayıp otonom çalışmalıdır.
2. **Ortam Yüklemesi (Environment Bootstrapping):** ForgeLM, kiralayıp çalıştırdığı Linux terminal ortamına gizlice ana veri setini ve YAML configini upload eder (yükler), kendi kendini Linux'a kurar ve eğitim işlemini otomatik kendi kendine başlatır.
3. **Veri Toplama ve Sunucu İmhası (Instance Termination):** Makinedeki saatlik faturayı durdurmak için iş bittikten hemen sonra eğitilen model ağırlıkları güvenli bir şekilde (yerel makineye veya HF Hub'a) indirilir/aktarılır ve ardından otonom şekilde ForgeLM sunucuyu tamamen imha eder (kapatır).

### İhtiyaçlar:
- RunPod / Lambda Labs API anahtarları yönetimi.
- Sağlam bir hata yakalama (Error Handling) kurgusu (Eğitim çöksün veya çökmesin makine açık kalmamalı, script garanti sonlanmalıdır).

---

## Risk ve Fırsat Analizi

### Fırsatlar (Opportunities)
- **Açık Kaynak (Open-Source) MLOps Öncülüğü:** Piyasada, veriler ile donanım kiralama süreçleri arasında tam otomatik ve SOTA uyumlu köprü görevi gören, YAML tabanlı neredeyse hiçbir profesyonel açık kaynak araç yoktur. Bu boşluğu dolduracaktır.
- **Kurumsal Benimseme (Enterprise Adoption):** OpenAI vb. kapalı sistemlere veri gizliliği nedeniyle güvenmeyen Bankalar, Sağlık ve Savunma yapıları "kendi bilgisayarlarında" güvenle SOTA (en ileri teknoloji) eğitim yapabilmek için mutlaka bu tarz araçlara ihtiyaç duyarlar.
- **Pazara Gidiş Gücü:** Unsloth ve QLoRA ekosisteme anında entegre edildiğinde, ForgeLM en üst dilimdeki (%10) GitHub repoları arasına girecektir.

### Riskler (Risks)
- **Ekosistemin Oynaklığı:** AI ekosistemi aşırı dinamiktir. Unsloth, TRL vb. kütüphaneler API'lerinde geriye dönük uyumsuzluklar (breaking changes) çıkarırsa ForgeLM'in bakım maliyeti (maintenance) sürekli yüksek seyredecektir.
- **Aracı ve Donanım Servislerine Bağımlılık:** Faz 3 hedefleri, tamamen 3. parti bulut (RunPod vb.) sağlayıcıların merhametine ve iş modellerine bağlıdır. Bu firmaların API iptali veya katı doğrulama limitleri koyması otonom süreçleri anında kırabilir (crash).
- **Bağımlılık (Dependency) Şişkinliği:** `transformers` yanına `unsloth`, `trl`, bulut SDK'leri eklendikçe `requirements.txt` dosyanız kontrolden çıkabilir. Kullanıcılara aşırı yavaş kurulum yaşatmamak için `pip install forgelm[cloud]` veya `pip install forgelm[unsloth]` gibi tamamen isteğe bağlı modüller (optional dependencies) sunulmalıdır.

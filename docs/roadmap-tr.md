# ForgeLM Kurumsal Yol Haritası (2026+)

Bu yol haritası, [2026 İyileştirme Önerisi](2026_upgrade_proposal-tr.md) belgesinde belirtilen stratejik vizyona ve Mart 2026'da gerçekleştirilen kapsamlı ürün analizine dayanarak, ForgeLM'in temel bir ince ayar aracı olmaktan çıkıp sağlam bir **Kurumsal MLOps İstasyonuna** dönüşmesi için gereken yürütme fazlarını detaylandırır.

> **Yol Gösterici İlke:** Özelliklerden önce güvenilirlik. Her yeni yetenek; test edilmiş, gözlemlenebilir ve iyi belgelenmiş bir temel üzerine inşa edilmelidir.

---

## Güncel Durum Özeti

| Faz | Durum | Tamamlanma |
|-----|-------|------------|
| Faz 1: SOTA İyileştirmeleri | **Tamamlandı** | 6/6 |
| Faz 2: Değerlendirme ve Doğrulama | **Devam Ediyor** | 3/5 |
| Faz 2.5: Güvenilirlik ve Olgunluk | **Planlandı** | 0/8 |
| Faz 3: Kurumsal Entegrasyon | **Planlandı** | 0/6 |
| Faz 4: Ekosistem Büyümesi | **Vizyon** | 0/5 |

---

## Faz 1: Temel SOTA İyileştirmeleri ✅
**Hedef:** Çekirdek eğitim motorunu 2026 başındaki En İleri Teknoloji (SOTA) standartlarına getirmek.
**Durum:** Tamamlandı

### Görevler:
1. [x] **4-Bit QLoRA & DoRA Uygulaması:** `model.py`, NF4 kuantizasyonu için `BitsAndBytesConfig` kullanacak ve PEFT konfigürasyonuna `use_dora` yeteneği kazandıracak şekilde güncellendi.
2. [x] **TRL `SFTTrainer` Geçişi:** Otomatik veri paketlemeyi ve maskelemeyi desteklemek için standart HF `Trainer`, `SFTTrainer` ile değiştirildi.
3. [x] **Sohbet Şablonu Standardizasyonu:** `data.py` artık manuel metin birleştirme yerine `tokenizer.apply_chat_template()` kullanıyor.
4. [x] **Unsloth Arka Uç Desteği:** 2-5 kat daha hızlı eğitim için `backend: "unsloth"` seçeneği YAML'da kullanılabilir durumda.
5. [x] **Blackwell (GB10) Optimizasyonu:** CUDA 13.0 ortamları için özel bayraklar. [Tasarım Dokümanı](design_blackwell_optimized.md)
6. [x] **Veri Seti ve Model Ön Doğrulaması:** Ağırlıkları yüklemeden önce `safetensors` formatı ve veri seti şema kontrolleri eklendi.

---

## Faz 2: Otonom Değerlendirme ve Doğrulama (Devam Ediyor)
**Hedef:** Eğitimin körü körüne iyi modellerin üzerine yazılmasını engellemek; otomatik kontrol mekanizmaları uygulamak.
**Durum:** 5 görevden 3'ü tamamlandı

### Görevler:
1. [/] **Otomatik Kıyaslama (Benchmarking):** `lm-evaluation-harness` veya LLM-as-a-Judge ile eğitim sonrası değerlendirme. *(Geliştirme başladı, entegrasyon bekliyor)*
2. [/] **Model Geri Alma Mekanizması:** Baz modelden kötü puan alan LoRA adaptörlerini otomatik olarak silme. *(Temel mantık `trainer.py`'de mevcut, uç durumlar güçlendirilmeli)*
3. [x] **Slack/Teams Webhook Entegrasyonu:** YAML config'inde `webhook` bölümü; başlatma/başarı/hata durumlarında yapılandırılmış JSON payload gönderiyor.
4. [ ] **Etkileşimli Yapılandırma Sihirbazı (`forgelm --wizard`):** Geçerli `config.yaml` oluşturmak için adım adım CLI. [Tasarım Dokümanı](design_wizard_mode.md) *(Faz 3'e ertelendi — güvenilirlik çalışması öncelikli)*
5. [x] **Otomatik Çalışma Zamanı Testi:** `tests/runtime_smoke.py` ile CPU/CI ortamlarında tam eğitim döngüsü doğrulaması.

---

## Faz 2.5: Güvenilirlik ve Üretime Hazırlık (YENİ — En Yüksek Öncelik)
**Hedef:** Mevcut kod tabanını üretim kullanımı için sağlamlaştırmak. Yeni özellik yok — yalnızca kararlılık, gözlemlenebilirlik ve güvenlik iyileştirmeleri.
**Tahmini Efor:** Orta (2-3 hafta)

> **Gerekçe:** Mart 2026 ürün analizi kritik güvenilirlik boşlukları tespit etti — sessiz istisna yutma, yetersiz test kapsamı ve eksik gözlemlenebilirlik. Yeni özellik eklemeden önce bunlar çözülmelidir. Test edilmemiş bir temel üzerine inşa etmek teknik borcu katlanarak artırır.

### Görevler:
1. [ ] **Yapılandırılmış Loglama (Structured Logging):** Tüm `print()` ifadelerini Python `logging` modülüyle değiştirin. Yapılandırılabilir log seviyeleri (`--log-level`) ve bulut/konteyner ortamları için JSON log formatı seçeneği ekleyin.
2. [ ] **Sessiz Hata Yutmanın Ortadan Kaldırılması:** Kod tabanındaki tüm `except Exception:` bloklarını denetleyin ve düzeltin. Yakalanan her istisna bağlamıyla birlikte loglanmalıdır. Kritik hatalar (veri biçimlendirme geri dönüşü, adaptör devre dışı bırakma başarısızlığı) kullanıcıya görünür uyarılar üretmelidir.
3. [ ] **Test Kapsamının Genişletilmesi:** Her çekirdek modül için birim testler ekleyin:
   - `config.py`: Doğrulama uç durumları, çelişkili yapılandırma tespiti
   - `data.py`: Format algılama, chat template geri dönüşü, boş veri seti işleme
   - `model.py`: Arka uç seçimi, kuantizasyon ayarı çözümlemesi
   - `webhook.py`: Payload formatı, ortam değişkeni çözümlemesi, zaman aşımı
4. [ ] **Bağımlılık Sürüm Sabitleme:** `pyproject.toml`'daki kritik bağımlılıklar (`trl`, `peft`, `transformers`, `unsloth`) için üst sınır sürüm kısıtlamaları ekleyin. Uyumluluk matrisi belgesi oluşturun.
5. [ ] **Güvenlik Sağlamlaştırma:** `trust_remote_code` parametresini YAML üzerinden yapılandırılabilir hale getirin (varsayılan: `false`). Etkinleştirildiğinde uyarı gösterin. Bu, kurumsal benimseme için engelleyici bir konudur.
6. [ ] **CLI Olgunluğu:**
   - `--version` bayrağı
   - `--dry-run` / `--validate-only` modu (config'i ayrıştır, model/veri seti erişimini doğrula, eğitim yapmadan çık)
   - Anlamlı çıkış kodları: `0` başarı, `1` config hatası, `2` eğitim hatası, `3` değerlendirme hatası
7. [ ] **Hata Teşhislerinin İyileştirilmesi:** CLI çıktısında hata türlerini ayırt edin. Config doğrulama hataları tam alanı ve beklenen tipi göstermelidir. Eğitim hataları donanım bağlamını (GPU modeli, VRAM, CUDA sürümü) içermelidir.
8. [ ] **CI/CD Pipeline Güçlendirmesi:** GitHub Actions'a eklemeler:
   - Kapsam raporlamalı birim test yürütmesi
   - Bağımlılık güvenlik açığı taraması
   - Config şablonu doğrulama testi

### Başarı Kriterleri:
- Kod tabanında sıfır sessiz hata
- Çekirdek modüllerde >%80 test kapsamı
- Tüm istisnalar eyleme dönüştürülebilir log mesajları üretir
- `--dry-run` GPU olmadan tam pipeline'ı doğrular

---

## Faz 3: Kurumsal Entegrasyon
**Hedef:** ForgeLM'i config-tabanlı, CI/CD-uyumlu, şirket içi (on-premise) LLM ince ayarı için standart araç haline getirmek.
**Tahmini Efor:** Yüksek (1-3 ay)

> **Stratejik Karar:** Orijinal Faz 3, doğrudan RunPod/Lambda Labs API entegrasyonu öneriyordu. Analiz sonucunda bu yaklaşım **öncelik sırası düşürüldü** ve yerine konteyner tabanlı strateji benimsendi. Doğrudan bulut API entegrasyonu sürdürülemez bakım yükü, 3. parti API bağımlılık riski yaratır ve ForgeLM'in temel değer önerisini sulandırır. Bunun yerine, taşınabilir Docker imajları sunarak altyapı yönetimini kullanıcının mevcut araçlarına (Terraform, Pulumi, Kubernetes) bırakıyoruz.

### Görevler:
1. [ ] **Etkileşimli Yapılandırma Sihirbazı (`forgelm --wizard`):** *(Faz 2'den taşındı)* Donanım algılama, model seçimi, strateji önerisi, YAML üretimi. [Tasarım Dokümanı](design_wizard_mode.md)
2. [ ] **Otomatik Kıyaslamanın Tamamlanması:** Yapılandırılabilir görev setleriyle tam `lm-evaluation-harness` entegrasyonu. Sonuçlar webhook bildirimlerine ve son çıktıya dahil edilir.
3. [ ] **Docker İmajı ve Konteyner Desteği:** Resmi `Dockerfile` ve `docker-compose.yaml` ile tek komutla eğitim: `docker run forgelm --config job.yaml`. CUDA, Unsloth ve değerlendirme bağımlılıkları yüklenmiş hazır imajlar.
4. [ ] **JSON Çıktı Modu (`--output-format json`):** Tüm pipeline aşamaları için makine tarafından okunabilir yapılandırılmış çıktı. CI/CD sistemleri, panolar ve orkestratörlerle programatik entegrasyonu mümkün kılar.
5. [ ] **Çevrimdışı / İzole (Air-Gapped) Mod:** İnternet erişimi olmadan tam çalışma. Yerel model yükleme, yalnızca yerel veri seti, HF Hub çağrısı yok. Savunma/sağlık/bankacılık dağıtımları için kritik.
6. [ ] **Kontrol Noktasından Devam Etme (`--resume`):** Kesintiden sonra son kaydedilen kontrol noktasından eğitime devam. Ön alımlı (preemptible) örneklerdeki uzun süreli işler için gerekli.

### İhtiyaçlar:
- Minimal imaj boyutu için Docker çok aşamalı (multi-stage) yapılar
- Çevrimdışı modun tüm kod yollarında kapsamlı test edilmesi
- Dokümantasyon: GitHub Actions, GitLab CI örnekleriyle CI/CD entegrasyon rehberi

---

## Faz 4: Ekosistem Büyümesi (Vizyon)
**Hedef:** Basitliği koruyarak ForgeLM'in yeteneklerini ileri düzey kullanım senaryoları için genişletmek.
**Tahmini Efor:** Süregelen

### Görevler:
1. [ ] **ORPO Trainer:** `chosen`/`rejected` veri setleriyle tek aşamalı tercih hizalaması. Ayrı SFT + DPO aşamalarına olan ihtiyacı ortadan kaldırır.
2. [ ] **Deney Takip Entegrasyonu:** Metrik loglama, model karşılaştırma ve hiperparametre arama görselleştirmesi için isteğe bağlı W&B / MLflow entegrasyonu.
3. [ ] **Çoklu Veri Seti Eğitimi:** Yapılandırılabilir karışım oranlarıyla tek eğitim çalışmasında birden fazla JSONL/HF veri seti desteği.
4. [ ] **Otomatik Model Kartı Üretimi:** Eğitim yapılandırması, metrikler, veri seti bilgisi ve değerlendirme sonuçlarıyla HF uyumlu model kartları oluşturma.
5. [ ] **DeepSpeed / FSDP Desteği:** Daha büyük modeller (30B+ parametre) için birden fazla GPU'da dağıtık eğitim.

### İhtiyaçlar:
- Her özellik tamamen isteğe bağlı olmalıdır (yeni zorunlu bağımlılık yok)
- Modüler kurulum: `pip install forgelm[tracking]`, `pip install forgelm[distributed]`

---

## Risk Matrisi

### Yüksek Ciddiyet
| Risk | Etki | Olasılık | Azaltma Stratejisi |
|------|------|----------|---------------------|
| **Bağımlılık Kırıcı Değişiklikleri** (TRL, PEFT, Unsloth) | Eğitim pipeline'ı uyarısız bozulur | Yüksek | Üst sınırlı sürüm sabitleme, en son bağımlılıklara karşı gece CI yapıları, uyumluluk matrisi |
| **Üretimde Sessiz Hatalar** | Yanlış biçimlendirilmiş veriyle eğitilen modeller, algılanmayan kalite düşüşü | Yüksek | Faz 2.5 tüm sessiz istisna yönetimini ortadan kaldırır |
| **Güvenlik: `trust_remote_code=True`** | Güvenilmeyen model depolarından rastgele kod çalıştırma | Orta | Yapılandırılabilir hale getir, varsayılanı `false` yap, riski belgele |

### Orta Ciddiyet
| Risk | Etki | Olasılık | Azaltma Stratejisi |
|------|------|----------|---------------------|
| **Kapsam Kayması** (bulut otomasyonu, çok fazla özellik) | Bakım yükü kapasiteyi aşar, çekirdek kalite düşer | Orta | Sıkı faz kapılama — Faz 2.5 kriterleri karşılanmadan Faz 3 çalışması yapılmaz |
| **Ekosistem Metalaşması** (Axolotl, LLaMA-Factory) | Rakip araçlar benzer özellikler ekler | Orta | CI/CD-uyumlu + kurumsal konumlanmaya odaklan |
| **GPU/CUDA Sürüm Parçalanması** | Farklı CUDA sürümlerindeki kullanıcılar uyumsuzlukla karşılaşır | Orta | Docker imajları CUDA sürümlerini sabitler, uyumluluk matrisi |

### Düşük Ciddiyet
| Risk | Etki | Olasılık | Azaltma Stratejisi |
|------|------|----------|---------------------|
| **Blackwell'e özgü kodun eskimesi** | Mimari yaygınlaşmazsa boşa efor | Düşük | İsteğe bağlı tut, algıla-ve-etkinleştir deseni |
| **HF Hub API değişiklikleri** | Veri seti/model yükleme bozulur | Düşük | Arayüz arkasına soyutla, `huggingface_hub` sürümünü sabitle |

---

## Fırsat Analizi

### Anlık Fırsatlar
1. **CI/CD Pipeline Entegrasyonu** — ForgeLM'in YAML tabanlı tasarımı `git push → eğit → değerlendir → bildir` iş akışları için benzersiz şekilde uygundur. Bu akışı gösteren bir demo/tutorial GitHub benimsenmesini önemli ölçüde artırır.
2. **Şirket İçi / İzole (Air-Gapped) Pazar** — Bankalar, sağlık, savunma verisini dışarı gönderemez. ForgeLM + Docker imajı = sıfır bulut bağımlılığıyla eksiksiz şirket içi çözüm.

### Orta Vadeli Fırsatlar
3. **Kurumsal Danışmanlık ve Destek** — ForgeLM'i üretimde benimseyen kuruluşlar özel entegrasyonlar, eğitim ve destek sözleşmelerine ihtiyaç duyacaktır.
4. **Model Kayıt Defteri Entegrasyonu** — Karşılaştırma panolarıyla sürümlü model depolama, eğitim ve dağıtım arasındaki boşluğu kapatır.

### Uzun Vadeli Fırsatlar
5. **Yönetilen ForgeLM Servisi** — Kullanıcıların veri + config yükleyip eğitilmiş model aldığı SaaS teklifi. Aynı açık kaynak çekirdek üzerine inşa edilir.
6. **Eğitim Pazaryeri** — Yaygın kullanım senaryoları (müşteri destek botu, hukuki belge analizci, kod asistanı) için hazır config şablonları.

---

## Rekabet Konumlandırması

| Rakip | ForgeLM Avantajı | ForgeLM Dezavantajı |
|-------|-------------------|---------------------|
| **Axolotl** | Daha basit config, daha kolay başlangıç, CI/CD-uyumlu | Axolotl daha fazla model mimarisi ve eğitim yöntemi destekliyor |
| **LLaMA-Factory** | Bildirimsel YAML vs GUI bağımlılığı, otomasyon için daha iyi | LLaMA-Factory'nin teknik olmayan kullanıcılar için web arayüzü var |
| **Unsloth (doğrudan)** | Çoklu arka uç geri dönüşü, değerlendirme, webhook, kurumsal özellikler | Unsloth doğrudan kullanımda daha hızlı |
| **AutoTrain** | Açık kaynak, şirket içi, tam kontrol, satıcı kilidi yok | AutoTrain yeni başlayanlar için daha kullanıcı dostu |
| **Özel Scriptler** | Doğrulanmış pipeline, config yönetimi, kontrol noktası yönetimi | Özel scriptler sınırsız esneklik sunar |

**ForgeLM'in niş'i net:** Config-tabanlı, CI/CD-uyumlu, şirket içi LLM ince ayarı. Bu niş'i sahiplenin — her şey olmaya çalışmayın.

---

## Karar Günlüğü

| Tarih | Karar | Gerekçe |
|-------|-------|---------|
| 2026-03-23 | Yeni özelliklerden önce Faz 2.5 (Güvenilirlik) eklendi | Ürün analizi kritik sessiz hata ve test kapsamı boşlukları ortaya koydu |
| 2026-03-23 | Doğrudan bulut API entegrasyonu (orijinal Faz 3) öncelik sırası düşürüldü | Sürdürülemez bakım yükü, 3. parti bağımlılık riski, kapsam kayması |
| 2026-03-23 | Docker tabanlı dağıtım stratejisi benimsendi | Taşınabilir, kullanıcı kontrollü altyapı, ForgeLM ekibi için minimal bakım |
| 2026-03-23 | Sihirbaz modu Faz 2'den Faz 3'e taşındı | Güvenilirlik çalışması UX iyileştirmelerinden önce gelir |
| 2026-03-23 | `trust_remote_code` kurumsal benimseme engelleyici olarak işaretlendi | Düzenlemeye tabi sektörlerle uyumsuz güvenlik riski |

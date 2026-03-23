# ForgeLM Ürün Stratejisi

> **Son Güncelleme:** 2026-03-23
> **Amaç:** ForgeLM'in pazar konumunu, hedef kullanıcılarını ve stratejik yönünü tanımlamak.

---

## Misyon

ForgeLM, kurumsal LLM ince ayarını (fine-tuning) config-tabanlı, CI/CD-uyumlu bir yaklaşımla **basit, tekrarlanabilir ve güvenli** kılar — bulut, şirket içi veya izole (air-gapped) ortamlarda çalışır.

---

## Hedef Kullanıcılar

### Birincil: MLOps / Veri Mühendisleri
- Otomatik eğitim pipeline'ları kurar (`git push → eğit → değerlendir → dağıt`)
- Jupyter Notebook değil, deterministik, YAML tabanlı iş akışlarına ihtiyaç duyar
- CI/CD ortamlarında (GitHub Actions, GitLab CI, Jenkins) çalışır
- Yapılandırılmış çıktıyla sessiz, başsız (headless) yürütme gerektirir

### İkincil: Düzenlemeye Tabi Sektörlerdeki AI/ML Mühendisleri
- Bankalar, sağlık, savunma — verisini harici API'lere gönderemez
- Tam denetim izleriyle şirket içi / izole çalışmaya ihtiyaç duyar
- Güvenlik bilincinde varsayılanlar gerektirir (`trust_remote_code: false`)
- Açık kaynak şeffaflığına ve tekrarlanabilirliğe değer verir

### Üçüncül: Bağımsız Araştırmacılar ve Geliştiriciler
- Derin altyapı bilgisi olmadan model ince ayarı yapmak ister
- Mantıklı varsayılanlar ve hızlı başlangıç rehberlerine ihtiyaç duyar
- Sihirbaz modu ve örnek yapılandırmalardan faydalanır

---

## Temel Değer Önerisi

**"YAML gir, ince ayarlı model çık."**

ForgeLM rakiplerinden üç sütunla ayrışır:

### 1. Config-Tabanlı (Bildirimsel Eğitim)
- Tüm eğitim çalışmaları tek bir YAML dosyasında tanımlanır
- Son kullanıcıdan Python kodu gerekmez
- Deterministik, tekrarlanabilir, sürüm kontrollü
- CI/CD pipeline'ları ve GitOps iş akışlarına doğal uyum

### 2. Kurumsal Hazırlık
- Eğitim yaşam döngüsü olayları için webhook bildirimleri
- Otomatik kalite kapıları (değerlendirme, otomatik geri alma)
- Pipeline orkestrasyonu için anlamlı çıkış kodları
- Gözlemlenebilirlik platformları için yapılandırılmış loglama

### 3. Her Yerde Çalışır
- Evrensel geri dönüş olarak standart Transformers arka ucu
- Yüksek performanslı ortamlar için Unsloth arka ucu
- Taşınabilir dağıtım için Docker imajları
- Düzenlemeye tabi sektörler için izole (air-gapped) mod

---

## ForgeLM Ne DEĞİLDİR

Odağı korumak adına, ForgeLM şunlardan kaçınır:

- **GUI/Web uygulaması değildir.** Config dosyaları arayüzdür. GUI isteyen kullanıcılar LLaMA-Factory veya AutoTrain kullanmalıdır.
- **Bulut altyapı sağlayıcısı değildir.** ForgeLM model eğitir — bulut örneklerini (instances) yönetmez. Kullanıcılar kendi hesaplama kaynaklarını getirir.
- **Model sunum (serving) platformu değildir.** ForgeLM eğitilmiş adaptör/model çıktısı verir. Dağıtım vLLM, TGI veya benzeri araçlarla yapılır.
- **Genel ML eğitim çerçevesi değildir.** ForgeLM özellikle LoRA/QLoRA ile LLM ince ayarı içindir, bilgisayarlı görü veya klasik ML için değil.

---

## Stratejik Kararlar

### Doğrudan Bulut API Yerine Docker
**Karar:** RunPod/Lambda Labs API'leriyle doğrudan entegrasyon yerine resmi Docker imajları sunulacak.
**Gerekçe:** Doğrudan bulut entegrasyonu sürdürülemez bakım yükü yaratır, 3. parti API bağımlılık riski doğurur ve kapsamı temel yetkinliğin ötesine taşır. Docker imajları taşınabilir, kullanıcı kontrollü ve herhangi bir bulut sağlayıcı veya şirket içi altyapıyla çalışır.

### Özelliklerden Önce Güvenilirlik
**Karar:** Yeni özellik geliştirmesinden önce Faz 2.5 (güvenilirlik sağlamlaştırma) eklendi.
**Gerekçe:** Sessiz hatalar, yetersiz test kapsamı ve print tabanlı loglama üretim engelleyicileridir. Güvenilir olmayan temeller üzerine inşa edilen yeni özellikler teknik borcu katlanarak artırır.

### Modüler Bağımlılıklar
**Karar:** Çekirdek dışı tüm özellikler isteğe bağlıdır (`pip install forgelm[unsloth]`, `forgelm[eval]` vb.).
**Gerekçe:** Temel kurulum hafif kalmalıdır. Kullanıcılar yalnızca ihtiyaç duyduklarını kurmalıdır. Bu, bağımlılık çakışmalarını önler ve saldırı yüzeyini azaltır.

---

## Başarı Metrikleri

### Kısa Vade (6 ay)
- Üretim pipeline'larında sıfır sessiz hata
- Çekirdek modüllerde >%80 test kapsamı
- `--dry-run` GPU olmadan tam pipeline'ı doğrular
- Docker imajı hazır ve belgelenmiş

### Orta Vade (12 ay)
- 3+ kurumsal ekip ForgeLM'i üretim CI/CD pipeline'larında kullanıyor
- Tam `lm-evaluation-harness` entegrasyonu
- İzole ortamlarda doğrulanmış air-gapped mod
- İlk 3 platform için yayınlanmış CI/CD entegrasyon rehberleri

### Uzun Vade (24 ay)
- Config-tabanlı LLM ince ayarı için standart açık kaynak araç olarak tanınma
- Topluluk katkılı yaygın kullanım senaryoları için config şablonları
- ORPO/tercih öğrenme desteği
- Dağıtık eğitim (DeepSpeed/FSDP) mevcut

---

## Dokümantasyon Haritası

| Belge | Amaç |
|-------|------|
| [README.md](../README.md) | Proje genel bakışı ve hızlı başlangıç |
| [Mimari](architecture-tr.md) | Sistem tasarımı ve bileşen detayları |
| [Yapılandırma Rehberi](configuration-tr.md) | YAML parametre referansı |
| [Kullanım Rehberi](usage-tr.md) | Eğitim nasıl çalıştırılır |
| [Veri Hazırlama](data_preparation-tr.md) | Veri seti format gereksinimleri |
| [Yol Haritası](roadmap-tr.md) | Faz bazlı yürütme planı |
| [2026 İyileştirme Önerisi](2026_upgrade_proposal-tr.md) | SOTA teknik benimseme gerekçesi |
| [Ürün Stratejisi](product_strategy-tr.md) | Pazar konumu ve stratejik yön (bu belge) |
| [Blackwell Tasarımı](design_blackwell_optimized.md) | GB10 optimizasyon tasarımı |
| [Sihirbaz Modu Tasarımı](design_wizard_mode.md) | Etkileşimli yapılandırma sihirbazı tasarımı |

Tüm belgeler İngilizce (`*.md`) ve Türkçe (`*-tr.md`) olarak mevcuttur.

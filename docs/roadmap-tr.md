# ForgeLM Kurumsal Yol Haritası (2026+)

Bu yol haritası, [2026 İyileştirme Önerisi](2026_upgrade_proposal-tr.md), kapsamlı ürün analizi (Mart 2026) ve Axolotl, LLaMA-Factory, Unsloth, TRL ve torchtune'a karşı rekabet araştırmasına dayanarak, ForgeLM'in standart **config-tabanlı, kurumsal düzeyde LLM ince ayar platformuna** dönüşmesi için yürütme fazlarını detaylandırır.

> **Yol Gösterici İlkeler:**
> 1. Özelliklerden önce güvenilirlik.
> 2. Özellik eşitliği yerine kurumsal farklılaşma.
> 3. Her yeni yetenek config-tabanlı, test edilebilir ve isteğe bağlı olmalı.

---

## Güncel Durum Özeti

| Faz | Durum | Tamamlanma |
|-----|-------|------------|
| Faz 1: SOTA İyileştirmeleri | **Tamamlandı** | 6/6 |
| Faz 2: Değerlendirme ve Doğrulama | **Tamamlandı** | 5/5 |
| Faz 2.5: Güvenilirlik ve Olgunluk | **Tamamlandı** | 8/8 |
| Faz 3: Kurumsal Entegrasyon | **Tamamlandı** | 6/6 |
| Faz 4: Ekosistem Büyümesi | **Tamamlandı** | 5/5 |
| Faz 5: Hizalama ve Post-Training Stack | **Tamamlandı** | 5/5 |
| Faz 5.5: Teknik Borç Çözümü | **Tamamlandı** | 7/7 |
| Faz 6: Kurumsal Güven ve Uyumluluk | **Tamamlandı** | 5/5 |
| Faz 7: Yeni Nesil Model Desteği | **Tamamlandı** | 5/5 |
| Faz 8: EU AI Act Derin Uyumluluk | **Planlandı** | 0/10 |

---

## Faz 1–4: Tamamlandı ✅

<details>
<summary>Tamamlanan fazları genişletmek için tıklayın</summary>

### Faz 1: Temel SOTA İyileştirmeleri ✅ (6/6)
4-Bit QLoRA & DoRA, TRL SFTTrainer, Chat Templates, Unsloth Backend, Blackwell Optimizasyonu, Ön Doğrulama.

### Faz 2: Otonom Değerlendirme ve Doğrulama ✅ (5/5)
Otomatik Kıyaslama (lm-eval-harness), Model Geri Alma, Webhook Entegrasyonu, Sihirbaz Modu, Çalışma Zamanı Testleri.

### Faz 2.5: Güvenilirlik ve Üretime Hazırlık ✅ (8/8)
Yapılandırılmış Loglama, Sessiz Hata Giderme, Test Kapsamı, Bağımlılık Sabitleme, Güvenlik, CLI Olgunluğu, Hata Teşhisleri, CI/CD.

### Faz 3: Kurumsal Entegrasyon ✅ (6/6)
Sihirbaz Modu, Kıyaslama, Docker/Compose, JSON Çıktı, Offline/Air-Gapped, Checkpoint Resume.

### Faz 4: Ekosistem Büyümesi ✅ (5/5)
ORPO Trainer, W&B/MLflow/TensorBoard, Çoklu Veri Seti, Model Kartı Üretimi, DeepSpeed/FSDP.

</details>

---

## Faz 5: Hizalama ve Post-Training Stack
**Hedef:** Tam modern post-training pipeline'ını sağlamak: SFT → Tercih Optimizasyonu → Akıl Yürütme RL. Rakiplere karşı en kritik açık — tüm büyük araçlar (Axolotl, TRL, Unsloth, LLaMA-Factory) DPO ve GRPO destekliyor.
**Tahmini Efor:** Yüksek (2-3 ay)
**Öncelik:** Kritik — pazar beklentisi

> **Bağlam:** 2026 post-training ortamı modüler bir stack'e oturdu: önce SFT, sonra tercih hizalaması (DPO/SimPO/KTO), isteğe bağlı olarak akıl yürütme RL (GRPO/DAPO). Tek başına ORPO yetersiz — kurumsal kullanıcılar tam menüye ihtiyaç duyuyor. Araştırma (arxiv 2603.19335) algoritma sıralamalarının ölçeğe bağlı olduğunu gösteriyor, bu yüzden kullanıcılar seçebilmeli.

### Görevler:
1. [ ] **DPO Trainer:** Direct Preference Optimization — temel tercih yöntemi. `trainer_type: "dpo"`. `chosen`/`rejected` veri formatı gerektirir.
2. [ ] **SimPO Trainer:** Simple Preference Optimization — referans model gerektirmez, DPO'dan daha düşük bellek. 7B ölçeğinde DPO'ya göre AlpacaEval 2'de +6.4 puan. `trainer_type: "simpo"`.
3. [ ] **KTO Trainer:** Kahneman-Tversky Optimization — eşleştirilmiş tercihler yerine ikili beğenme/beğenmeme geri bildirimi kullanır. Üretim veri toplama için daha pratik. `trainer_type: "kto"`.
4. [ ] **GRPO Trainer:** Group Relative Policy Optimization — DeepSeek-R1'in arkasındaki yöntem. Eğitim sırasında yanıt üreten ve puanlayan çevrimiçi RL. Akıl yürütme/matematik/kod ince ayarı için kritik. `trainer_type: "grpo"`.
5. [ ] **Hizalama Stratejisi Otomatik Seçimi:** Veri seti formatına göre (eşleştirilmiş tercihler vs ikili geri bildirim vs doğrulanabilir ödüller) uygun trainer'ı otomatik önerme veya seçme. `--wizard` ve `--dry-run`'da gösterilir.

### Config Örneği:
```yaml
training:
  trainer_type: "dpo"  # "sft", "orpo", "dpo", "simpo", "kto", "grpo"
  dpo_beta: 0.1
  grpo_num_generations: 4
```

---

## Faz 6: Kurumsal Güven ve Uyumluluk
**Hedef:** ForgeLM'i en güvenli, en denetlenebilir ince ayar aracı yapmak — hiçbir rakibin sunmadığı benzersiz bir farklılaştırıcı. Hedef: EU AI Act uyumluluğu (Ağustos 2026 tam yürürlük) ve düzenlemeye tabi sektörlerin benimsemesi.
**Tahmini Efor:** Yüksek (2-3 ay)
**Öncelik:** Yüksek — farklılaştırıcı, hiçbir rakip bunu iyi yapmıyor

> **Bağlam:** İnce ayar, hizalanmış modellerin güvenliğini kanıtlanmış şekilde bozuyor — zararsız verilerle bile (birden fazla makale, Microsoft Şubat 2026). EU AI Act yüksek riskli AI sistemleri için makinece okunabilir denetim izleri, risk sınıflandırması ve sürekli izleme gerektiriyor. Bugün hiçbir ince ayar aracı bunu eğitim döngüsünde ele almıyor. ForgeLM bu alanı sahiplenebilir.

### Görevler:
1. [ ] **Post-Training Güvenlik Değerlendirmesi:** Eğitim sonrası model çıktılarında güvenlik sınıflandırıcıları (Llama Guard, ShieldGemma) çalıştırma. İnce ayar öncesi/sonrası güvenlik puanlarını karşılaştırma. Eşik aşılırsa otomatik geri alma.
2. [ ] **LLM-Hakim Değerlendirme Pipeline'ı:** Güçlü bir LLM (GPT-4, Claude, yerel hakim model) kullanarak ince ayarlı model çıktılarını kalite, faydalılık ve talimat takibi açısından puanlama. İnsan değerlendirmesinden 500x-5000x ucuz.
3. [ ] **GPU Maliyet ve Kaynak Takibi:** Çalışma başına metrikler: GPU-saat, peak VRAM, toplam eğitim süresi, tahmini bulut maliyeti. JSON çıktısı, webhook ve model kartına dahil.
4. [ ] **EU AI Act Uyumluluk Dışa Aktarımı:** Model kartının yanında makinece okunabilir uyumluluk belgesi üretme. İçerir: eğitim verisi kaynağı, model soy ağacı, değerlendirme sonuçları, risk sınıflandırması, zaman damgalı denetim izi.
5. [ ] **Eğitim Verisi Kaynak Takibi:** Veri seti parmak izleri (hash, boyut, şema, kaynak URL), uygulanan ön işleme adımları, bölüm başına örnek sayıları. Model kartı ve uyumluluk dışa aktarımında saklanır.

---

## Faz 7: Yeni Nesil Model Desteği
**Hedef:** 2026 ortası ve sonrasını tanımlayan model mimarileri ve eğitim paradigmalarını desteklemek: MoE, multimodal, uzun bağlam ve model birleştirme.
**Tahmini Efor:** Çok Yüksek (3-6 ay, süregelen)
**Öncelik:** Yüksek — pazar uyumu

> **Bağlam:** Model ortamı değişti. Qwen3, Mixtral ve DeepSeek-V3 hep MoE mimarileri. Görsel-dil modelleri (Qwen2.5-VL, Llama-3.2-Vision) artık ana akım. Bağlam pencereleri 128K token'ı aşıyor. Model birleştirme (TIES, DARE) standart bir post-training iş akışı. ForgeLM'in ilgili kalması için bunları desteklemesi gerekiyor.

### Görevler:
1. [ ] **MoE (Mixture of Experts) İnce Ayarı:** MoE modellerinin (Qwen3-30B-A3B, Mixtral, DeepSeek) LoRA/QLoRA ince ayarı. VRAM azaltma için uzman-farkında kuantizasyon. MoE mimarisini otomatik algılama.
2. [ ] **Multimodal VLM İnce Ayarı:** Görsel-dil modeli ince ayar desteği (Qwen2.5-VL, Llama-3.2-Vision). Otomatik işlemci yönetimi ile görsel+metin veri seti formatı.
3. [ ] **Model Birleştirme Entegrasyonu:** mergekit entegrasyonu ile eğitim sonrası model birleştirme. TIES-Merging, DARE, SLERP veya doğrusal interpolasyon ile birden fazla LoRA adaptörü veya ince ayarlı modeli birleştirme.
4. [ ] **Gelişmiş PEFT Yöntemleri:** LoRA/DoRA ötesinde yeni parametre-verimli yöntemler:
   - **PiSSA:** Principal component başlatma — daha hızlı yakınsama
   - **rsLoRA:** Yüksek rank'larda (r>64) önerilen
   - **GaLore:** Gradient düşük rank projeksiyonu — bellek verimli tam parametre benzeri eğitim
5. [ ] **Notebook ve Colab Şablonları:** Yaygın kullanım senaryoları için hazır Jupyter notebook'ları: müşteri destek botu, kod asistanı, alan-spesifik S&C, çok dilli ince ayar. Tek tıkla Colab başlatma.

---

## Risk Matrisi

### Yüksek Ciddiyet
| Risk | Etki | Olasılık | Azaltma Stratejisi |
|------|------|----------|---------------------|
| **Bağımlılık Kırıcı Değişiklikleri** (TRL, PEFT, Unsloth) | Eğitim pipeline'ı uyarısız bozulur | Yüksek | Sürüm sabitleme, gece CI yapıları, uyumluluk matrisi |
| **EU AI Act Uyumsuzluğu** (Ağustos 2026 son tarih) | Kurumsal müşteriler yüksek riskli AI için ForgeLM'i benimseyemez | Orta | Faz 6 uyumluluk dışa aktarımı son tarihten önce |
| **İnce Ayardan Güvenlik Bozulması** | İnce ayarlı modeller hizalamayı kaybeder, kurumsal sorumluluk | Yüksek | Faz 6 güvenlik değerlendirme pipeline'ı, güvenlik gerilemesinde otomatik geri alma |
| **Hizalama Yöntemi Kilitlenmesi** | ForgeLM yalnızca ORPO desteklerken pazar DPO/GRPO talep eder | Yüksek | Faz 5 en yüksek öncelik |

### Orta Ciddiyet
| Risk | Etki | Olasılık | Azaltma Stratejisi |
|------|------|----------|---------------------|
| **MoE/VLM Mimari Kayması** | ForgeLM baskın model mimarilerini eğitemez | Orta | Faz 7; PEFT kütüphanesi MoE desteğini izle |
| **Kapsam Kayması** | Bakım yükü kapasiteyi aşar, çekirdek kalite düşer | Orta | Sıkı faz kapılama, TRL'nin mevcut trainer'larını kullan |
| **Ekosistem Metalaşması** | Rakip araçlar benzer kurumsal özellikler ekler | Orta | Güvenlik + uyumluluk farklılaşmasına odaklan |

---

## Fırsat Analizi

### Anlık Fırsatlar
1. **Hizalama Stack (Faz 5)** — DPO+GRPO desteği en kritik rekabet açığını kapatır.
2. **Güvenlik-Özellik (Faz 6)** — Hiçbir rakip güvenlik değerlendirmesini eğitim pipeline'ına entegre etmiyor. "LLM ince ayarının en güvenli yolu" konumlandırması.

### Orta Vadeli Fırsatlar
3. **EU AI Act Uyumluluğu** — Ağustos 2026 son tarihi acil talep yaratır. Uyumluluk belgeleri üreten tek araç olmak güçlü bir kurumsal satış argümanı.
4. **Maliyet Şeffaflığı** — Çalışma başına GPU maliyet takibi, kurumsal bütçe planlamasını mümkün kılar.

### Uzun Vadeli Fırsatlar
5. **Yönetilen ForgeLM Servisi** — SaaS: veri + config yükle → eğitilmiş model + uyumluluk belgeleri al.
6. **Sentetik Veri Pipeline'ı** — Config-tabanlı öğretmen model distillasyonu.
7. **Eğitim Pazaryeri** — Topluluk katkılı config şablonları.

---

## Rekabet Konumlandırması (Güncel — Mart 2026)

| Rakip | Yıldız | ForgeLM Avantajı | ForgeLM Açığı |
|-------|--------|-------------------|---------------|
| **LLaMA-Factory** | ~55-68K | CI/CD-native, güvenlik eval, uyumluluk | Web UI, 100+ model, GaLore/PiSSA, VLM |
| **Unsloth** | ~54-56K | Kurumsal özellikler, çoklu trainer, güvenlik | Hız (2-5x), Studio GUI, MoE optimizasyonu |
| **TRL** | ~17.6K | Tam pipeline (sadece trainer değil), Docker, değerlendirme | GRPO, resmi HF entegrasyonu |
| **Axolotl** | ~11.4K | Daha basit config, Docker, güvenlik eval | GRPO, GDPO, sequence parallelism |
| **torchtune** | Meta destekli | Config-tabanlı kurumsal odak | Knowledge distillation, QAT, PyTorch-native |

**ForgeLM'in gelişen niş'i:** Config-tabanlı, CI/CD-uyumlu, **güvenlik-bilinçli**, kurumsal LLM ince ayarı. Güvenlik + uyumluluk açısı mevcut en güçlü farklılaştırıcıdır.

---

## Karar Günlüğü

| Tarih | Karar | Gerekçe |
|-------|-------|---------|
| 2026-03-23 | Yeni özelliklerden önce Faz 2.5 (Güvenilirlik) eklendi | Ürün analizi kritik boşluklar ortaya koydu |
| 2026-03-23 | Doğrudan bulut API entegrasyonu öncelik düşürüldü | Sürdürülemez bakım yükü, 3. parti bağımlılık riski |
| 2026-03-23 | Docker tabanlı dağıtım stratejisi benimsendi | Taşınabilir, kullanıcı kontrollü altyapı |
| 2026-03-23 | `trust_remote_code` kurumsal engelleyici olarak işaretlendi | Düzenlemeye tabi sektörlerle uyumsuz güvenlik riski |
| 2026-03-23 | Faz 5 (Hizalama Stack) Kritik olarak önceliklendirildi | Rekabet analizi: DPO/GRPO pazar beklentisi, tek başına ORPO yetersiz |
| 2026-03-23 | Faz 6 (Güvenlik ve Uyumluluk) birincil farklılaştırıcı seçildi | Hiçbir rakip güvenlik eval veya EU AI Act uyumluluğu entegre etmiyor. Ağustos 2026 son tarihi |
| 2026-03-23 | Faz 7 (MoE/VLM/Birleştirme) süregelen olarak kapsamlandı | Model ortamı MoE ve multimodal'a kayıyor; desteklemeli ama Faz 5-6 pahasına değil |
| 2026-03-23 | Hizalama yöntemleri için TRL trainer'ları kullanılacak | TRL zaten DPO, KTO, GRPO implementasyonlarını sunuyor — ForgeLM yeniden implement etmek yerine config, değerlendirme ve pipeline entegrasyonu ile sarar |

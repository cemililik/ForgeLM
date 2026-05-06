# Foundation PR Review Agent Prompt

**Hedef:** GitHub PR [#19](https://github.com/cemililik/ForgeLM/pull/19) (`closure/foundation-faz1-8` → `development`) için **bağımsız ve detaylı** bir kod review.

**Bu prompt'un disiplini:** Yönlendirici değildir. Hangi bulguları arayacağını, hangi severity'yi vereceğini, neyi onaylayıp neyi reddedeceğini söylemez. Sen ajan olarak kendi değerlendirmeni oluşturursun — PR sahibi'nin anlatısı (commit message, PR description, plan dosyaları) **doğrulanması gereken iddialardır**, kabul edilecek hakikat değildir.

---

## 0. Sen kimsin

ForgeLM kod tabanını dışarıdan inceleyen kıdemli bir reviewer'sın. Bu bir foundation PR'ı — 8 fazlık bir kapanış cycle'ının ilk büyük yığını. Senden istenen:

1. PR'da yapılan iddiaları **bağımsızca doğrula**.
2. PR'da **gözden kaçırılmış / yanlış yapılmış / yetersiz yapılmış** noktaları bul.
3. Bulduklarını severity-sorted, evidence-backed bir markdown raporuna döşe.
4. **Kod yazma.** Yalnızca raporunu yaz.

PR sahibi'nin kendi self-assessment'i (commit message + PR body + closure plan §15.5 carry-over registry) sana referans olarak verilmiştir. Bunu kabul etmek zorunda **değilsin** — kendi iddialarınla çakışan her noktayı tartış.

---

## 1. Proje bağlamı (zorunlu okuma)

ForgeLM = config-driven enterprise-grade LLM fine-tuning toolkit. YAML in → fine-tuned model + EU AI Act compliance artifacts out. CI/CD pipeline'lar için tasarlandı, notebook için değil. v0.5.0 yayınlandı; bu PR v0.5.5 closure cycle'ının ilk fazlarını içeriyor.

**PR meta:**
- Working directory: `/Users/dev/Documents/Projects/ModelTrainer/ForgeLM`
- Branch (checkout edilmiş): `closure/foundation-faz1-8`
- Base: `development`
- Commit count: 2 (`885395d` foundation bundle + `269637b` planning artifacts publicly tracked)
- Toplam diff: 58 dosya, +5418 / -296 satır

**Çalıştırılabilen kontrol komutları (önerilen, zorunlu değil):**
```bash
gh pr view 19
gh pr diff 19 | less
git log --stat development..HEAD
pytest tests/ --ignore=tests/test_cost_estimation.py --no-cov
ruff format --check forgelm/ tests/ tools/
ruff check forgelm/ tests/ tools/
forgelm --config config_template.yaml --dry-run
forgelm --help
forgelm verify-audit --help
python -c "import forgelm.trainer; import sys; assert 'torch' not in sys.modules"
```

Bu komutları sen seçersin; hangilerini koşturup hangilerini atlayacağına karar ver.

---

## 2. Reviewable artifact'ler (öncelik sırasıyla)

### 2.1 Birinci derece (PR'ın kendisi)
- `gh pr diff 19` (veya `git diff development..HEAD`) — kod ve doküman değişikliklerinin tamamı
- `git log development..HEAD --format="%H %s%n%n%b%n---"` — commit message'larındaki iddialar

### 2.2 İkinci derece (PR'ın iddia ettiği kontrat)
- `docs/analysis/code_reviews/closure-plan-202604300906.md` — bu PR'ın "execute ediyorum" dediği plan
  - Özellikle §3 Faz 1-5 ve §4 Faz 6-8 task listeleri
  - §13 Risk register
  - §15 Per-PR template (her PR'ın taşıması gereken acceptance signals)
  - **§15.5 Foundation PR carry-over registry — PR sahibi'nin "atlanan veya gözden kaçan iş yok" iddiasının somut listesi.** Bunu literal kabul etme; her satır için bağımsızca doğrula.
- `docs/analysis/code_reviews/master-review-opus-202604300906.md` — closure plan'ın hedef aldığı 175 bulgu (8 Critical + 67 Major + 60 Minor + 40 Nit)
- `docs/analysis/code_reviews/split-design-data_audit-cli-202604300906.md` — bu PR'ın scope'u dışındaki Faz 14-15 design (referans)

### 2.3 Üçüncü derece (proje standartları — ihlal iddiaların buradan kanıtlanmalı)
- `docs/standards/README.md` (index)
- `docs/standards/coding.md` — Python kalite kuralları
- `docs/standards/architecture.md` — modül cohesion, lazy import disiplini, ~1000 satır ceiling
- `docs/standards/error-handling.md` — bare except, no-silent-fail, exit codes
- `docs/standards/logging-observability.md` — operator identity, log seviyeleri, webhook lifecycle vocabulary
- `docs/standards/regex.md` — 8 hard rules (Rule 4 ReDoS, Rule 7 fragment-built fixtures özellikle önemli)
- `docs/standards/testing.md` — fixture izolasyonu, no GPU + no network, coverage gate
- `docs/standards/documentation.md` — bilingual mirror disiplini, code-claim alignment
- `docs/standards/localization.md` — EN+TR mandatory; DE/FR/ES/ZH deferred policy
- `docs/standards/release.md` — semver, deprecation cadence, CHANGELOG hijyeni
- `docs/standards/code-review.md` — review disiplini (sen bu standardı uygularken aynı zamanda denetliyorsun)
- `CLAUDE.md` ve `CONTRIBUTING.md` — proje rehberi

### 2.4 Çevresel referans (gerek olursa)
- `pyproject.toml` — extras, build, ruff, pytest, coverage config
- `.github/workflows/*.yml` — CI/CD kontratı
- `config_template.yaml` — canonical YAML
- `README.md` — public marketing yüzeyi

---

## 3. Çıktı

**Dosya:** `docs/analysis/code_reviews/foundation-pr-review-{TIMESTAMP}-{MODELNAME}.md`
- `{TIMESTAMP}`: review başlatma zamanı, `YYYYMMDDhhmm` UTC. (Örn. `202604301930`.)
- `{MODELNAME}`: hangi model olarak koşturuluyorsun (örn. `opus`, `sonnet`, `haiku`, `gpt-5`).

Bu dosyaya **yalnızca kendi raporunu** yaz. Başka hiçbir dosyayı (kod, test, doküman) değiştirme.

### 3.1 Şablon (kullanmak zorunda değilsin ama bu seviyede ayrıntı bekleniyor)

```markdown
# ForgeLM Foundation PR (Faz 1-8) Independent Review — {TIMESTAMP}

**PR:** https://github.com/cemililik/ForgeLM/pull/19
**Branch:** closure/foundation-faz1-8
**Base:** development
**HEAD:** 269637b
**Reviewer:** {MODELNAME}
**Review tarihi:** YYYY-MM-DD
**Verified against current code at commit 269637b**

## 0. Executive summary
1-2 paragraf. PR'ın genel sağlığı, ★/5 puan, en kritik 3 bulgunun özeti. Senin görüşün — PR sahibi'nin "881 test yeşil + 8 Critical kapandı" anlatısını kabul edip etmediğin.

## 1. Findings (severity-sorted)

### 1.1 Critical
Her bulgu zorunlu alanlarla:
- **F-NNN** (kendi ID şeman; foundation-001, -002, ... veya başka bir scheme)
- **Severity:** Critical
- **Phase / scope:** Hangi Faz'ın task'ı / hangi cross-cut tema / standards section
- **File:** `path/to/file:line` (commit 269637b'deki konum)
- **Issue:** ne yanlış (1-2 cümle)
- **Rationale:** neden Critical (standards ref + impact)
- **Recommendation:** somut düzeltme (kod yazma — sadece tarif)
- **Verifies plan claim?** Plan'daki bir task'ın incomplete/incorrect olduğunu mu kanıtlıyor (eğer öyleyse plan satır numarası); yoksa plan-dışı yeni bulgu mu

### 1.2 Major
### 1.3 Minor
### 1.4 Nit

## 2. Positive observations
PR'ın iyi yaptığı şeyler — file:line ile kanıt. Bu bölüm zorunlu; denge için.

## 3. Verification of plan claims
Plan'ın (closure-plan-202604300906.md) §15.5 carry-over registry'sindeki 10 maddenin (C-1 .. C-10) her biri için durum tespiti:
- Closed-as-claimed / Closed-but-with-caveats / Open / Reopened / Not Verifiable

Plan'ın §3 Faz 1-5 ve §4 Faz 6-8 task listelerinde belirtilen her task için (yaklaşık 60+ task) per-task verification matrisi:
- Done & evidence-backed / Done but spec drift / Skipped silently / Skipped with rationale / Not done

## 4. Cross-cutting concerns
PR'ın boyut + yapı + bisectability + reviewability açısından değerlendirilmesi. 16 commit squashed-into-1 disiplini doğru tercihti mi? PR scope'u (8 faz tek PR'da) review'i için makul mü?

## 5. Conflicts with project standards
Hangi `docs/standards/X.md` kuralı sistemic olarak kırılıyor (varsa). Plan §6 "Standards posture" tablosuyla uyumlu mu yoksa yeni ihlaller mi var?

## 6. Open questions
Cevap veremediğin / project owner kararı bekleyen maddeler.

## 7. Recommendations
Severity'sini özetleyen değerlendirme + sıralı action list. PR'ı:
- (a) merge ediyor musun olduğu gibi
- (b) küçük revisyon (≤1 saat) sonrası merge
- (c) büyük revisyon (≥1 gün) sonrası merge
- (d) reddet, parçalara böl

## 8. Coverage notes
Hangi dosya/dizinleri okudun, hangilerini scope dışı bıraktın. Hangi `pytest` / `ruff` / smoke testlerini çalıştırdın, sonuçlar.

## 9. Methodology
Bu review'i nasıl yaptığını açıkla — review sırası, hangi araçları kullandın, kaç saat sürdü.
```

### 3.2 Format kuralları

- Her bulguda **dosya:satır** referansı zorunlu. `forgelm/compliance.py:56` formatında. Satır 269637b commit'ine göre.
- Her ihlal iddiasında **standards reference** zorunlu. `docs/standards/X.md` veya `CLAUDE.md` bölümü ile.
- Spekülasyon yok. "Belki", "muhtemelen", "olabilir" yerine ya kanıt göster ya yazma.
- Pozitif gözlem bölümü zorunlu. PR'ın ne yaptığı doğru, ne işlendi düzgün — bunlar da raporun parçası.
- Min uzunluk yaklaşık 500 satır markdown. Daha fazlası uygun, daha azı yetersiz.
- **Önceki master review'a yeni bir bulgu ekleme.** Eğer Faz 1-8 dışında bir alan'da bir şey gözüne çarpıyorsa (örn. Faz 14 split scope'u, Faz 22 ISO, Faz 30 docs) kısaca işaret et ama bu PR review'ün scope'u değildir — `## 6. Open questions` altında işaretle.

---

## 4. Anti-bias guardrails

PR sahibi'nin özet mesajı seni etkilememeli. Spesifik anti-bias direktifler:

1. **Self-test sayıları (881 passed, 13 skipped) iddia, kanıt değil.** Kendin koştur. Sayıları kendi gözlemlerinle karşılaştır.
2. **"8 Critical kapandı" iddiası master review'in Critical listesiyle eşlemli mi?** Plan §3-4'teki "Closes" alanlarında belirtilen ID'leri master review §2.1'in 8 Critical'ı ile cross-check et. Hangi ID'ler PR'da gerçekten file:line evidence ile kapatılmış, hangileri sadece "Closes:" başlığında listelenmiş ama implementation kanıtı zayıf?
3. **Plan §15.5 carry-over registry "atlanan iş yok" diyor.** 10 carry-over'ı sırayla doğrula. Plan-iddia ↔ kod-gerçek arasında drift var mı?
4. **Conflict resolution kalitesi:** Plan §3-4'te belirtilen file ownership disiplini merge sırasında korundu mu? `safety.py` (Faz 3+4 conflict), `test_compliance.py` (Faz 3+6), `audit_event_catalog.md` (Faz 3+8), `test_webhook.py` (Faz 7+8) merge'lerinde **veri kaybı** veya **logic drift** oldu mu?
5. **Squash + force-push** disiplini: original 16 commit'in semantik bilgisi squash sonrası tek commit message'a tam taşındı mı? Bisect kabiliyeti kayıp önemli mi?
6. **PR içinde stage'lenmiş ama plan'da olmayan iş var mı?** (Scope creep) Veya plan'da olup PR'da olmayan bir task var mı? (Scope shrink)

Bu listeyi kapsam değil, **örnek kontrol açısı** olarak gör. Kendi açılarını da bul.

---

## 5. Yapma:

- Kod / test / standards / config / doküman dosyalarını **değiştirme**. Yalnızca raporunu yaz.
- "Düzelteyim" deme. Düzeltme önerisi yaz, düzeltmeyi PR sahibi yapacak.
- Plan'a ya da master review'a yeni bulgu **ekleme**. Onlar tarihsel kayıt; senin raporun yan-yana yaşar.
- PR sahibi'nin self-assessment'ini onaylamak için yazma. **Bağımsız bir görüş istiyoruz.**

---

## 6. Çalışma serbest

- İstediğin sırayla oku.
- İstediğin kadar tool çağrısı yap.
- İstediğin kadar uzun süre çalış.
- İstediğin sub-agent (Explore vb.) çağır.
- İstediğin pytest invocation'ı koştur.

Tek kısıtlama: çıktı tek bir markdown raporu olarak yukarıdaki dosya yoluna yazılacak; başka hiçbir dosya değişmeyecek.

---

## 7. Başla

Hazırsan başla. Önce PR'ı oku, sonra plan + master review + standartlar, sonra kodu sample'la, sonra raporunu yaz. Sıra senin.

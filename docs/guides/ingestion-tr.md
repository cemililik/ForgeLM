# Doküman Yutma Rehberi

Ham kurumsal külliyatı (PDF / DOCX / EPUB / TXT / Markdown) ForgeLM'in
eğittiği SFT-uyumlu JSONL'a dönüştürün. Faz 11; `v0.5.0`'da tanıtıldı.
Faz 11.5 (`v0.5.1`) token-aware chunking, PDF sayfa header/footer dedup
ve yapılandırılmış ingestion notları ekledi. **Faz 12 (`v0.5.2`)**
markdown-aware splitter (`--strategy markdown`), code/credential
leakage scrubbing (`--secrets-mask`) ve DOCX tablolarının markdown
syntax'ı ile çıkarılmasını ekledi.

> Sonrasında [`forgelm audit`](data_audit-tr.md) ile uzunluk dağılımı /
> dil / near-duplicate / PII metriklerini yüzeye çıkarın; chunk'ları Q&A
> `messages` formuna genişletmek için
> [`forgelm --generate-data`](../reference/usage-tr.md) ile zincirleyin.

---

## Kurulum

```bash
pip install 'forgelm[ingestion]'
```

Bu opsiyonel grup `pypdf`, `python-docx`, `ebooklib`, `beautifulsoup4`,
`langdetect` ve (Faz 11.5'ten itibaren) opsiyonel non-cryptographic
hızlı `xxhash` backend'i getirir. Düz metin + Markdown için bu
paketlerin hiçbiri gerekmediği için opsiyonel tutuldu. Modülün kendisi
import edildiğinde ilgili extractor çağrılmadığı sürece bu bağımlılıkları
yüklemez.

OCR **kapsam dışındadır.** Metin katmanı olmayan taranmış PDF'ler bir
uyarı yüzdürür ve sıfır chunk üretir; ingest etmeden önce Tesseract veya
AWS Textract ile ön işleyin.

---

## Tek komut — dosya gir, JSONL çık

```bash
forgelm ingest ./book.epub --output data/sft.jsonl
forgelm ingest ./policies/ --recursive --output data/policies.jsonl
forgelm ingest ./scan.pdf --strategy sliding --chunk-size 1024 --overlap 128 \
  --output data/scan.jsonl

# Faz 12 — heading-aware splitter + secrets/PII maskeleme tek pass
forgelm ingest ./engineering_wiki/ --recursive \
  --strategy markdown --chunk-size 600 \
  --secrets-mask --pii-mask \
  --output data/wiki.jsonl
```

Çıktı satır başına bir chunk:

```json
{"text": "EU AI Act Madde 10, yüksek-riskli AI sağlayıcılarından ..."}
{"text": "Veri kalitesi kriterleri arasında uygunluk, temsil edicilik ..."}
```

Trainer'ın veri yükleyicisi `{"text": "..."}` formatını önceden
formatlanmış SFT sütunu olarak tanır (bkz.
[`forgelm/data.py`](../../forgelm/data.py)) — başka bir ön işleme
gerekmez.

---

## Chunking stratejileri

| Strateji | Ne zaman | Davranış |
|---|---|---|
| `paragraph` (varsayılan) | Düz yazı, politika dokümanları, makaleler | Açgözlü paragraf paketleyici; bir paragrafı asla yarıda bölmez. |
| `sliding` | Uzun teknik dokümanlar, prose ile karışık kod | Sabit boyutlu karakter penceresi + bağlam taşıması için `--overlap`. |
| `markdown` (Faz 12) | Heading hiyerarşili dokümanlar (rehberler, README, wiki sayfaları) | Heading sınırlarında böler; fenced kod bloklarını (` ``` ` veya `~~~`) atomik tutar; her chunk'ın başına heading **breadcrumb**'ını inline eder ki SFT loss doküman bağlamını görsün. Non-overlapping (sections are atomic). |

> Embedding tabanlı semantik chunking takip eden bir faza ayrılmıştır —
> bugün `NotImplementedError` raise eder ve runtime crash'i önlemek için
> CLI `--strategy` choice listesinden bilinçli olarak gizlenmiştir.

`--chunk-size` **karakter olarak** ölçülür, token değil. Kaba bir kural
olarak `--chunk-size 2048` tipik İngilizce / Türkçe metinde ≈500–700
token'a karşılık gelir — değeri `model.max_length` ile uyumlu seçin
(örneğin `max_length: 2048` token'lı bir model `--chunk-size 6000-8000`
ile rahat bir manevra alanı bulur, çünkü formatter sistem prompt + chat
template overhead'ine yer ayırır). Soft cap'i aşan paragraflar tek
başlarına yayılır — yarıda bölmekten daha iyidir.

**Sliding overlap sınırlıdır.** `--overlap` hem `< --chunk-size` hem de
`≤ --chunk-size // 2` olmalıdır — bunun üstündeki değerler chunk
sayısını patlatır (`--overlap 199 --chunk-size 200` kombinasyonu
karakter başına ~bir chunk üretir). Patolojik kombinasyonları CLI
önden reddeder.

**Dosyalar leksikografik sırayla işlenir** (sıralanmış glob sonucu),
böylece aynı girdi + bayraklarla yeniden çalıştırma byte-byte aynı
JSONL'i üretir.

---

## Yazma sırasında PII maskeleme

Tespit edilen e-posta, telefon, Luhn-doğrulanmış kredi kartı, IBAN ve
ulusal kimlik numaralarını (TR Kimlik No, DE Personalausweis, FR INSEE,
US SSN) chunk'lar JSONL'a inmeden önce redact etmek için `--pii-mask`
ekleyin:

```bash
forgelm ingest ./customer_emails/ --output data/anon.jsonl --pii-mask
```

Tespit edilen span'ler `[REDACTED]` ile değiştirilir. Tespit regex
tabanlıdır — false positive'ler kasıtlıdır. Sonrasında
`forgelm audit` ile çıktıyı doğrulayın.

---

## Yazma sırasında secrets/credential maskeleme (Faz 12)

`--secrets-mask` chunk'lar JSONL'a inmeden önce credentials ve token'ları
temizler — gerçek bir API anahtarı içeren metin üzerinde fine-tune
etmek o anahtarı modelin içine ezberletir.

```bash
# Tek başına
forgelm ingest ./engineering_wiki/ --output data/wiki.jsonl --secrets-mask

# PII maskelemesiyle kombine — secrets önce, PII sonra çalışır ki
# birleşik detector'lar örtüşen span'leri çift saymasın
forgelm ingest ./mixed_corpus/ --output data/clean.jsonl --secrets-mask --pii-mask
```

Detector dar bir prefix-anchored regex seti kullanır (false-positive
oranı bilerek düşük): AWS access key'leri, GitHub PAT'ler, Slack
token'ları, OpenAI API key'leri, Google API key'leri, JSON Web
Token'lar (kanonik header alphabet'ine anchored), tam OpenSSH / RSA /
DSA / EC / PGP private-key blokları (BEGIN'den END'e kadar tüm
gövde redact edilir) ve Azure storage connection string'leri. Tespit
edilen span'ler `[REDACTED-SECRET]` ile değiştirilir.

İsteğe bağlı `[ingestion-secrets]` extra'sı ileriki bir release için
ayrılmıştır — mevcut sürüm `detect-secrets` paketini çağırmaz; yalnızca
yukarıdaki regex seti çalışır.

---

## Recursive dizin yürüyüşü

```text
./policies/
├── 2024_q1.pdf
├── 2024_q2.pdf
└── archive/
    ├── 2023.docx
    └── 2022.epub
```

```bash
forgelm ingest ./policies/ --recursive --output data/all_policies.jsonl
```

Desteklenmeyen uzantıya sahip dosyalar (`.png`, `.zip`, vb.) sessizce
atlanır. Desteklenen uzantısı olup ekstrakte edilebilir metin içermeyen
dosyalar (taranmış PDF'ler, boş DOCX) bir uyarıyla atlanır.

**Şifreli PDF'ler** açıkça yakalanır: önce boş şifreyle decrypt denenir
(owner-encrypted ama hâlâ okunabilen PDF'leri kapsar). Başarısız olursa
dosya başına extractor `ValueError` raise eder — toplu ingestion
döngüsü bunu "extraction failed" olarak yakalar, dosya adını içeren
bir uyarı log'lar, sonuçtaki `files_skipped`'i artırır ve sonraki
dosyaya geçer. Uyarı metni harici decrypt yolunu önerir:

```bash
qpdf --decrypt --password=<pwd> input.pdf out.pdf
# veya
pdftk input.pdf input_pw <pwd> output out.pdf
```

CLI'a şifre flag'i bilinçli olarak eklenmedi — şifreleri shell
geçmişinden uzak tutmak daha güvenli.

**Metin gibi davranan binary içerik** (zip / image yeniden adlandırılmış
`.txt`) dosyanın %1'inden fazlası Unicode replacement karakteri olarak
decode olduğunda bir uyarı yüzdürür. Chunk'lar yine yazılır —
operatörler kalıp kalmayacaklarına karar verir — ama uyarı CI loglarında
görülecek kadar yüksek seslidir.

---

## Uçtan uca örnek

```bash
# 1. Yutma
forgelm ingest ./policies/ --recursive --output data/policies.jsonl

# 2. Denetim (near-duplicate'leri, PII'yi, uzunluk aykırılarını yakalar)
forgelm audit data/policies.jsonl --output ./audit/

# 3. (opsiyonel) Öğretmen modelle Q&A'ya genişletme
forgelm --config configs/synth.yaml --generate-data

# 4. Eğitim
forgelm quickstart domain-expert --dataset data/policies.jsonl
```

---

## CLI referansı

```text
forgelm ingest INPUT_PATH \
  --output FILE \
  [--chunk-size N | --chunk-tokens N --tokenizer MODEL_NAME] \
  [--overlap N] \
  [--overlap-tokens N] \
  [--strategy {sliding,paragraph,markdown}] \
  [--recursive] \
  [--pii-mask] \
  [--secrets-mask] \
  [--output-format {text,json}] \
  [--quiet | --log-level {DEBUG,INFO,WARNING,ERROR}]
```

`--strategy markdown` (Faz 12) heading-aware splitter'ı seçer; her
chunk'ın başına heading breadcrumb'ı inline eder. `--secrets-mask`
(Faz 12) AWS / GitHub / Slack / OpenAI / Google / JWT / OpenSSH /
PGP / Azure credential span'lerini chunk'lar JSONL'a inmeden önce
`[REDACTED-SECRET]` ile değiştirir.

`--output-format json` standart çıktıya makine-okunabilir bir özet
yazar (dosya yolları, chunk sayısı, format sayıları, notlar ve Faz
11.5'te eklenen `notes_structured` makine-okunabilir `{key: value}`
yapısı). CI/CD pipeline'larında kullanışlı.

### Token-aware chunking — `--chunk-tokens` (Faz 11.5)

Karakter tabanlı chunking pratik ama yoğun metinde modelinizin
`max_length` token bütçesini aşabilir. `--chunk-tokens N` ile birlikte
`--tokenizer MODEL_NAME` geçirerek chunk'ları aynı tokenizer üzerinden
boyutlandırabilirsiniz:

```bash
forgelm ingest ./policies/ --recursive --output data/policies.jsonl \
  --chunk-tokens 1024 --tokenizer "Qwen/Qwen2.5-7B-Instruct"
```

`--chunk-tokens` set edildiğinde `--chunk-size` görmezden gelinir (bir
uyarı log'lanır). `--overlap-tokens N` token cinsinden sliding overlap
boyutudur ve `--overlap` ile aynı yarım-pencere üst sınırına tabidir.
`--chunk-tokens` ile `--tokenizer` zorunludur — varsayılan vocab
seçmiyoruz çünkü chunk sayısı modelden modele sessizce değişirdi.

### PDF sayfa header/footer dedup (Faz 11.5)

`forgelm ingest`, bir PDF'in sayfalarının ≥ %70'inde ilk veya son
boş-olmayan satır olarak tekrarlayan satırları (şirket filigranı,
copyright satırı, sayfa numarası vb.) chunk'lamadan önce otomatik
olarak temizler. Açık/kapatma flag'i yok; bayrak gerektirmiyor.
Audit'in `near_duplicate_pairs` metriğindeki gürültüyü azaltır. 3
sayfadan kısa belgelerde devre dışı kalır. Yapılandırılmış notlar
çıktısı `pdf_header_footer_lines_stripped` alanını taşır.

---

## Sorun giderme

| Belirti | Sebep | Çözüm |
|---|---|---|
| `ImportError: PDF ingestion requires the 'ingestion' extra` | Opsiyonel grup yüklü değil | `pip install 'forgelm[ingestion]'` |
| "No extractable text in '<x>.pdf'" uyarısı + 0 chunk | Taranmış PDF, metin katmanı yok | Önce OCR (Tesseract / AWS Textract) |
| `FileNotFoundError: No supported files found at '<dir>'` | Dizinde sadece desteklenmeyen uzantı | Dosya uzantılarının `.pdf / .docx / .epub / .txt / .md` ile eşleştiğini doğrulayın |
| `ValueError: overlap must be in [0, chunk_size)` | `--overlap >= --chunk-size` | `--overlap`'i azaltın |

---

## Sınırlamalar

- **OCR:** Kapsam dışı. Harici araçlar kullanın — aşağıdaki örneklere bakın.
- **Tablolar / şekiller:** Faz 12'den (`v0.5.2`) itibaren `--strategy markdown`
  ile DOCX tabloları **Markdown tablo syntax'ına** (header + `---` ayraç +
  body satırları) dönüştürülür ve chunk sınırları arasında bütünlüğünü korur.
  Diğer stratejilerde (`paragraph`, `sliding`) ve bu sürümden önceki
  versiyonlarda tablolar düz metin olarak satır-major düzende düzleştirilir;
  görsel yapı kaybolur. PDF tabloları her durumda düzleştirilmiş kalır.
- **Metadata:** başlık / yazar / sayfa numarası düşürülür — yalnızca gövde
  metni JSONL'a iner.
- **Encoding:** non-UTF-8 girdi `errors="replace"` ile okunur; binary
  noise Unicode replacement karakterlerine dönüşür.
- **Semantik chunking:** embedding desteği bir sonraki fazda gelene kadar
  `NotImplementedError` raise eder.

---

## Taranmış PDF'lerle çalışma (OCR teslim akışı)

`forgelm ingest` OCR yapmaz. Metin katmanı olmayan taranmış PDF'ler
uyarı yüzdürür ve sıfır chunk üretir. Doğru yol önce harici OCR yapıp
sonucu ingestion'dan geçirmektir. İki tarif, maliyet sırasıyla:

### Tarif A — Tesseract (yerel, ücretsiz)

```bash
# Bir kerelik kurulum.
brew install tesseract            # macOS
# veya: sudo apt install tesseract-ocr tesseract-ocr-tur tesseract-ocr-eng

# 1. Her taranmış PDF sayfasını searchable PDF'e dönüştür (metin katmanı eklenir).
ocrmypdf scan_input.pdf scan_with_text_layer.pdf --language eng+tur

# 2. Şimdi normal text-bearing PDF olarak ingest et.
forgelm ingest scan_with_text_layer.pdf --output data/scan.jsonl
```

`ocrmypdf` önerilen sarmalayıcıdır — deskew, sayfa rotasyonunu yönetir
ve OCR'lı karakterleri görsel katmana yakmak yerine gizli bir metin
katmanı yazar. Yalnızca düz metne ihtiyaç varsa pure `tesseract` da
çalışır:

```bash
# Sayfa-başına çıkarım, TXT'e birleştir, TXT'i ingest et.
pdftoppm -r 300 scan_input.pdf scan_page -png
for img in scan_page-*.png; do tesseract "$img" - >> scan_pages.txt; done
forgelm ingest scan_pages.txt --output data/scan.jsonl
```

### Tarif B — AWS Textract (bulut, ücretli; tablo / formlarda daha iyi)

```bash
# 1. Taranmış PDF'leri S3'e yükle.
aws s3 cp scan_input.pdf s3://my-ingest-bucket/scan_input.pdf

# 2. Async Textract işi başlat. (Polling + SNS notification pattern için
#    AWS Textract dokümanına bakın; tam shell loop kapsam dışı.)
aws textract start-document-text-detection \
    --document-location "{\"S3Object\":{\"Bucket\":\"my-ingest-bucket\",\"Name\":\"scan_input.pdf\"}}"

# 3. İş tamamlandığında LINE blok'larını metne dök ve ingest et.
python -c "
import boto3, sys
client = boto3.client('textract')
job = sys.argv[1]
result = client.get_document_text_detection(JobId=job)
for block in result['Blocks']:
    if block['BlockType'] == 'LINE':
        print(block['Text'])
" $JOB_ID > scan_textract.txt
forgelm ingest scan_textract.txt --output data/scan.jsonl
```

Textract çok-sütunlu sayfalarda (akademik makaleler, dergiler), karışık
dilli sayfalarda ve formlar / tablolarda Tesseract'tan kayda değer
şekilde daha iyidir. Karşılığı: sayfa başına maliyet (yazıldığı sırada
text detection için ~$0.0015 / sayfa) ve ağ bağımlılığı.

### PII içeren formlar?

OCR'dan sonra, dataset'i yayımlamadan önce `--pii-mask` ile ön işleyin:

```bash
ocrmypdf medical_scan.pdf medical_with_text.pdf --language tur+eng
forgelm ingest medical_with_text.pdf --output data/medical.jsonl --pii-mask
forgelm audit data/medical.jsonl --output ./audit/
```

Audit adımı redaksiyonun çalıştığını doğrular: `data_audit_report.json`'da
kalan herhangi bir PII flag'i, maskelemeden kaçan bir satırdır.

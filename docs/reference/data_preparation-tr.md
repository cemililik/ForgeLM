# Veri Hazırlama Rehberi

> **Kapsam.** Bu sayfa SFT-row şemasını kapsar. Modern veri pipeline'ı
> (DPO/SimPO/KTO/GRPO satır formatları, audit, ham doc'lardan ingest,
> PII / secrets maskeleme, multi-dataset karıştırma) için bkz:
>
> - [Doküman Ingestion Rehberi](../guides/ingestion-tr.md) — `forgelm
>   ingest` ham → JSONL.
> - [Veri Seti Audit Rehberi](../guides/data_audit-tr.md) — `forgelm
>   audit` ön-uçuş kapısı (PII, secrets, near-duplicate, leakage,
>   quality).
> - [Veri Setleri Formatları](../usermanuals/tr/concepts/data-formats.md)
>   — per-trainer format referansı (SFT messages, DPO `chosen` /
>   `rejected`, KTO `completion` + `label`, GRPO yalnız `prompt`).
> - [`forgelm.data.prepare_dataset`](library_api_reference-tr.md#veri-hazırlama)
>   — Python API.

ForgeLM, perde arkasında Hugging Face `datasets` (veri setleri) kütüphanesini kullanır. HF (Hugging Face) platformundaki yüz binlerce veri setine anında bağlanabildiği gibi, gözetimli ince ayar (supervised fine-tuning - SFT) yaparken sizin kendi veri setinizin doğru şekilde işlenmesi için de onu belirli yapısal ilkelere göre formatlamanız gerekir.

## Desteklenen Formatlar

ForgeLM'in veri işlemcisi (data processor), sistemde **Talimat/Yanıt (Instruction/Response)** formatında yapılandırılmış diyalogsal veri kümeleri (dataset) beklemektedir.

Eğer verileri Hugging Face Hub üzerinden yüklüyorsanız (örn. `dataset_name_or_path: "HuggingFaceH4/ultrachat_200k"`), veya `.jsonl` formatında yerel bir (local) test dosyası veriyorsanız, ForgeLM bu diyalogsal/konuşmaya dönük (conversational) sütunları (satır arama işlemi) tarayıp eşlemeye çalışır.

### Algılama Üzerine Şema Desteği (Implicit Schema Support)
ForgeLM sırasıyla kendi içerisinde eşleştirme yapabileceği sütun başlıkları arar:

- **Sistem Bağlamı (System Context) (İsteğe Bağlı - Optional)**: Eğer veri setinizde `System` (Sistem) isimli bir sütun (column) varsa bu birleşim için derlenecektir. Yoksa boş (kullanılmadan) bırakılır.
- **Kullanıcı Kullanım İstemleri (User Prompt) (Zorunlu)**: Veri tablosunda `User`, `instruction` ya da `text` olan ilk yeri arar.
- **Asistan Yanıtları (Assistant Response) (Zorunlu)**: Veri tablosunda `Assistant`, `output` ya da `response` adındaki sütunlara (column) odaklanır.

## Örnek JSONL Yapısı (Yerel Veri)

Eğer sisteme şirketinize ve size özel bir şirket içi model veri aktarımı yapmak istiyorsanız, bunu her satırın birer JSON nesnesi olduğu `.jsonl` dosyası şekline getirebilirsiniz. `.jsonl` yapınızın var olan `dataset_name_or_path` dosyası üzerindeki yoluna (config kısmından) dosyanızın tam adresini (mutlak konumunu) vermeniz yeterli olacaktır.

Aşağıda standart kabul görmüş örnek JSONL yapısı:
```json
{"System": "Sen kodlamada uzman, yardımcı bir Python yapay zeka asistanısın.", "User": "Bir listeyi Python'da nasıl ters çevirebilirim?", "Assistant": "`[::-1]` kullanabilirsin veya listelerdeki `.reverse()` metodundan (method) yardım alabilirsin."}
{"System": "Sen kodlamada uzman, yardımcı bir Python yapay zeka asistanısın.", "User": "Python'da döngü (loop) nedir?", "Assistant": "Döngü (Loop), dizilim veya benzeri işlemlerde belirli işlemleri devamlı tekrarlatarak otomatik işleterek üzerinde dönmek için kullanılır. For ya da While kullanabilirsin."}
```

## Chat Templates (Sohbet Şablonları) ve Otomatik Biçimlendirme
2026 yılı itibarıyla, modern diyalogsal modellerin eğitiminde artık manuel metin biçimlendirmesine (örneğin `[SYSTEM]...[USER]...` yazmaya) gerek yoktur.

ForgeLM, bunun yerine Hugging Face'in `tokenizer.apply_chat_template()` metodunu kullanır. Bu da şu anlama gelir: ForgeLM, eğitmekte olduğunuz modelin mimarisini (ister Llama-3, ister Mistral, Gemma veya Qwen olsun) dinamik olarak anlar ve verilerinizi otomatik olarak **tam olarak o modelin kendi doğal dil bilgisine özgü yapıya** (örneğin `<|im_start|>user\n...<|im_end|>`) göre düzenler.

Bu özellik, sizin hiçbir manuel efor sarf etmenize gerek kalmadan SOTA (En ileri teknoloji) standardında maksimum model uyumluluğu ve eğitim doğruluğu sağlar.

Baz (temel) modelinizin sohbet şablonlarını (chat templates) desteklediğinden emin olun. Desteklemiyorsa, ForgeLM jenerik/standart bir etiket (bounding token) yapısına geri dönecektir.

# Veri Hazırlama Rehberi

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

## Nihai Metin İstemi Formatı (Prompt Format)
Kullanıcılar anlamasa da ve hissetmese de, ForgeLM arka planda verileri derlerken veri metin yapılarınıza etiketler geçirerek (bounding tags) özel işlemler (tokenizing) gerçekleştirerek makinenin öğrenebileceği son noktaya hazırlar:

```text
[SYSTEM]
{system_text} (sistemden gelen metin)
[USER]
{user_text} (kullanıcıdan gelen sorgu / question)
[ASSISTANT]
{assistant_text} (AI asistan cevabı / answer)
```

Eğitim işleminde başarıyı artırmak için asıl baz modelin bu girdi yapısını kullanmaya ne kadar meyilli veya adaptasyonunun açık olduğundan emin olun!

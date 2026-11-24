# ClauseRAG pilot değerlendirmesi

Set, 15 sigorta belgesi ve 15 sözleşme içerir. Her grupta 9 kamuya açık ve 6 sentetik PDF bulunur. Altı belge geliştirme, kalan 24 belge sabit test için ayrıldı. Alt türler konut, kasko, ferdi kaza, hizmet, kira ve tedariktir.

- `degerlendirme.xlsx` içindeki **Belgeler** sekmesi kaynakları, incelenen tarafı ve test ayrımını gösterir. **Bulgular** sekmesi beklenen riskleri ve yanlış alarm örneklerini içerir.
- `pdf/` ölçümde kullanılacak dosyaları içerir. Kamuya açık kaynaklardan bölüm alındığında **Kaynak kapsamı** orijinal dosyadaki fiziksel sayfaları gösterir. Bulgulardaki sayfalar set içindeki PDF’nin 1’den başlayan fiziksel sayfalarıdır.
- `manifest.json` sabit sürümün belge kimliklerini, beklenen risk adetlerini ve SHA-256 özetlerini tutar. Aynı şablonu paylaşan iki bölgesel satın alma örneği test grubundadır. Test PDF’lerini dış RAG indeksine dahil etmeyin. PDF içi RAG, analiz sırasında kullanıcının yüklediği PDF’yi arayabilir.

Codex, etiketleri PDF metnini inceleyerek ve ClauseRAG tahmini kullanmadan hazırladı. Maddeler, incelenen taraf üzerindeki somut etkileriyle mevcut beş kategoriye eşlendi. `Sorumluluk sınırlamaları` etiketi, maddi sorumluluğu incelenen tarafa yükleyen hükümleri de kapsıyor. Yaptırım veya somut etki göstermeyen işlem talimatları `risk yok` olarak işaretlenebilir. Aynı etkiyi doğuran bitişik istisna listeleri tek bulguda gruplandı. Kamuya açık kesitler görünür hükümlerle sınırlı. Ek veya atıf hedefi set PDF’sinde yoksa etkisi varsayılmadı. `hzm-01` kaynakta bulunan metin katmanında yazım bozulmaları içerir. Bu pilot referans etiketleri bağımsız bir insan uzman tarafından doğrulanmadı.

## Tam PDF ölçümü

Komutları proje kökünde çalıştırın. Özgün etiket tablosunu sabit tutup düzeltmeler için bir kopya kullanın.

```powershell
uv run --locked python -m evaluation.evaluate validate
uv run --locked python -m evaluation.evaluate run --split test --output "$env:TEMP\clauserag-tam-pdf-v1"
```

`run` komutu `OPENAI_API_KEY` gerektirir. Mevcut tam PDF stratejisini kullanır ve belge başına tahminleri, çağrıda kullanılan tokenları, model kimliğini, süreyi ve uygulamanın elediği bulgu sayısını kaydeder. Aynı dizinle yeniden çalıştırıldığında başarılı belgeleri atlar. Süre PDF okuma, API çağrısı ve alıntı doğrulamasını kapsar. Etiketler modele gönderilmez.

Sayfa referansı için girdi JSON’undaki fiziksel sayfa numarası kullanılır. Modelin verdiği sayfada bulunamayan birebir alıntı, belgenin yalnızca bir sayfasında geçiyorsa o sayfaya bağlanır. Birden fazla sayfada geçen ve hedefi belirsiz kalan veya belgede bulunamayan alıntı içeren bulgu elenir.

Belge sonuçlarında `raw_findings` modelin doğrulama öncesi bulgularını, `discarded_findings` elenme nedenlerini ve `evidence_corrections` kabul edilen bulgulardaki sayfa düzeltmelerini içerir. Bu kayıtlardaki `finding_index` ve `evidence_index`, ham çıktının 1’den başlayan sırasını gösterir. `empty_rationale`, `missing_evidence`, `empty_quote`, `quote_not_found` ve `ambiguous_quote` nedenleri sırasıyla boş açıklama, eksik kanıt, boş alıntı, bulunamayan alıntı ve belirsiz sayfa eşleşmesidir. Terminal mesajı kaydedilen, elenen ve sayfası düzeltilen adetleri gösterir.

`run.json` analiz kodunun sürüm özetini de tutar. Kod güncellendikten sonra yeni bir çıktı klasörü kullanın. Böylece eski ve yeni doğrulayıcıyla üretilen sonuçlar aynı çalıştırmada karışmaz. Örneğin güncel sürümü `--output "$env:TEMP\clauserag-tam-pdf-v2"` ile çalıştırabilirsiniz. Önceki sürümün kayıtlı sonuçları kendi klasöründe puanlanabilir.

## Puanlama

1. Her tahmini aynı belgedeki en fazla bir `risk` satırıyla eşleştirin. Aynı hükmü veya gruplu hüküm listesini, kategoriyi ve maddi etkiyi arayın. Sonucu değiştiren istisna atlanmışsa eşleştirmeyin. `risk yok` kayıtları, yanlış alarm değerlendirmesinde kullanılır.
2. `inceleme.csv` dosyasında her belge için eşleştirilen tahmin sayısını `dogru_bulgu` alanına yazın. `gerekceyi_destekleyen_kanit` alanına PDF alıntılarının gerekçeyi gerçekten desteklediği tahminlerin sayısını yazın. Uygulamanın alıntının varlığını doğrulaması bu ikinci kontrolün yerini tutmaz. Sıfır değerleri de açıkça girin.
3. Aşağıdaki komutla sigorta ve sözleşme için ayrı TP, FP, FN, precision, recall, F1, token ve süre özetini üretin. Boş paydalı ölçüler `null` döner.

Örneğin `knt-02` için altı referans etiketin beşi `risk`, biri `risk yok` kararındadır. Beklenen risk sayısı beştir. Beş model tahmininden dördü doğru risklere eşleşir, biri `risk yok` örneğine alarm verirse TP=4, FP=1, FN=1 olur. Bu belgede precision, recall ve F1 %80’dir. `dogru_bulgu` alanına 4 girilir. `gerekceyi_destekleyen_kanit` sayısı ayrıca her tahminin kendi alıntıları üzerinden değerlendirilir. Risk olmadığı doğru şekilde atlanan bir örnek TP sayısına eklenmez.

```powershell
uv run --locked python -m evaluation.evaluate score --output "$env:TEMP\clauserag-tam-pdf-v1"
```

PDF içi RAG hazır olduğunda aynı test PDF’lerini, model sürümünü ve eşleştirme kurallarını kullanın. Her iki yöntemde de süreyi PDF okumadan doğrulanmış bulguya kadar ölçün. Pilot sonuçları belge türleri ve kaynak kapsamı ile birlikte raporlayın.

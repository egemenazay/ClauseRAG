# ClauseRAG

Türkçe sigorta poliçeleri ve sözleşmeler için kaynaklı risk tespiti. Uygulama PDF’deki maddeleri ön incelemeden geçirir ve olası etkilerini ilgili sayfadan alıntıyla gösterir.

## Çalıştırma

Python 3.13 ve `uv` ile proje klasöründe aşağıdaki komutu çalıştırın. İlk açılışta bağımlılıklar indirilir.

```powershell
uv run streamlit run main.py
```

Uygulamayı [localhost:8501](http://127.0.0.1:8501) adresinden açın. **Hazır örneği göster** düğmesi iki sayfalık sentetik poliçeyi ve önceden hazırlanmış, PDF’de doğrulanmış bulguları açar. Bağımlılıklar kurulduktan sonra bu akış çevrimdışı çalışır.

Canlı analiz için GPT-5.4 mini erişimi olan ücretli bir OpenAI API hesabı gerekir. PowerShell’de anahtarı yalnızca mevcut terminal oturumu için ayarlayın ve uygulamayı aynı oturumdan başlatın.

```powershell
$secureKey = Read-Host "OpenAI API anahtarı" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
uv run streamlit run main.py
```

**Örnek PDF’yi indir**, **PDF yükle** ve **Analiz et** adımlarını izleyin. Örneğin ikinci sayfasında 24 saatlik bildirim koşulunu ve teminat limitini düşürme yetkisini gösterebilirsiniz. Toplam analiz süresi PDF metninin çıkarılmasından alıntı doğrulamasına kadar ölçülür.

Canlı analiz başlatıldığında PDF’den çıkarılan metin OpenAI API’ye gönderilir. Yerelde dosya diske yazılmaz. Sunumda sentetik poliçeyi kullanın. MVP, en fazla 10 MB, 30 sayfa ve 60.000 çıkarılmış karakter içeren PDF’leri kabul eder. Taranmış sayfalar için OCR sonraki bir çalışma kalemidir.

## Mimari ve araştırma

- `documents.py` PDF metnini çıkarır ve sayfa numaralarını korur. `analysis.py` analiz stratejisini, bulgu biçimini ve ortak alıntı doğrulamasını tanımlar. `openai_model.py` model istemcisini, `main.py` arayüzü içerir.
- MVP’de Full-Context LLM, çıkarılan metni tek istekle inceler. Standart RAG sabit uzunluklu parçalarla, Clause-Aware RAG madde ve alt madde sınırlarını koruyan parçalarla aynı strateji arayüzüne eklenebilir. Sonraki adımlar kaynaklı soru-cevap ve aynı model arayüzü üzerinden fine-tuned bir model denemesidir.
- İlk üç strateji için üretici modeli sabit tutup aynı etiketli Türkçe belge setinde madde ve kategori düzeyinde precision, recall, micro/macro-F1, risksiz maddelerde yanlış alarm oranı, sayfa-alıntı eşleşmesi, alıntının bulguyu destekleme oranı ve uçtan uca gecikme ölçülmesi planlanıyor. Referans çalışma Basel Alkanjo’nun Stanford CS224N projesi *Practical and Interpretable Unfair ToS Detection*.

## Otomatik kontroller

```powershell
uv run python -m unittest discover -s tests -v
```

Testler canlı API anahtarı gerektirmez. Canlı uçtan uca kontrol için örnek PDF’yi ücretli API erişimiyle arayüzden analiz edin.

# Sağlık Takip Uygulaması

Bu uygulama, kullanıcıların e-Nabız sisteminden aldıkları tahlil sonuçlarını yükleyip analiz edebilecekleri ve kişiselleştirilmiş sağlık önerileri alabilecekleri bir web uygulamasıdır.

## Özellikler

- PDF formatındaki tahlil sonuçlarını OCR ile okuma
- Tahlil sonuçlarını analiz etme ve yorumlama
- Kişiselleştirilmiş sağlık önerileri sunma
- Kullanıcı profili ve sağlık verilerini takip etme
- Grafiksel veri gösterimi
- Güvenli veri saklama ve gizlilik

## Kurulum

1. Python 3.8 veya üstü sürümü yükleyin
2. Sanal ortam oluşturun ve aktifleştirin:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   ```
3. Gerekli paketleri yükleyin:
   ```bash
   pip install -r requirements.txt
   ```
4. Tesseract OCR'ı yükleyin:
   - Windows: https://github.com/UB-Mannheim/tesseract/wiki
   - Linux: `sudo apt-get install tesseract-ocr`
   - Mac: `brew install tesseract`

5. Uygulamayı çalıştırın:
   ```bash
   python health_app/app.py
   ```

## Kullanılan Teknolojiler

- Flask: Web framework
- SQLAlchemy: Veritabanı ORM
- PyPDF2 ve pdf2image: PDF işleme
- Tesseract OCR: Metin tanıma
- Pandas ve NumPy: Veri analizi
- Plotly: Grafik gösterimi
- Bootstrap 5: Frontend framework

## Güvenlik

- Kullanıcı şifreleri güvenli bir şekilde hashlenir
- PDF dosyaları güvenli bir şekilde saklanır
- Kullanıcı verileri şifrelenir
- HTTPS kullanımı önerilir

## Katkıda Bulunma

1. Bu repository'yi fork edin
2. Yeni bir branch oluşturun (`git checkout -b feature/yeniOzellik`)
3. Değişikliklerinizi commit edin (`git commit -am 'Yeni özellik eklendi'`)
4. Branch'inizi push edin (`git push origin feature/yeniOzellik`)
5. Pull Request oluşturun

## Lisans

Bu proje MIT lisansı altında lisanslanmıştır. Detaylar için [LICENSE](LICENSE) dosyasına bakın. 
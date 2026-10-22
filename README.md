# Karne Analiz Sistemi — Aşama 1: Ayrıştırıcılar ve Ortak Şema

Deneme sınavı karnelerini (PDF) yayınevinden bağımsız, soru düzeyinde bir JSON'a dönüştürür
ve sonucu çapraz kontrollerle doğrular.

## Çalıştırma

```bash
pip install -r requirements.txt
python cli.py karne.pdf --out out/     # format otomatik tanınır
bash tests/run_all.sh                   # tüm örneklerde doğrulamanın TAMAM olduğunu kontrol eder
```

Çıktılar (`out/<exam_id>/`):

| Dosya | İçerik |
|---|---|
| `exam_report.json` | Tüm sınav: yapı, sorular (kazanım, kitapçık eşlemesi, kurum şık dağılımı), tüm öğrenciler |
| `students/<student_id>.json` | Öğrenci başına tek dosya (sınav bağlamı + öğrenci). API'nin döndüreceği birim |
| `dogrulama_raporu.md` | Doğrulama özeti |

## Klasör yapısı

```
karne_core/
  schema.py        Ortak şema (pydantic, v1) — API sözleşmesi
  taxonomy.py      Ders/bölüm adlarını ortak kodlara eşler (TURKCE, MATEMATIK, ...)
  pdfutil.py       Koordinatlı metin çıkarımı (run / token / Courier cevap dizileri)
  builder.py       Ham çıktı -> ortak şema + çapraz doğrulama
  parsers/
    __init__.py    Yayınevi kaydı ve otomatik tanıma
    bes_cap.py     BES / ÇAP formatı (kurum soru analizi sayfaları dahil)
    supara.py      Supara formatı (ızgara cevaplar, 2 sayfalık karne, soru analizi yok)
  inference.py     Soru analizi olmayan formatlar için soru→kazanım ve A↔B kitapçık eşlemesi çıkarımı
schema/            Dışa aktarılmış JSON Schema dosyaları
samples/           Örnek karneler (regresyon testi)
tests/run_all.sh   Tüm örnekleri işleyip doğrulamayı kontrol eder
cli.py
```

## Şemanın temel kuralları

- **Soru kimliği** her zaman A kitapçığı sırasıdır: `TYT_MATEMATIK-07`. Öğrencinin kendi kitapçığındaki
  numara `booklet_no` alanında tutulur. Böylece A ve B kitapçıklı öğrenciler aynı soruda birleşir.
- **Cevap durumu:** `correct` / `wrong` / `blank` / `not_taken`. `not_taken`, seçmeli gruptan
  (Din / Felsefe seçmeli) çözülmeyen ders içindir ve nete girmez.
- `kazanim_report`, karnede basılı kazanım tablosudur (ham). Asıl analiz soru düzeyindeki `answers` ve
  `questions[].kazanim` üzerinden yapılır.

## Doğrulama (her çalıştırmada)

| Kontrol | Ne kanıtlar |
|---|---|
| Cevap dizisi → ders D/Y/B | Cevap hizalaması doğru |
| Net = D − Y/4 | Sayılar doğru okunmuş |
| Ders toplamları = genel toplam | Karne başlığı doğru okunmuş |
| Okul net listesi ile eşleşme | Karne ile liste aynı (ders D/Y/N, puan, sıra) |
| Karne kazanım tablosu = soru-kazanım eşlemesinden hesap | Kazanım eşlemesi doğru |
| Analizdeki doğru cevap = karne anahtarı | Kitapçık eşlemesi doğru |
| **Kurum şık dağılımı = öğrenci cevaplarının toplamı** | 73×125 cevabın tamamı doğru okunmuş |

## Desteklenen formatlar

| Format | Örnek | Öğrenci | Soru-kazanım | A↔B eşlemesi | Kurum şık dağılımı |
|---|---|---|---|---|---|
| BES / ÇAP | ÇAP TYT 0 | 73 | Yayınevi raporundan | Yayınevi raporundan | Yayınevi raporu (cevaplardan doğrulandı) |
| Supara | Alfa Seri TYT | 69 | **Çıkarım**: 120/120 kesin | **Çıkarım**: 80 kesin, 40 tahmini | Öğrenci cevaplarından hesaplandı |

## Soru analizi raporu yoksa: çıkarım (`inference.py`)

- **Soru → kazanım:** Her öğrencinin kazanım tablosundaki S/D/Y sayıları bir kısıttır. Bütün öğrencilerin
  kısıtlarını aynı anda sağlayan atama CP-SAT ile bulunur. Her soru için alternatif atama denenir; alternatif
  yoksa sonuç `kesin` olarak işaretlenir. Kazanım tablosu sayfaya sığmayıp eksik basılmışsa, basılmayanlar
  ders toplamından türetilen bir "diğer" kovasıyla kısıtlanır.
- **A ↔ B eşlemesi:** Aday çiftler aynı ders, aynı doğru cevap ve uyumlu kazanım koşuluyla belirlenir.
  Aralarından, iki gruptaki şık dağılımı en çok benzeyen tam eşleme seçilir. Çift, çıkarıldığında tam
  eşleme kurulamıyorsa `kesin`, aksi halde `tahmini` olarak işaretlenir.
- **Gerçek veriyle sınama:** Çıkarım, ÇAP verisinde (yayınevinin kendi raporu yok sayılarak) çalıştırıldı:
  - Kazanım: 102/102 doğru
  - `kesin` eşlemeler: 92/92 doğru
  - `tahmini` eşlemeler: 29/33 doğru
- Supara'daki 40 `tahmini` eşlemenin tamamı aynı kazanımlı sorular arasında (25'i Paragraf Yorumu). Bu yüzden
  kazanım düzeyindeki analiz etkilenmez. Soru düzeyindeki kurum istatistiğinde bu sorular kendi aralarında
  yer değiştirmiş olabilir; bu durum `questions[].inference` alanında belirtilir.

## Yeni yayınevi eklemek

1. `parsers/<yayinevi>.py` içinde `detect(pdf) -> skor` ve `parse(path) -> ham sözlük` yazılır
   (`bes_cap.parse` çıktısıyla aynı anahtarlar: `cards`, `questions`, `net_list`).
2. `parsers/__init__.py` içindeki `PARSERS` listesine eklenir.
3. Farklı ders adları varsa `taxonomy.py` içine eş anlamlı olarak eklenir.

## Bilinen sınırlar

- Çift/geçersiz işaretleme `given: "*"` olarak tutulur ve yanlış sayılır (Supara).
- Karnede basılmayan bölüm (öğrenci hiç girmemiş) tamamen boş olarak eklenir. Yayınevinin toplamları da bu şekilde.
- Yalnızca metin katmanlı PDF desteklenir; fotoğraf/taranmış karne Aşama 3'te (görüntü okuma) gelecek.
- Şu an yalnızca TYT doğrulandı. AYT ve LGS için yanlış katsayısı tanımlı (`builder.WRONG_PENALTY`),
  ancak örnek karneyle test edilmeli.
- Sınav tarihi karnede yok, `exam.date` boş kalıyor. Yükleme sırasında arayüzden girilecek.

# AutoTax Kurulum ve Çalıştırma Rehberi

## Hızlı Başlangıç (Docker — Tavsiye Edilen)

```powershell
# 1. Projeyi klonlayın / klasöre gidin
cd AutoTax-MVP

# 2. Docker ile başlatın (ilk seferde build alır ~5 dk)
docker-compose up --build -d

# 3. Tarayıcıda açın
# http://localhost:8000
# API Docs: http://localhost:8000/api/docs
```

## Yerel Çalıştırma (Windows)

```powershell
# 1. Tesseract kur (Windows installer):
# https://github.com/UB-Mannheim/tesseract/wiki
# Dil paketleri: deu, eng, fra, spa, ara, kor, chi_sim seç

# 2. Poppler kur (PDF için):
# https://github.com/oschwartz10612/poppler-windows/releases

# 3. Python ortamı
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 4. Ortam değişkenleri
Copy-Item env.example .env
# .env dosyasında TESSERACT_CMD yolunu düzenleyin

# 5. Başlat
python start.py
# veya: uvicorn main:app --reload --port 8000
```

## API Endpoint'leri

| Method | URL | Açıklama |
|--------|-----|----------|
| GET    | /api/health | Sağlık kontrolü |
| POST   | /api/ocr/upload | Tek fatura yükle |
| POST   | /api/ocr/upload-multi | Çoklu fatura yükle (max 50) |
| GET    | /api/stats/summary | Kombine filtre + pagination |
| GET    | /api/stats/by-date | Tarih aralığı |
| GET    | /api/stats/by-vendor | Firma adı |
| GET    | /api/stats/by-category | Kategori |
| GET    | /api/stats/by-payment | Ödeme yöntemi |
| GET    | /api/stats/export/excel | Excel indirme (server-side) |
| GET    | /api/docs | Swagger UI |

## Desteklenen Diller
Almanca · İngilizce · Fransızca · İspanyolca · Arapça · Korece · Çince

## Dosya Limitleri
- Maksimum: 30 MB / dosya
- Maksimum: 50 dosya / istek
- Desteklenen: JPG, PNG, PDF, WEBP, BMP, TIFF

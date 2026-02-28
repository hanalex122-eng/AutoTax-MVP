FROM python:3.11-slim

# ── Sistem bağımlılıkları ──────────────────────────────────
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-deu \
        tesseract-ocr-eng \
        tesseract-ocr-fra \
        tesseract-ocr-spa \
        tesseract-ocr-ara \
        tesseract-ocr-kor \
        tesseract-ocr-chi-sim \
        tesseract-ocr-tur \
        poppler-utils \
        libzbar0 \
        libgl1 \
        libglib2.0-0 \
        curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /app

# ── Python bağımlılıkları ──────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Uygulama kodları (storage/ HARİÇ) ─────────────────────
COPY . .

# ── Kalıcı veri klasörü: /app/data ────────────────────────
# Railway'de bu klasör deploy'lar arasında KORUNABİLİR
# Volume eklenince mount path /app/data olarak ayarlayın
RUN mkdir -p /app/data/uploads /app/data/incoming /app/data/processed models

ENV TESSERACT_CMD=/usr/bin/tesseract \
    DB_PATH=/app/data/invoices_db.json \
    SQLITE_PATH=/app/data/invoices.db \
    USERS_DB_PATH=/app/data/users.db \
    UPLOAD_DIR=/app/data/uploads \
    STORAGE_PATH=/app/data \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "start_prod.py"]


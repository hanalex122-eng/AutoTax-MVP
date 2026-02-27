FROM python:3.11-slim

# ── Sistem bağımlılıkları ──────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
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
    libsm6 \
    libxrender1 \
    libxext6 \
    curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python bağımlılıkları (cache layer) ───────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Uygulama dosyaları ────────────────────────────────────
COPY . .

# ── Kalıcı dizinler ───────────────────────────────────────
RUN mkdir -p storage/incoming storage/processed models

# ── Ortam değişkenleri ────────────────────────────────────
ENV TESSERACT_CMD=/usr/bin/tesseract \
    DB_PATH=/app/storage/invoices_db.json \
    SQLITE_PATH=/app/storage/invoices.db \
    REDIS_HOST=redis \
    REDIS_PORT=6379 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]

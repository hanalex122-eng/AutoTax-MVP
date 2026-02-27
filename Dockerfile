FROM python:3.11-slim

# ── Sistem bağımlılıkları (tek RUN = daha az layer) ───────
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

# ── Python bağımlılıkları ─────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Uygulama ──────────────────────────────────────────────
COPY . .

RUN mkdir -p storage/incoming storage/processed models

ENV TESSERACT_CMD=/usr/bin/tesseract \
    DB_PATH=/app/storage/invoices_db.json \
    SQLITE_PATH=/app/storage/invoices.db \
    REDIS_HOST=localhost \
    REDIS_PORT=6379 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips "*"

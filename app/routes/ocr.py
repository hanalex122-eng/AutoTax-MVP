from fastapi import APIRouter, UploadFile, File, HTTPException, Body, Request, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from typing import List, Optional
import asyncio
import os

from app.services.image_processor import to_raw_png, prepare_for_ocr
from app.services.ocr_engine import run_ocr
from app.services.invoice_parser import parse_invoice
from app.services.invoice_db import (
    add_invoice, update_invoice, get_review_queue, get_invoice
)
from app.services.qr_reader import read_qr, parse_qr
from app.models.invoice import InvoiceResult
from app.services.user_db import check_quota, increment_usage, PLANS

router = APIRouter(prefix="/ocr", tags=["OCR"])

MAX_FILE_SIZE = 30 * 1024 * 1024   # 30 MB

ALLOWED_MIME = {
    "image/jpeg", "image/jpg", "image/png", "image/webp",
    "image/bmp", "image/tiff", "application/pdf",
}

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".pdf"}

QR_MAX_STR   = 500        # QR override değer max uzunluk
QR_MAX_TOTAL = 9_999_999  # Makul max tutar


def _sanitize_filename(name: str) -> str:
    """Path traversal ve tehlikeli karakterleri temizle."""
    base = os.path.basename(name or "upload")
    safe = "".join(c for c in base if c.isalnum() or c in "._- ")
    return safe[:120] or "upload"


def _sanitize_qr_override(qr: dict) -> dict:
    """QR override değerlerini doğrula — injection koruması."""
    safe = {}
    for k, v in qr.items():
        if k == "raw":
            continue
        if not isinstance(v, str):
            v = str(v)
        v = v.strip()[:200]          # max 200 karakter
        if k == "total":
            try:
                f = float(v.replace(",", "."))
                if 0 < f <= QR_MAX_TOTAL:
                    safe[k] = f
            except ValueError:
                pass
        elif k == "vat_rate":
            try:
                i = int(v)
                if 0 < i <= 30:
                    safe[k] = i
            except ValueError:
                pass
        elif k in ("date", "time", "invoice_number", "vendor", "company", "vat_amount"):
            safe[k] = v
    return safe


async def _process(f: UploadFile) -> InvoiceResult:
    filename = _sanitize_filename(f.filename or "upload")

    # Uzantı kontrolü
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=415, detail=f"Desteklenmeyen dosya türü: {ext}")

    # Dosya boyutu kontrolü
    raw = await f.read()
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Dosya çok büyük ({len(raw)//1024//1024} MB). Maksimum: 30 MB."
        )
    if len(raw) < 100:
        raise HTTPException(status_code=400, detail="Dosya boş veya bozuk.")

    # Ham PNG (QR için — enhancement YOK)
    raw_png  = await run_in_threadpool(to_raw_png, raw, filename)

    # QR / Barkod — ham görüntüden
    qr_raw    = await run_in_threadpool(read_qr, raw_png)
    qr_parsed = _sanitize_qr_override(parse_qr(qr_raw)) if qr_raw else {}

    # Enhancement → Super Resolution → OCR
    ocr_ready = await run_in_threadpool(prepare_for_ocr, raw_png)
    text      = await run_in_threadpool(run_ocr, ocr_ready)

    parsed = parse_invoice(text)

    # QR override (sanitize edilmiş)
    for key in ("total", "date", "time", "invoice_number", "vendor", "vat_amount", "vat_rate", "company"):
        if qr_parsed.get(key) is not None:
            parsed[key] = qr_parsed[key]

    needs_review  = not parsed.get("total")
    review_reason = "Toplam tutar bulunamadı" if needs_review else None
    inv_id        = add_invoice(parsed, filename)

    return InvoiceResult(
        invoice_id     = inv_id,
        filename       = filename,
        vendor         = parsed.get("vendor"),
        date           = parsed.get("date"),
        time           = parsed.get("time"),
        total          = parsed.get("total"),
        vat_rate       = parsed.get("vat_rate"),
        vat_amount     = parsed.get("vat_amount"),
        invoice_no     = parsed.get("invoice_number"),
        category       = parsed.get("category"),
        payment_method = parsed.get("payment_method"),
        qr_raw         = qr_raw[:QR_MAX_STR] if qr_raw else None,
        qr_parsed      = qr_parsed or None,
        raw_text       = text[:5000],   # response boyutunu sınırla
        needs_review   = needs_review,
        review_reason  = review_reason,
        message        = "OCR tamamlandı",
    )


@router.post("/upload", response_model=InvoiceResult)
async def upload(request: Request, file: UploadFile = File(...)):
    user = getattr(request.state, "user", None)
    if user:
        allowed, used, limit = check_quota(user)
        if not allowed:
            plan_label = PLANS.get(user.get("plan","free"), {}).get("label","")
            raise HTTPException(
                status_code=429,
                detail=f"Aylık fatura limitinize ulaştınız ({used}/{limit}). "
                       f"{plan_label} planınızı yükseltin."
            )
    result = await _process(file)
    if user:
        increment_usage(user["id"])
    return result


@router.post("/upload-multi")
async def upload_multi(request: Request, files: List[UploadFile] = File(...)):
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="Tek seferde maksimum 50 dosya yükleyebilirsiniz.")
    user = getattr(request.state, "user", None)
    if user:
        allowed, used, limit = check_quota(user)
        remaining = (limit - used) if limit != -1 else len(files)
        if not allowed:
            plan_label = PLANS.get(user.get("plan","free"), {}).get("label","")
            raise HTTPException(
                status_code=429,
                detail=f"Aylık fatura limitinize ulaştınız ({used}/{limit}). "
                       f"{plan_label} planınızı yükseltin."
            )
        if limit != -1 and len(files) > remaining:
            files = files[:remaining]
    # Seri işle (concurrent race condition'ı önle)
    results = []
    errors  = []
    for f in files:
        try:
            r = await _process(f)
            results.append(r)
        except HTTPException as e:
            errors.append({"filename": f.filename, "error": e.detail})
        except Exception as e:
            errors.append({"filename": f.filename, "error": "İşleme hatası"})
    return {"count": len(results), "invoices": results, "errors": errors}


# ── İnceleme kuyruğu ─────────────────────────────────────
@router.get("/review-queue")
def review_queue(page: int = 1, per_page: int = 50):
    """OCR'nin okuyamadığı / eksik bilgili faturalar."""
    return get_review_queue(page=page, per_page=per_page)


# ── Tek fatura getir ──────────────────────────────────────
@router.get("/invoice/{inv_id}")
def get_one(inv_id: str):
    inv = get_invoice(inv_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Fatura bulunamadı.")
    return inv


# ── Manuel düzeltme ───────────────────────────────────────
@router.patch("/invoice/{inv_id}")
def patch_invoice(inv_id: str, fields: dict = Body(...)):
    """
    Kullanıcı eksik / yanlış alanları elle düzeltir.
    Kabul edilen alanlar: vendor, date, time, total, vat_rate,
    vat_amount, invoice_number, category, payment_method
    """
    ok = update_invoice(inv_id, fields)
    if not ok:
        raise HTTPException(status_code=404, detail="Fatura bulunamadı veya güncellenemedi.")
    return {"status": "ok", "invoice_id": inv_id, "updated": fields}

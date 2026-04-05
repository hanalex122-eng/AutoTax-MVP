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
    add_invoice, update_invoice, get_review_queue, get_invoice,
    find_duplicate, find_recurring
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


def _plan_allows_qr(user) -> bool:
    """Kullanıcının planı QR okumaya izin veriyor mu?"""
    if not user:
        return False
    plan = user.get("plan", "free")
    return PLANS.get(plan, PLANS["free"]).get("qr", False)


async def _process(f: UploadFile, qr_allowed: bool = True,
                   user_id: str = None) -> InvoiceResult:
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

    # QR / Barkod — plan izni varsa
    qr_raw    = await run_in_threadpool(read_qr, raw_png) if qr_allowed else None
    qr_parsed = _sanitize_qr_override(parse_qr(qr_raw)) if qr_raw else {}

    # Enhancement → Super Resolution → OCR
    ocr_ready = await run_in_threadpool(prepare_for_ocr, raw_png)
    text      = await run_in_threadpool(run_ocr, ocr_ready)

    # --- ADDED START ---
    ocr_result = text
    print("=== OCR RAW RESPONSE START ===")
    print(ocr_result)
    print("=== OCR RAW RESPONSE END ===")
    try:
        print("OCR IsErroredOnProcessing:", ocr_result.get("IsErroredOnProcessing"))
    except:
        pass
    try:
        print("OCR ErrorMessage:", ocr_result.get("ErrorMessage"))
    except:
        pass
    try:
        parsed = ocr_result.get("ParsedResults")
        print("OCR ParsedResults:", parsed)
    except:
        pass
    # --- ADDED END ---

    # --- ADDED START ---
    try:
        file_bytes = raw
        print("=== OCR INPUT INFO ===")
        print("Original file size:", len(file_bytes))
    except Exception as e:
        print("Error reading input info:", str(e))
    try:
        processed_bytes = ocr_ready
        print("=== OCR PREPROCESS INFO ===")
        print("Processed size:", len(processed_bytes))
    except Exception as e:
        print("Error reading preprocess info:", str(e))
    print("=== OCR RAW RESPONSE START ===")
    print(ocr_result)
    print("=== OCR RAW RESPONSE END ===")
    try:
        print("IsErroredOnProcessing:", ocr_result.get("IsErroredOnProcessing"))
        print("ErrorMessage:", ocr_result.get("ErrorMessage"))
    except Exception as e:
        print("Error reading error fields:", str(e))
    try:
        _parsed_dbg = ocr_result.get("ParsedResults")
        print("ParsedResults:", _parsed_dbg)
    except Exception as e:
        print("Error reading ParsedResults:", str(e))
    try:
        _text_dbg = ocr_result["ParsedResults"][0]["ParsedText"]
        print("=== OCR TEXT START ===")
        print(_text_dbg)
        print("=== OCR TEXT END ===")
    except Exception as e:
        print("TEXT EXTRACTION ERROR:", str(e))
    print("=== OCR DEBUG SUMMARY ===")
    try:
        if not ocr_result:
            print("FAIL: No response")
        elif hasattr(ocr_result, "get") and ocr_result.get("IsErroredOnProcessing"):
            print("FAIL: OCR API error")
        elif hasattr(ocr_result, "get") and not ocr_result.get("ParsedResults"):
            print("FAIL: No ParsedResults")
        else:
            try:
                _summary_text = ocr_result["ParsedResults"][0].get("ParsedText", "")
            except Exception:
                _summary_text = ocr_result if isinstance(ocr_result, str) else ""
            if not _summary_text.strip():
                print("FAIL: Empty OCR text")
            else:
                print("SUCCESS: OCR returned text")
    except Exception as e:
        print("SUMMARY ERROR:", str(e))
    # --- ADDED END ---

    # --- ADDED START ---
    try:
        print("\n=== OCR ANALYSIS: INPUT ===")
        print("Raw image bytes:", len(raw_png))
    except Exception as e:
        print("Input analysis error:", str(e))
    try:
        print("\n=== OCR ANALYSIS: PREPROCESS ===")
        print("Processed image bytes:", len(ocr_ready))
    except Exception as e:
        print("Preprocess analysis error:", str(e))
    try:
        with open("debug_raw.png", "wb") as _f:
            _f.write(raw_png)
        with open("debug_processed.png", "wb") as _f:
            _f.write(ocr_ready)
        print("Saved debug images: debug_raw.png, debug_processed.png")
    except Exception as e:
        print("Image save error:", str(e))
    try:
        print("\n=== OCR ANALYSIS: PRIMARY OCR ===")
        print("Text length:", len(text))
        print("Text preview:", text[:200] if text else "EMPTY")
    except Exception as e:
        print("Primary OCR analysis error:", str(e))
    alt_text = ""
    try:
        import pytesseract as _pt
        from PIL import Image as _Image
        import io as _io
        _img = _Image.open(_io.BytesIO(ocr_ready))
        alt_text = _pt.image_to_string(_img, config="--psm 6")
        print("\n=== OCR ANALYSIS: FALLBACK OCR ===")
        print("Alt text length:", len(alt_text))
        print("Alt preview:", alt_text[:200] if alt_text else "EMPTY")
    except Exception as e:
        print("Fallback OCR error:", str(e))
    print("\n=== OCR FINAL REPORT ===")
    try:
        if not text and not alt_text:
            print("RESULT: TOTAL OCR FAILURE")
            print("LIKELY CAUSES:")
            print("- Image unreadable or corrupted")
            print("- Preprocessing destroying text")
            print("- Tesseract not configured correctly")
        elif not text and alt_text:
            print("RESULT: PRIMARY OCR FAILED, FALLBACK WORKS")
            print("LIKELY CAUSE: OCR config or pipeline issue")
        elif text:
            print("RESULT: OCR WORKING")
            if len(text.strip()) < 10:
                print("WARNING: Very low text content")
            else:
                print("Text extraction looks OK")
    except Exception as e:
        print("Final report error:", str(e))
    print("=== END OF OCR REPORT ===")
    # --- ADDED END ---

    parsed = parse_invoice(text)

    # QR override (sanitize edilmiş)
    for key in ("total", "date", "time", "invoice_number", "vendor", "vat_amount", "vat_rate", "company"):
        if qr_parsed.get(key) is not None:
            parsed[key] = qr_parsed[key]

    needs_review  = not parsed.get("total")
    review_reason = "Toplam tutar bulunamadı" if needs_review else None
    inv_id        = add_invoice(parsed, filename, user_id)

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
    result = await _process(file, qr_allowed=_plan_allows_qr(user),
                            user_id=user["id"] if user else None)
    if user:
        increment_usage(user["id"])
        # Kota %80 veya %95 dolunca uyarı e-postası gönder
        _, used2, limit2 = check_quota(user)
        if limit2 and limit2 > 0:
            pct = used2 / limit2
            if pct in (0.8, 0.95) or (0.799 < pct < 0.801) or (0.949 < pct < 0.951):
                from app.services.email_service import send_quota_warning
                from app.services.user_db import get_user_by_id
                u = get_user_by_id(user["id"])
                if u:
                    send_quota_warning(
                        u["email"],
                        u.get("full_name") or u["email"].split("@")[0],
                        used2, limit2, u.get("plan","free")
                    )

    # Duplikasyon + tekrarlayan fatura kontrolü
    uid = user["id"] if user else None
    dup = find_duplicate(
        vendor         = result.vendor,
        date           = result.date,
        total          = result.total,
        invoice_number = result.invoice_number,
        user_id        = uid,
    )
    result_dict = result.model_dump()

    if dup:
        result_dict["duplicate_warning"] = {
            "existing_id":        dup["id"],
            "existing_date":      dup.get("date"),
            "existing_timestamp": dup.get("timestamp"),
            "existing_total":     dup.get("total"),
        }
        if user:
            from app.services.email_service import send_duplicate_warning
            from app.services.user_db import get_user_by_id
            u2 = get_user_by_id(user["id"])
            if u2:
                send_duplicate_warning(
                    u2["email"],
                    u2.get("full_name") or u2["email"].split("@")[0],
                    result.vendor or "?",
                    result.total  or 0,
                    (dup.get("timestamp") or "")[:10],
                )

    # Tekrarlayan fatura analizi (3 ay ardışık gelmişse bildir)
    if result.vendor:
        recurring = find_recurring(result.vendor, months=3, user_id=uid)
        if len(recurring) >= 3:
            months_found = [r["month"] for r in recurring]
            result_dict["recurring_info"] = {
                "vendor":       result.vendor,
                "months":       months_found,
                "avg_total":    round(sum(r["avg_total"] for r in recurring) / len(recurring), 2),
                "message":      f"Bu firmadan {len(recurring)} aydır düzenli fatura geliyor.",
            }

    return result_dict


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
    qr_ok   = _plan_allows_qr(user)
    uid     = user["id"] if user else None
    for f in files:
        try:
            r = await _process(f, qr_allowed=qr_ok, user_id=uid)
            if user:
                increment_usage(user["id"])
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

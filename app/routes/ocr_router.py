from fastapi import APIRouter, UploadFile, File
from fastapi.concurrency import run_in_threadpool
from typing import List
import io
import asyncio
import os

from pdf2image import convert_from_bytes
from PIL import Image, ImageEnhance, ImageFilter
import cv2
import numpy as np
from functools import lru_cache

from app.services.ocr_engine import run_ocr
from app.services.invoice_parser import parse_invoice
from app.services.invoice_db import add_invoice
from app.services.qr import read_qr_raw, parse_qr_data
from app.models.invoice_model import InvoiceModel

router = APIRouter(prefix="/ocr", tags=["OCR"])

MODEL_PATH = os.getenv("SR_MODEL_PATH", "app/models/ESPCN_x2.pb")


# ---------------------------------------------------------
# SUPER RESOLUTION (ESPCN x2 + LANCZOS fallback)
# ---------------------------------------------------------
@lru_cache(maxsize=1)
def get_sr_model():
    sr = cv2.dnn_superres.DnnSuperResImpl_create()
    sr.readModel(MODEL_PATH)
    sr.setModel("espcn", 2)
    return sr


def super_resolve(png_bytes: bytes) -> bytes:
    try:
        sr = get_sr_model()
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        result = sr.upsample(cv_img)
        img = Image.fromarray(cv2.cvtColor(result, cv2.COLOR_BGR2RGB))
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()
    except Exception:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        w, h = img.size
        img = img.resize((w * 2, h * 2), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()


# ---------------------------------------------------------
# IMAGE ENHANCEMENT  (OCR için optimize — QR burada çalışmaz)
# ---------------------------------------------------------
def enhance_image(png_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")

    # 1) Kontrast + Parlaklık
    img = ImageEnhance.Contrast(img).enhance(1.5)
    img = ImageEnhance.Brightness(img).enhance(1.1)

    # 2) Sharpness
    img = ImageEnhance.Sharpness(img).enhance(2.0)

    # 3) UnsharpMask (kenar belirginleştirme)
    img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=150, threshold=3))

    # 4) Gri tona çevir → gürültü temizle → adaptif eşik
    cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

    # Gürültü temizleme
    gray = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)

    # Gamma düzeltme (açık görüntüler için)
    gamma = 1.2
    lut = np.array([((i / 255.0) ** (1.0 / gamma)) * 255 for i in range(256)], dtype="uint8")
    gray = cv2.LUT(gray, lut)

    # Adaptif eşik (binary LUT yerine — daha akıllı)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 8
    )

    # 5) Deskew (eğim düzeltme) — koyu piksel = metin
    coords = np.column_stack(np.where(binary < 128))  # metin pikselleri
    if len(coords) > 50:
        angle = cv2.minAreaRect(coords)[-1]
        # Açıyı -45..+45 aralığına normalize et
        if angle < -45:
            angle = 90 + angle
        # Küçük açıları yok say (gürültü)
        if abs(angle) > 0.5:
            (h, w) = binary.shape[:2]
            M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            binary = cv2.warpAffine(
                binary, M, (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE
            )

    out_img = Image.fromarray(binary)
    out = io.BytesIO()
    out_img.save(out, format="PNG")
    return out.getvalue()


# ---------------------------------------------------------
# PDF → PNG dönüşümü (ham, enhancement öncesi)
# ---------------------------------------------------------
def pdf_to_png(content: bytes, dpi: int = 300) -> bytes:
    images = convert_from_bytes(content, first_page=1, last_page=1, dpi=dpi)
    buf = io.BytesIO()
    images[0].save(buf, format="PNG")
    return buf.getvalue()


def to_png(content: bytes) -> bytes:
    img = Image.open(io.BytesIO(content)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------
# ORTAK İŞLEME FONKSİYONU
# ---------------------------------------------------------
async def process_file(f: UploadFile) -> InvoiceModel:
    raw = await f.read()
    filename = f.filename or ""

    # Adım 1: Ham görüntüyü PNG'ye çevir (QR için — enhancement YOK)
    if filename.lower().endswith(".pdf"):
        raw_png = await run_in_threadpool(pdf_to_png, raw)
    else:
        raw_png = await run_in_threadpool(to_png, raw)

    # Adım 2: QR / Barkod — ham görüntüden oku (enhancement bozar)
    qr_raw = await run_in_threadpool(read_qr_raw, raw_png)
    qr_parsed = parse_qr_data(qr_raw) if qr_raw else {}

    # Adım 3: Enhancement → Super Resolution → OCR
    enhanced = await run_in_threadpool(enhance_image, raw_png)
    ocr_ready = await run_in_threadpool(super_resolve, enhanced)
    text = await run_in_threadpool(run_ocr, ocr_ready)

    parsed = parse_invoice(text)

    # QR verisi parser'ı override eder (daha güvenilir)
    for key in ["total", "date", "time", "invoice_number", "company",
                "vendor", "vat_amount", "vat_rate"]:
        if qr_parsed.get(key):
            parsed[key] = qr_parsed[key]

    needs_review = not parsed.get("total")
    review_reason = "Toplam tutar bulunamadı" if needs_review else None

    invoice_id = add_invoice(parsed, filename)

    return InvoiceModel(
        invoice_id=invoice_id,
        filename=filename,
        raw_text=text,
        qr_raw=qr_raw or None,
        qr_parsed=qr_parsed or None,
        vendor=parsed.get("vendor"),
        date=parsed.get("date"),
        time=parsed.get("time"),
        total=parsed.get("total"),
        vat_amount=parsed.get("vat_amount"),
        vat_rate=parsed.get("vat_rate"),
        invoice_no=parsed.get("invoice_number"),
        category=parsed.get("category"),
        payment_method=parsed.get("payment_method"),
        company_from_qr=parsed.get("company"),
        needs_review=needs_review,
        review_reason=review_reason,
        message="OCR tamamlandı",
    )


# ---------------------------------------------------------
# TEKLI OCR ENDPOINT
# ---------------------------------------------------------
@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    return await process_file(file)


# ---------------------------------------------------------
# COKLU OCR ENDPOINT
# ---------------------------------------------------------
@router.post("/upload-multi")
async def upload_multi(files: List[UploadFile] = File(...)):
    tasks = [process_file(f) for f in files]
    results = await asyncio.gather(*tasks)
    return {
        "count": len(results),
        "invoices": results,
    }

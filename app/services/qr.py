import cv2
import numpy as np
from pdf2image import convert_from_bytes
from PIL import Image
import io
import re
from urllib.parse import urlparse, parse_qs

try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    PYZBAR_AVAILABLE = True
except ImportError:
    PYZBAR_AVAILABLE = False


# ---------------------------------------------------------
# QR / BARKOD OKUMA  (çok katmanlı strateji)
# ---------------------------------------------------------
def _try_cv2_detect(img_cv: np.ndarray) -> str:
    detector = cv2.QRCodeDetector()
    data, bbox, _ = detector.detectAndDecode(img_cv)
    return data or ""


def _try_pyzbar(img_cv: np.ndarray) -> str:
    if not PYZBAR_AVAILABLE:
        return ""
    try:
        results = pyzbar_decode(img_cv)
        for r in results:
            text = r.data.decode("utf-8", errors="ignore")
            if text:
                return text
    except Exception:
        pass
    return ""


def _variants(img_cv: np.ndarray) -> list:
    """Farklı görüntü ön işleme varyantları."""
    variants = [img_cv]

    # Gri ton
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    variants.append(gray)

    # Adaptif eşik
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    variants.append(thresh)

    # 2x büyütme (küçük/uzak QR için)
    h, w = img_cv.shape[:2]
    upscaled = cv2.resize(img_cv, (w * 2, h * 2), interpolation=cv2.INTER_LANCZOS4)
    variants.append(upscaled)

    # Kontrast artırma (CLAHE)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    clahe_img = clahe.apply(gray)
    variants.append(clahe_img)

    # Gürültü temizleme
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    variants.append(denoised)

    return variants


def read_qr_raw(file_bytes: bytes) -> str:
    """
    QR ve barkod okuma.
    Strateji sırası: cv2 → pyzbar
    Her ikisi için de 6 farklı görüntü varyantı denenir.
    """
    if file_bytes[:4] == b'%PDF':
        try:
            images = convert_from_bytes(file_bytes, dpi=300, first_page=1, last_page=3)
            pil_images = images
        except Exception:
            return ""
    else:
        try:
            img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
            pil_images = [img]
        except Exception:
            return ""

    for pil_img in pil_images:
        img_cv = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        for variant in _variants(img_cv):
            # cv2
            result = _try_cv2_detect(variant)
            if result:
                return result
            # pyzbar
            result = _try_pyzbar(variant)
            if result:
                return result

    return ""


# ---------------------------------------------------------
# QR VERİSİ PARSE (URL params / key=value / serbest metin)
# ---------------------------------------------------------
def parse_qr_data(data: str) -> dict:
    if not data:
        return {}

    parsed: dict = {"raw": data}

    # 1) URL formatı: https://example.com?total=100&date=2024-01-01
    if data.startswith("http://") or data.startswith("https://"):
        try:
            qs = parse_qs(urlparse(data).query)
            for key, values in qs.items():
                parsed[key.lower()] = values[0] if len(values) == 1 else values
        except Exception:
            pass
        return parsed

    # 2) key=value satır formatı (e-fatura QR yaygın format)
    #    Total=125.00\nDate=2024-01-15\nVendor=REWE
    kv_pattern = re.findall(r"([A-Za-z_\u0600-\u06FF\uAC00-\uD7A3]+)\s*[=:]\s*([^\n\r;|]+)", data)
    if kv_pattern:
        for key, value in kv_pattern:
            k = key.strip().lower()
            v = value.strip()
            # Alan isimlerini standartlaştır
            k = _normalize_qr_key(k)
            parsed[k] = v
        return parsed

    # 3) Türkiye e-fatura özel format (| ile ayrılmış)
    if "|" in data:
        parts = data.split("|")
        field_map = ["vendor", "tax_no", "date", "time", "total", "vat_amount", "invoice_number"]
        for i, part in enumerate(parts):
            if i < len(field_map):
                parsed[field_map[i]] = part.strip()
        return parsed

    # 4) Noktalı virgülle ayrılmış
    if ";" in data:
        parts = data.split(";")
        for part in parts:
            if "=" in part or ":" in part:
                sep = "=" if "=" in part else ":"
                k, _, v = part.partition(sep)
                parsed[_normalize_qr_key(k.strip().lower())] = v.strip()
        return parsed

    return parsed


def _normalize_qr_key(key: str) -> str:
    mapping = {
        # Total
        "total": "total", "amount": "total", "tutar": "total",
        "betrag": "total", "montant": "total", "المجموع": "total",
        "합계": "total", "总计": "total",
        # Date
        "date": "date", "tarih": "date", "datum": "date",
        "fecha": "date", "تاريخ": "date", "날짜": "date", "日期": "date",
        # Time
        "time": "time", "saat": "time", "zeit": "time",
        "hora": "time", "الوقت": "time", "시간": "time", "时间": "time",
        # Vendor
        "vendor": "vendor", "merchant": "vendor", "satici": "vendor",
        "händler": "vendor", "marchand": "vendor", "البائع": "vendor",
        "판매자": "vendor", "商家": "vendor",
        # Invoice number
        "invoice_number": "invoice_number", "invoice_no": "invoice_number",
        "fatura_no": "invoice_number", "rechnungsnummer": "invoice_number",
        "رقم_الفاتورة": "invoice_number",
        # VAT
        "vat": "vat_amount", "kdv": "vat_amount", "mwst": "vat_amount",
        "tva": "vat_amount", "iva": "vat_amount",
        # Company
        "company": "company", "firma": "company", "شركة": "company",
    }
    return mapping.get(key, key)

import cv2
import numpy as np
from PIL import Image
import io
import re
from urllib.parse import urlparse, parse_qs

try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    PYZBAR_OK = True
except ImportError:
    PYZBAR_OK = False


# --------------------------------------------------------
# VARYANT ÜRETİCİ
# --------------------------------------------------------
def _variants(img_cv: np.ndarray) -> list:
    results = [img_cv]
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    results.append(gray)
    thresh = cv2.adaptiveThreshold(gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    results.append(thresh)
    h, w = img_cv.shape[:2]
    results.append(cv2.resize(img_cv, (w*2, h*2), interpolation=cv2.INTER_LANCZOS4))
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    results.append(clahe.apply(gray))
    results.append(cv2.fastNlMeansDenoising(gray, h=10))
    return results


def _cv2_read(img) -> str:
    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(img)
    return data or ""


def _pyzbar_read(img) -> str:
    if not PYZBAR_OK:
        return ""
    try:
        for r in pyzbar_decode(img):
            t = r.data.decode("utf-8", errors="ignore")
            if t:
                return t
    except Exception:
        pass
    return ""


# --------------------------------------------------------
# ANA OKUMA FONKSİYONU
# --------------------------------------------------------
def read_qr(png_bytes: bytes) -> str:
    """PNG bytes → QR/barkod içeriği (boşsa boş string)"""
    try:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    except Exception:
        return ""

    for v in _variants(img_cv):
        r = _cv2_read(v)
        if r: return r
        r = _pyzbar_read(v)
        if r: return r
    return ""


# --------------------------------------------------------
# QR VERİSİ PARSE
# --------------------------------------------------------
_KEY_MAP = {
    # total
    "total":"total","amount":"total","tutar":"total","betrag":"total",
    "montant":"total","المجموع":"total","합계":"total","总计":"total",
    # date
    "date":"date","tarih":"date","datum":"date","fecha":"date",
    "تاريخ":"date","날짜":"date","日期":"date",
    # time
    "time":"time","saat":"time","zeit":"time","hora":"time",
    "الوقت":"time","시간":"time","时间":"time",
    # vendor
    "vendor":"vendor","merchant":"vendor","satici":"vendor","البائع":"vendor",
    "판매자":"vendor","商家":"vendor","händler":"vendor","marchand":"vendor",
    # invoice_number
    "invoice_number":"invoice_number","invoice_no":"invoice_number",
    "fatura_no":"invoice_number","rechnungsnummer":"invoice_number",
    "رقم_الفاتورة":"invoice_number",
    # vat
    "vat":"vat_amount","kdv":"vat_amount","mwst":"vat_amount",
    "tva":"vat_amount","iva":"vat_amount",
    # company
    "company":"company","firma":"company","شركة":"company",
}


def parse_qr(data: str) -> dict:
    if not data:
        return {}
    result: dict = {"raw": data}

    # URL formatı
    if data.startswith(("http://", "https://")):
        try:
            qs = parse_qs(urlparse(data).query)
            for k, v in qs.items():
                result[_KEY_MAP.get(k.lower(), k.lower())] = v[0] if len(v)==1 else v
        except Exception:
            pass
        return result

    # key=value / key:value
    kv = re.findall(r"([A-Za-z_\u0600-\u06FF\uAC00-\uD7A3\u4E00-\u9FFF]+)\s*[=:]\s*([^\n\r;|]+)", data)
    if kv:
        for k, v in kv:
            result[_KEY_MAP.get(k.strip().lower(), k.strip().lower())] = v.strip()
        return result

    # Türkiye e-fatura pipe formatı
    if "|" in data:
        parts = data.split("|")
        fields = ["vendor","tax_no","date","time","total","vat_amount","invoice_number"]
        for i, p in enumerate(parts):
            if i < len(fields):
                result[fields[i]] = p.strip()
        return result

    return result

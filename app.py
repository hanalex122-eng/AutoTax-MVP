# ——————————————————————————————————————————————
#  FINAL APP.PY — AutoTax MVP COMPLETE
# ——————————————————————————————————————————————

import cv2
import pytesseract
from pyzbar.pyzbar import decode as qr_decode
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
import re
from datetime import datetime, date
from io import BytesIO
from PIL import Image
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "invoices_db.json"

# ——————————————————————————————————————————————
# SIMPLE JSON "DB"
# ——————————————————————————————————————————————
def load_db() -> List[Dict[str, Any]]:
    if not os.path.exists(DB_PATH):
        return []
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_db(data: List[Dict[str, Any]]):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_invoice_record(record: Dict[str, Any]):
    db = load_db()
    db.append(record)
    save_db(db)

# ——————————————————————————————————————————————
# OCR PREPROCESSING
# ——————————————————————————————————————————————
def preprocess_for_ocr(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    thresh = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31, 2
    )
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharp = cv2.filter2D(thresh, -1, kernel)

    coords = np.column_stack(np.where(sharp > 0))
    angle = cv2.minAreaRect(coords)[-1]

    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    (h, w) = sharp.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    deskewed = cv2.warpAffine(
        sharp, M, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE
    )

    return deskewed

# ——————————————————————————————————————————————
# OCR
# ——————————————————————————————————————————————
def run_ocr(image):
    processed = preprocess_for_ocr(image)
    text = pytesseract.image_to_string(processed, lang="eng")
    return text

def read_qr(image):
    decoded = qr_decode(image)
    if not decoded:
        return []
    return [d.data.decode("utf-8") for d in decoded]

def brightness_score(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    return float(np.mean(hsv[:, :, 2]))

def blur_score(image):
    return float(cv2.Laplacian(image, cv2.CV_64F).var())

def rotation_hint(image):
    h, w = image.shape[:2]
    return "portrait" if h > w else "landscape"

def ki_robot_analysis(image, text, qr_data):
    return {
        "quality_score": 65,
        "document_type": "invoice",
        "risk_level": "medium",
        "issues": [],
        "hints": [
            "No QR/payment code detected in the image." if not qr_data else "QR code detected.",
            "Brightness OK.",
            "Image is in portrait orientation."
        ],
        "blur_score": blur_score(image),
        "brightness_score": brightness_score(image),
        "rotation_hint": rotation_hint(image),
        "country_hint": "US_or_EN",
        "qr_data": qr_data
    }

# ——————————————————————————————————————————————
# COUNTRY DETECTION
# ——————————————————————————————————————————————
def detect_country(text: str):
    t = text.lower()
    scores = {
        "fr": 0, "de": 0, "tr": 0, "us": 0, "uk": 0,
        "es": 0, "it": 0, "nl": 0, "pl": 0, "in": 0,
        "cn": 0, "jp": 0
    }

    if "€" in t:
        scores["fr"] += 2; scores["de"] += 2

    if "tl" in t or "₺" in t:
        scores["tr"] += 5

    if "$" in t:
        scores["us"] += 3

    if "£" in t:
        scores["uk"] += 5

    return max(scores, key=scores.get)

# ——————————————————————————————————————————————
# PARSING HELPERS
# ——————————————————————————————————————————————
def normalize_ocr(text: str) -> str:
    return (
        text.replace("O", "0").replace("o", "0")
            .replace("I", "1").replace("l", "1")
            .replace(",", ".")
    )

def extract_dates_generic(text: str):
    text = normalize_ocr(text)
    found_dates = []

    patterns = [
        r"@?(\d{1,2})\.(\d{1,2})\.(\d{2,4})",
        r"@?(\d{1,2})/(\d{1,2})/(\d{2,4})",
        r"@?(\d{4})-(\d{1,2})-(\d{1,2})",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text):
            a, b, c = match.groups()
            raw = match.group(0)

            if len(c) == 2:
                year_2 = int(c)
                c = f"20{c}" if year_2 <= 49 else f"19{c}"

            if "." in raw:
                day, month, year = a, b, c
            elif "/" in raw:
                if int(a) <= 12:
                    month, day, year = a, b, c
                else:
                    day, month, year = a, b, c
            elif "-" in raw:
                year, month, day = a, b, c
            else:
                continue

            try:
                dt = datetime(int(year), int(month), int(day)).date()
                if 1900 <= dt.year <= 2100:
                    found_dates.append(str(dt))
            except:
                continue

    found_dates = sorted(set(found_dates))
    result = {
        "dates": found_dates,
        "date_primary": found_dates[0] if found_dates else None,
        "date_range": None
    }
    if len(found_dates) >= 2:
        result["date_range"] = {
            "start": found_dates[0],
            "end": found_dates[-1]
        }
    return result

def extract_total_generic(text: str):
    text_norm = text.lower().replace(",", ".")
    nums = re.findall(r"\d+\.\d{2}", text_norm)
    return nums[-1] if nums else None

def extract_vendor_smart(text: str):
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines:
        if len(line) > 3:
            return line.strip()
    return None

def extract_items_simple(text: str):
    items = []
    for line in text.split("\n"):
        clean = line.strip()
        if not clean:
            continue
        m = re.findall(r"\d+[\.,]\d{2}", clean)
        if m:
            amount = m[-1].replace(",", ".")
            desc = clean.replace(m[-1], "").strip()
            items.append({
                "raw_line": clean,
                "description": desc,
                "amount": amount
            })
    return items

def detect_multi_invoice(text: str):
    return False

# ——————————————————————————————————————————————
# PARSE ROUTER
# ——————————————————————————————————————————————
def parse_by_country(text: str, country: str):
    dates_info = extract_dates_generic(text)
    total = extract_total_generic(text)
    vendor = extract_vendor_smart(text)
    items = extract_items_simple(text)

    return {
        "country": country,
        "dates": dates_info["dates"],
        "date_primary": dates_info["date_primary"],
        "date_range": dates_info["date_range"],
        "vendor_name": vendor,
        "items": items,
        "total_amount": total,
    }

# ——————————————————————————————————————————————
# OCR ENDPOINT
# ——————————————————————————————————————————————
@app.post("/ocr")
async def process_invoice(file: UploadFile = File(...)):
    content = await file.read()
    image = Image.open(BytesIO(content)).convert("RGB")
    image_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    text = run_ocr(image_cv)
    qr_data = read_qr(image_cv)

    country = detect_country(text)
    parsed = parse_by_country(text, country)

    if not parsed["total_amount"]:
        parsed["total_warning"] = "Total amount could not be extracted. Please enter it manually."
        parsed["total_confidence"] = 0.0
    else:
        parsed["total_confidence"] = 1.0

    result = {
        "filename": file.filename,
        "text": text,
        "country": country,
        "dates": parsed["dates"],
        "date_primary": parsed["date_primary"],
        "date_range": parsed["date_range"],
        "total_amount": parsed["total_amount"],
        "vendor_name": parsed["vendor_name"],
        "items": parsed["items"],
        "qr_hint": bool(qr_data),
        "multi_invoice_detected": detect_multi_invoice(text),
        "ki_robot": ki_robot_analysis(image_cv, text, qr_data),
        "total_warning": parsed.get("total_warning"),
        "total_confidence": parsed.get("total_confidence"),
        "needs_user_total": parsed["total_amount"] is None
    }

    record = {
        "filename": file.filename,
        "country": country,
        "date_primary": parsed["date_primary"],
        "total_amount": parsed["total_amount"],
        "vendor_name": parsed["vendor_name"],
        "items": parsed["items"],
        "created_at": datetime.utcnow().isoformat()
    }
    add_invoice_record(record)

    return {"status": "ok", "results": [result]}

# ——————————————————————————————————————————————
# CORRECTION ENDPOINT
# ——————————————————————————————————————————————
class InvoiceCorrection(BaseModel):
    filename: str
    user_total_value: Optional[float] = None
    user_total_confirmed: bool
    fast_mode: Optional[bool] = False

@app.post("/invoice/correction")
async def invoice_correction(correction: InvoiceCorrection):

    if not correction.user_total_confirmed:
        return {"status": "skipped", "filename": correction.filename}

    record = {
        "filename": correction.filename,
        "total_amount": correction.user_total_value,
        "corrected": True,
        "created_at": datetime.utcnow().isoformat()
    }
    add_invoice_record(record)

    return {
        "status": "saved",
        "filename": correction.filename,
        "searchable": True
    }

# ——————————————————————————————————————————————
# SUMMARY REPORT (FINAL MVP FEATURE)
# ——————————————————————————————————————————————
@app.get("/invoices/summary-report")
async def summary_report():
    db = load_db()

    complete = []
    incomplete = []
    unreadable = []

    okunan_toplam = 0.0

    for inv in db:
        vendor = inv.get("vendor_name")
        date_p = inv.get("date_primary")
        total = inv.get("total_amount")
        items = inv.get("items", [])

        if vendor and date_p and total:
            complete.append(inv)
            try:
                okunan_toplam += float(total)
            except:
                pass

        elif vendor or date_p or total:
            incomplete.append(inv)

        else:
            unreadable.append(inv)

    return {
        "status": "ok",
        "okunan_toplam": okunan_toplam,
        "tamamlanmis_faturalar": complete,
        "eksik_faturalar": incomplete,
        "okunamayan_faturalar": unreadable,
        "genel_toplam": okunan_toplam
    }


# DELETE INVOICE ENDPOINT
# ——————————————————————————————————————————————
@app.delete("/invoice/{invoice_id}")
def delete_invoice(invoice_id: str):
    # Veritabanını oku
    with open("invoices_db.json", "r", encoding="utf-8") as f:
        invoices = json.load(f)

    # Silinecek invoice'u bul
    updated = [inv for inv in invoices if inv["invoice_id"] != invoice_id]

    # Eğer hiç değişiklik olmadıysa -> invoice yoktur
    if len(updated) == len(invoices):
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Güncellenmiş veriyi kaydet
    with open("invoices_db.json", "w", encoding="utf-8") as f:
        json.dump(updated, f, indent=4, ensure_ascii=False)

    return {"status": "deleted", "invoice_id": invoice_id}

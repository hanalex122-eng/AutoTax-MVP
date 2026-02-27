from pdf2image import convert_from_bytes
from PIL import Image, ImageEnhance, ImageFilter
import cv2
import numpy as np
import io
import os

from app.config import settings

if os.path.exists(settings.TESSERACT_CMD) or os.sep in settings.TESSERACT_CMD:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
else:
    import pytesseract

LANG = settings.OCR_LANG
HANDWRITING_CONFIG = "--oem 1 --psm 6"


# --------------------------------------------------------
# SUPER RESOLUTION
# --------------------------------------------------------
_sr_model = None

def _get_sr():
    global _sr_model
    if _sr_model is not None:
        return _sr_model
    try:
        path = settings.SR_MODEL_PATH
        if os.path.exists(path):
            sr = cv2.dnn_superres.DnnSuperResImpl_create()
            sr.readModel(path)
            sr.setModel("espcn", 2)
            _sr_model = sr
    except Exception:
        pass
    return _sr_model


def super_resolve(png_bytes: bytes) -> bytes:
    sr = _get_sr()
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    if sr:
        try:
            cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            result = sr.upsample(cv_img)
            img = Image.fromarray(cv2.cvtColor(result, cv2.COLOR_BGR2RGB))
        except Exception:
            pass
    else:
        w, h = img.size
        img = img.resize((w * 2, h * 2), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


# --------------------------------------------------------
# IMAGE ENHANCEMENT  (OCR optimize, QR için değil)
# --------------------------------------------------------
def enhance_for_ocr(png_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")

    img = ImageEnhance.Contrast(img).enhance(1.5)
    img = ImageEnhance.Brightness(img).enhance(1.1)
    img = ImageEnhance.Sharpness(img).enhance(2.0)
    img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=150, threshold=3))

    cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    gray   = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

    # CLAHE — düzensiz aydınlatma düzeltme
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray  = clahe.apply(gray)

    # Gürültü temizleme
    gray = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)

    # Gamma
    lut  = np.array([((i / 255.0) ** (1.0 / 1.2)) * 255 for i in range(256)], dtype="uint8")
    gray = cv2.LUT(gray, lut)

    # Deskew — metin piksellerini kullan
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 15, 8)
    coords = np.column_stack(np.where(binary < 128))
    if len(coords) > 100:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = 90 + angle
        if abs(angle) > 0.5:
            h, w = binary.shape[:2]
            M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            binary = cv2.warpAffine(binary, M, (w, h),
                                    flags=cv2.INTER_CUBIC,
                                    borderMode=cv2.BORDER_REPLICATE)

    out_img = Image.fromarray(binary)
    out = io.BytesIO()
    out_img.save(out, format="PNG")
    return out.getvalue()


# --------------------------------------------------------
# PDF / IMAGE → RAW PNG  (QR için ham versiyon)
# --------------------------------------------------------
def to_raw_png(content: bytes, filename: str = "") -> bytes:
    if filename.lower().endswith(".pdf") or content[:4] == b"%PDF":
        images = convert_from_bytes(content, first_page=1, last_page=1, dpi=300)
        buf = io.BytesIO()
        images[0].save(buf, format="PNG")
        return buf.getvalue()
    img = Image.open(io.BytesIO(content)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# --------------------------------------------------------
# FULL PIPELINE: raw bytes → OCR-ready bytes
# --------------------------------------------------------
def prepare_for_ocr(raw_png: bytes) -> bytes:
    enhanced = enhance_for_ocr(raw_png)
    return super_resolve(enhanced)

import pytesseract
from PIL import Image
import io

from app.config import settings

pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

LANG   = settings.OCR_LANG
CONFIG = "--oem 1 --psm 6"


def run_ocr(png_bytes: bytes) -> str:
    img = Image.open(io.BytesIO(png_bytes))
    text = pytesseract.image_to_string(img, lang=LANG, config=CONFIG)

    # Çok az metin çıktıysa sparse mod ile tekrar dene (el yazısı)
    if len(text.strip()) < 20:
        text = pytesseract.image_to_string(img, lang=LANG, config="--oem 1 --psm 11")

    return text or ""

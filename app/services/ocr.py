from pdf2image import convert_from_bytes
from PIL import Image
import pytesseract
import io

def run_ocr(file_bytes: bytes) -> str:
    text = ""

    if file_bytes[:4] == b'%PDF':
        images = convert_from_bytes(file_bytes)
    else:
        try:
            img = Image.open(io.BytesIO(file_bytes))
            images = [img]
        except Exception:
            return ""

    for img in images:
        text += pytesseract.image_to_string(img, lang="deu+eng+fra+spa+ara+kor+chi_sim")

    return text

import os
import pytesseract
from PIL import Image
from pdf2image import convert_from_path
import cv2
import numpy as np

# Tesseract config
TESS_CONFIG = "--oem 1 --psm 6"

def preprocess_image(pil_image):
    """
    OCR doğruluğunu artırmak için image temizleme
    """
    img = np.array(pil_image)

    # grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # threshold (binarization)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

    return Image.fromarray(thresh)


def run_ocr(file_path):
    try:
        text_output = ""

        # PDF ise
        if file_path.lower().endswith(".pdf"):
            pages = convert_from_path(
                file_path,
                dpi=200,               # 300 yerine 200 (daha hızlı)
                first_page=1,
                last_page=1            # fiş ise tek sayfa yeterli
            )

            for page in pages:
                processed = preprocess_image(page)
                text = pytesseract.image_to_string(
                    processed,
                    lang="deu+eng",
                    config=TESS_CONFIG
                )
                text_output += text + "\n"

        else:
            img = Image.open(file_path)
            processed = preprocess_image(img)

            text_output = pytesseract.image_to_string(
                processed,
                lang="deu+eng",
                config=TESS_CONFIG
            )

        return text_output

    except Exception as e:
        print("OCR ERROR:", e)
        return ""
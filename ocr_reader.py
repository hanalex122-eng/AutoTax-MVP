import pytesseract
from PIL import Image

# Eğer Tesseract Mannheim farklı bir path'te ise buraya yaz:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def run_ocr(image_path):
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang="deu+eng")

        print("\n--- OCR RAW TEXT ---")
        print(text)
        print("---------------------\n")

        return text

    except Exception as e:
        print("OCR ERROR:", e)
        return ""

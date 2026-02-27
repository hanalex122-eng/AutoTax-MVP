import re

def parse_extras(raw_text: str):
    """
    OCR çıktısındaki 'extra' veya ek ürün kalemlerini yakalar.
    Örnek: 'extra', 'ekstra', 'addon', 'sos', 'sauce', vb.
    """
    extras = []

    # OCR satırlarını al
    lines = raw_text.split("\n")

    # Extra kelimelerini tanımla (genişletilebilir)
    extra_keywords = [
        "extra", "ekstra", "addon", "sos", "sauce", "dip", "ek ürün"
    ]

    for line in lines:
        lower = line.lower()

        # Satırda extra kelimesi var mı?
        if any(keyword in lower for keyword in extra_keywords):
            price = extract_price(line)
            if price is not None:
                extras.append({
                    "name": "extra",
                    "qty": 1,
                    "price": price
                })

    return extras


def extract_price(text: str):
    """
    Satırdaki fiyatı regex ile yakalar.
    Örnek: 8.0, 32.50, 40,50, 12 TL, vb.
    """
    match = re.search(r"(\d+[.,]?\d*)", text)
    if match:
        return float(match.group(1).replace(",", "."))
    return None

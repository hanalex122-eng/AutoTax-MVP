import re
from typing import Optional

PRIORITY_WORDS = [
    # English
    "total", "amount due", "grand total",

    # German
    "gesamt", "gesamtbetrag", "betrag", "summe",
    "endbetrag", "zu zahlen", "brutto",

    # French
    "total ttc", "montant", "payé",

    # Spanish
    "total", "importe", "importe total",

    # Turkish
    "toplam", "genel toplam", "tutar", "ödenecek"
]

money_pattern = r"\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})"


def normalize_amount(value: str) -> Optional[float]:
    """
    1.234,56
    1,234.56
    1234,56
    1234.56
    hepsini doğru parse eder
    """
    value = value.strip()

    if "," in value and "." in value:
        # Hangisi decimal?
        if value.rfind(",") > value.rfind("."):
            # 1.234,56
            value = value.replace(".", "").replace(",", ".")
        else:
            # 1,234.56
            value = value.replace(",", "")
    elif "," in value:
        value = value.replace(",", ".")
    else:
        value = value

    try:
        return float(value)
    except ValueError:
        return None


def extract_total_amount(text: str) -> Optional[float]:
    lines = text.lower().splitlines()

    candidates = []
    priority_candidates = []

    # 🔥 sadece son 40 satır (genelde total altta olur)
    lines = lines[-40:]

    for line in lines:
        matches = re.findall(money_pattern, line)

        for m in matches:
            value = normalize_amount(m)
            if value is None:
                continue

            candidates.append(value)

            if any(word in line for word in PRIORITY_WORDS):
                priority_candidates.append(value)

    # Önce keyword eşleşenler
    if priority_candidates:
        return max(priority_candidates)

    # Yoksa en büyük değer (fallback)
    if candidates:
        return max(candidates)

    return None
import re
from datetime import datetime

# ---------------------------------------------------------
# OCR NORMALIZATION
# ---------------------------------------------------------
def normalize_ocr(text: str) -> str:
    return (
        text.replace("O", "0").replace("o", "0")
            .replace("I", "1").replace("l", "1")
            .replace(",", ".")  # 4,90 → 4.90
    )


# ---------------------------------------------------------
# DATE EXTRACTION (OCR-DOSTU)
# ---------------------------------------------------------
DATE_PATTERNS = [
    r"@?(\d{1,2})\.(\d{1,2})\.(\d{2,4})",
    r"@?(\d{1,2})/(\d{1,2})/(\d{2,4})",
    r"@?(\d{4})-(\d{1,2})-(\d{1,2})",
]

def extract_date(text: str):
    text = normalize_ocr(text)
    found_dates = []

    for pattern in DATE_PATTERNS:
        for match in re.finditer(pattern, text):
            a, b, c = match.groups()
            raw = match.group(0)

            # Yıl düzeltme (ör: 24 → 2024)
            if len(c) == 2:
                year_2 = int(c)
                c = f"20{c}" if year_2 <= 49 else f"19{c}"

            # Almanya formatı dd.mm.yyyy
            if "." in raw:
                day, month, year = a, b, c

            # USA formatı mm/dd/yyyy
            elif "/" in raw:
                if int(a) <= 12:
                    month, day, year = a, b, c
                else:
                    continue

            # ISO formatı yyyy-mm-dd
            elif "-" in raw:
                year, month, day = a, b, c

            # Tarihi doğrula
            try:
                dt = datetime(int(year), int(month), int(day)).date()
                if 1900 <= dt.year <= 2100:
                    found_dates.append(dt)
            except:
                continue

    if not found_dates:
        return None

    return str(max(found_dates))


# ---------------------------------------------------------
# VENDOR EXTRACTION (AKILLI)
# ---------------------------------------------------------
def extract_vendor(text: str) -> str:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    candidates = []

    blacklist_patterns = [
        r"\bIBAN\b", r"\bBIC\b", r"\bUST\b", r"\bMwSt\b",
        r"\bSteuer\b", r"\bRechnung\b", r"\bInvoice\b",
        r"\bKunden\b", r"\bKundennummer\b", r"\bDatum\b",
        r"\bUhrzeit\b", r"\d{5}",  # Posta kodu
    ]

    def is_blacklisted(line):
        return any(re.search(p, line, re.IGNORECASE) for p in blacklist_patterns)

    for line in lines[:10]:
        if len(line) < 3 and not line.isupper():
            continue
        if line.isdigit():
            continue
        if is_blacklisted(line):
            continue
        if any(ext in line.lower() for ext in [".txt", ".html", ".js", ".css"]):
            continue

        candidates.append(line)

    if not candidates:
        return None
    uppercase = [c for c in candidates if c.isupper()]
    if uppercase:
        return max(uppercase, key=len).title()

    no_numbers = [c for c in candidates if not re.search(r"\d", c)]
    if no_numbers:
        return max(no_numbers, key=len).title()

    return max(candidates, key=len).title()


# ---------------------------------------------------------
# ITEM EXTRACTION
# ---------------------------------------------------------
IGNORE_ITEM_KEYWORDS = [
    "datum", "uhrzeit", "zeit", "transaktions",
    "beleg", "mwst", "steuer", "summe", "gesamt",
]

PRICE_REGEX = r'(\d+\.\d{2})\s*€'

def extract_items(text):
    items = []
    lines = text.split("\n")

    for line in lines:
        clean = line.strip()
        if not clean:
            continue

        # Tarih, saat, toplam, vergi gibi satırları item olarak alma
        if any(k in clean.lower() for k in IGNORE_ITEM_KEYWORDS):
            continue

        price_match = re.search(PRICE_REGEX, clean)
        if price_match:
            amount = price_match.group(1)
            description = clean.replace(amount, "").replace("€", "").strip()
            items.append({
                "raw_line": clean,
                "description": description,
                "amount": amount
            })

    return items


# ---------------------------------------------------------
# TOTAL EXTRACTION
# ---------------------------------------------------------
TOTAL_REGEX = r'(gesamt|total|summe|betrag)[^\d]*(\d+\.\d{2})'

def extract_total(text):
    match = re.search(TOTAL_REGEX, text.lower())
    if match:
        return match.group(2)
    return None


# ---------------------------------------------------------
# MAIN PARSER FUNCTION
# ---------------------------------------------------------
def parse_invoice(text):
    text = normalize_ocr(text)

    date_primary = extract_date(text)
    vendor = extract_vendor(text)
    items = extract_items(text)
    total = extract_total(text)

    return {
        "date_primary": date_primary,
        "dates": [date_primary] if date_primary else [],
        "vendor_name": vendor,
        "items": items,
        "total_amount": total
    }


    
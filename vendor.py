import re

def extract_vendor(text: str) -> str:
    """
    Faturadaki mağaza/şirket adını bulur.
    """

    # Satırları temizle
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    candidates = []

    # Vendor olmayan tipik satırları ele
    blacklist_patterns = [
        r"\bIBAN\b",
        r"\bBIC\b",
        r"\bUST\b",
        r"\bUSt\b",
        r"\bVAT\b",
        r"\bMwSt\b",
        r"\bSteuer\b",
        r"\bSteuernummer\b",
        r"\bUSt-IdNr\b",
        r"\bRechnung\b",
        r"\bInvoice\b",
        r"\bKunden\b",
        r"\bKundennummer\b",
        r"\bBestell\b",
        r"\bAuftrag\b",
        r"\bLiefer\b",
        r"\bZahlungsziel\b",
        r"\bNr\b",
        r"\bNo\b",
        r"\bDatum\b",
        r"\bDate\b",
        r"\bTel\b",
        r"\bFax\b",
        r"\bEmail\b",
        r"\bAdresse\b",
        r"\d{5}",  # Posta kodu
    ]

    def is_blacklisted(line):
        return any(re.search(p, line, re.IGNORECASE) for p in blacklist_patterns)

    # İlk 10 satır genelde vendor'a en yakın olanlardır
    for line in lines[:10]:

        # Çok kısa satırları alma (istisna: tamamen büyük harfli kısa marka isimleri)
        if len(line) < 3 and not line.isupper():
            continue

        # Sadece rakam olan satırları alma
        if line.isdigit():
            continue

        # Kara listeye girenleri alma
        if is_blacklisted(line):
            continue

        # Dosya adı çöplüğü olan satırları alma
        if any(ext in line.lower() for ext in [".txt", ".html", ".js", ".css"]):
            continue

        candidates.append(line)

    if not candidates:
        return None

    # 1) Tamamen büyük harf olan satırlar (marka isimleri)
    uppercase_candidates = [c for c in candidates if c.isupper()]
    if uppercase_candidates:
        return max(uppercase_candidates, key=len)

    # 2) İçinde sayı olmayan satırlar (adresleri elemek için)
    no_number_candidates = [c for c in candidates if not re.search(r"\d", c)]
    if no_number_candidates:
        return max(no_number_candidates, key=len)

    # 3) Son çare: en uzun satır
    return max(candidates, key=len)

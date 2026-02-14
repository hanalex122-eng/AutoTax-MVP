import re

def extract_vat(text: str) -> list:
    """
    Faturadaki KDV satırlarını çıkarır.
    Her satır: {"rate": ..., "amount": ...}
    """

    lines = text.split("\n")
    vat_items = []

    # KDV oranı (7%, 19%, 20%, 8%, 1.5% vs.)
    rate_pattern = r"\d{1,2}(?:[.,]\d{1,2})?\s*%"

    # Para formatı
    money_pattern = r"\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})"

    # KDV olmayan satırları elemek için kara liste
    blacklist = [
        "rabatt", "discount", "gutschrift",
        "versand", "shipping", "porto"
    ]

    for line in lines:
        clean = line.strip().lower()

        # Kara liste kontrolü
        if any(word in clean for word in blacklist):
            continue

        # Oranı bul
        rate_match = re.search(rate_pattern, clean)
        if not rate_match:
            continue

        # Satırdaki tüm para değerlerini bul
        amounts = re.findall(money_pattern, clean)
        if not amounts:
            continue

        # Son para değeri genelde KDV tutarıdır
        raw_amount = amounts[-1]

        # Normalize et
        raw_rate = rate_match.group()
        rate = raw_rate.replace("%", "").replace(",", ".").strip()
        amount = raw_amount.replace(".", "").replace(",", ".")

        try:
            rate_val = float(rate)
            amount_val = float(amount)
        except:
            continue

        # Negatif KDV olmaz
        if amount_val < 0:
            continue

        vat_items.append({
            "rate": rate_val,
            "amount": amount_val
        })

    return vat_items

import re

def extract_items(text: str) -> list:
    """
    Faturadaki ürün listesini çıkarır.
    Her ürün: {"name": ..., "price": ...}
    """

    lines = text.split("\n")
    items = []

    # Para formatı (12,99 / 12.99 / 1.299,00)
    price_pattern = r"\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})"

    # Ürün olmayan satırları elemek için kara liste
    blacklist = [
        "summe", "total", "betrag", "brutto", "netto",
        "mwst", "ust", "steuer", "rabatt", "discount",
        "zahlung", "versand", "shipping"
    ]

    for line in lines:
        clean = line.strip().lower()

        # Kara liste kontrolü
        if any(word in clean for word in blacklist):
            continue

        # Fiyatları bul
        prices = re.findall(price_pattern, clean)
        if not prices:
            continue

        # Son fiyat genelde ürün fiyatıdır
        raw_price = prices[-1]

        # Normalize et
        normalized = raw_price.replace(".", "").replace(",", ".")
        try:
            price = float(normalized)
        except:
            continue

        # Negatif fiyatları alma
        if price < 0:
            continue

        # Ürün adı: satırdan fiyatı çıkar
        name = line.replace(raw_price, "").strip()

        # Ürün adı içindeki diğer fiyatları da temizle
        for p in prices[:-1]:
            name = name.replace(p, "").strip()

        # Çok kısa isimleri alma
        if len(name) < 2:
            continue

        items.append({
            "name": name,
            "price": price
        })

    return items

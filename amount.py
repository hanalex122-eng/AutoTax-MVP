import re

def extract_total_amount(text: str) -> float:
    """
    Faturadaki toplam tutarı bulur.
    """

    money_pattern = r"\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})"

    priority_words = [
        "total", "summe", "betrag", "brutto",
        "zu zahlen", "payé", "montant", "ttc"
    ]

    candidates = []
    keyword_candidates = []

    for line in text.split("\n"):
        amounts = re.findall(money_pattern, line)
        for amt in amounts:
            normalized = amt.replace(".", "").replace(",", ".")
            try:
                value = float(normalized)
                candidates.append(value)

                # Anahtar kelime varsa bu satırdaki değerleri ayrı topla
                if any(word in line.lower() for word in priority_words):
                    keyword_candidates.append(value)

            except:
                pass

    if keyword_candidates:
        return max(keyword_candidates)

    return max(candidates) if candidates else None

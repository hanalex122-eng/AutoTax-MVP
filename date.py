import re
from datetime import datetime

# OCR'de görülen tüm tarih formatlarını destekler
DATE_PATTERNS = [
    r"@?(\d{1,2})\.(\d{1,2})\.(\d{2,4})",       # 10.02.2026  /  @5.11.2024
    r"@?(\d{1,2})/(\d{1,2})/(\d{2,4})",         # 02/10/2026  /  @02/10/26
    r"@?(\d{4})-(\d{1,2})-(\d{1,2})",           # 2026-02-10  /  @2026-02-10
]

def normalize_ocr(text: str) -> str:
    """
    OCR hatalarını düzeltir.
    """
    return (
        text.replace("O", "0").replace("o", "0")
            .replace("I", "1").replace("l", "1")
            .replace(",", ".")  # 4,90 → 4.90
    )

def extract_date(text: str):
    """
    Metindeki en mantıklı tarihi bulur ve ISO formatında döndürür (YYYY-MM-DD).
    """
    text = normalize_ocr(text)
    found_dates = []

    for pattern in DATE_PATTERNS:
        for match in re.finditer(pattern, text):
            parts = match.groups()
            raw = match.group(0)

            # Parçaları al
            a, b, c = parts

            # Yıl düzeltme (ör: 24 → 2024)
            if len(c) == 2:
                year_2 = int(c)
                c = f"20{c}" if year_2 <= 49 else f"19{c}"

            # Almanya formatı dd.mm.yyyy
            if "." in raw:
                day, month, year = a, b, c

            # USA formatı mm/dd/yyyy (sadece ay <= 12 ise)
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

                # Mantıksız yılları ele
                if 1900 <= dt.year <= 2100:
                    found_dates.append(dt)

            except:
                continue

    if not found_dates:
        return None

    # Birden fazla tarih varsa en mantıklı olanı seç → en yeni tarih
    return str(max(found_dates))

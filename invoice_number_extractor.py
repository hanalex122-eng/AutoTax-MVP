import re

# Fatura numarası için çoklu desen (Avrupa + İngilizce + Türkçe)
invoice_patterns = [
    r"(?:Rechnung(?:s)?nummer|Rechnung\s*Nr|Rg\.?-?Nr|RgNr|Rgnr)\s*[:\-]?\s*([A-Za-z0-9\-\/\.]+)",
    r"(?:Invoice\s*No|Invoice\s*Number|Inv\s*No)\s*[:\-]?\s*([A-Za-z0-9\-\/\.]+)",
    r"(?:Faktura\s*Nr|Faktura\s*No)\s*[:\-]?\s*([A-Za-z0-9\-\/\.]+)",
    r"(?:Bill\s*No|Bill\s*Number)\s*[:\-]?\s*([A-Za-z0-9\-\/\.]+)",
    r"(?:No\.?|Nr\.?)\s*[:\-]?\s*([A-Za-z0-9\-\/\.]+)"
]

def extract_invoice_number(text: str):
    """
    PDF veya OCR metninden fatura numarasını çıkarır.
    Eşleşme bulunamazsa None döner.
    """
    for pattern in invoice_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None

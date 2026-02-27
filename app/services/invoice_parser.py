import re
from typing import Optional


def normalize(text: str) -> str:
    text = re.sub(r"[^\x20-\x7E\u0600-\u06FF\uAC00-\uD7A3\u4E00-\u9FFF\u3400-\u4DBF]+", " ", text)
    text = re.sub(r"[\u0617-\u061A\u064B-\u0652]", "", text)
    for w, c in {
        "TOT A L":"TOTAL","T0TAL":"TOTAL","TO TAL":"TOTAL",
        "INV01CE":"INVOICE","INVO1CE":"INVOICE",
        "rew e":"rewe","rew3":"rewe","lidi":"lidl","aldo":"aldi",
        "mlgros":"migros","m1gros":"migros","carref0ur":"carrefour",
    }.items():
        text = text.replace(w, c)
    text = re.sub(r"2n[z0-9b](\d)", r"202\1", text)
    return re.sub(r"\s+", " ", text).strip()


# ─── TOTAL (öncelikli label'lı eşleşmeleri tercih et) ────
def parse_total(text: str) -> Optional[float]:
    t  = normalize(text)
    ar = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    t  = t.translate(ar)

    # Tier 1 — açık "grand total / toplam / gesamt" etiketi (en güvenilir)
    tier1 = [
        r"(?:grand total|total ttc|net à payer|amount due|amount paid)\s*[:\-]?\s*([\d.,]+)",
        r"(?:gesamtbetrag|gesamt|endbetrag|zu zahlen)\s*[:\-]?\s*([\d.,]+)",
        r"(?:genel toplam|ödenecek tutar|odenecek tutar)\s*[:\-]?\s*([\d.,]+)",
        r"(?:المجموع الإجمالي|الإجمالي المستحق)\s*[:\-]?\s*([\d.,٠-٩]+)",
        r"(?:총합계|결제금액)\s*[:\-]?\s*([\d.,]+)",
        r"(?:应付金额|實付金額)\s*[:\-]?\s*([\d.,]+)",
    ]
    # Tier 2 — genel "total / tutar / 합계" etiketi
    tier2 = [
        r"(?:total|subtotal|amount)\s*[:\-]?\s*([\d.,]+)",
        r"(?:toplam|tutar|ara toplam)\s*[:\-]?\s*([\d.,]+)",
        r"(?:summe|betrag|montant|importe)\s*[:\-]?\s*([\d.,]+)",
        r"(?:المجموع|الإجمالي)\s*[:\-]?\s*([\d.,٠-٩]+)",
        r"(?:합계|총액)\s*[:\-]?\s*([\d.,]+)",
        r"(?:总计|合计)\s*[:\-]?\s*([\d.,]+)",
    ]
    # Tier 3 — para birimi öneki/soneki (en az güvenilir)
    tier3 = [
        r"([\d.,]+)\s?(?:USD|EUR|GBP|SAR|AED|EGP|TRY|TL|KRW|CNY|₺|€|£|\$|₩|¥|﷼)",
    ]

    def _extract(patterns):
        for p in patterns:
            for m in re.findall(p, t, re.IGNORECASE):
                raw = str(m).translate(ar)
                try:
                    val = float(raw.replace(",", ".")) if not re.search(r"\d{1,3}\.\d{3},\d{2}$", raw) \
                          else float(raw.replace(".", "").replace(",", "."))
                    if 0 < val < 10_000_000:
                        return val
                except ValueError:
                    pass
        return None

    return _extract(tier1) or _extract(tier2) or _extract(tier3)


# ─── DATE ─────────────────────────────────────────────────
MONTHS = {
    "january":1,"jan":1,"february":2,"feb":2,"march":3,"mar":3,
    "april":4,"apr":4,"may":5,"june":6,"jun":6,"july":7,"jul":7,
    "august":8,"aug":8,"september":9,"sep":9,"october":10,"oct":10,
    "november":11,"nov":11,"december":12,"dec":12,
    "januar":1,"februar":2,"märz":3,"maerz":3,"mai":5,"juni":6,
    "juli":7,"oktober":10,"dezember":12,
    "janvier":1,"fevrier":2,"février":2,"mars":3,"avril":4,
    "juin":6,"juillet":7,"aout":8,"août":8,"septembre":9,
    "octobre":10,"novembre":11,"decembre":12,"décembre":12,
    "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,
    "junio":6,"julio":7,"agosto":8,"septiembre":9,"octubre":10,
    "noviembre":11,"diciembre":12,
    "ocak":1,"şubat":2,"subat":2,"mart":3,"nisan":4,"mayıs":5,"mayis":5,
    "haziran":6,"temmuz":7,"ağustos":8,"agustos":8,"eylül":9,"eylul":9,
    "ekim":10,"kasım":11,"kasim":11,"aralık":12,"aralik":12,
    "يناير":1,"فبراير":2,"مارس":3,"أبريل":4,"ابريل":4,"مايو":5,
    "يونيو":6,"يوليو":7,"أغسطس":8,"اغسطس":8,"سبتمبر":9,
    "أكتوبر":10,"اكتوبر":10,"نوفمبر":11,"ديسمبر":12,
}


def parse_date(text: str) -> Optional[str]:
    ar = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    t  = normalize(text).translate(ar)

    m = re.search(r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})", t)
    if m: return m.group(1).replace(".", "-").replace("/", "-")

    m = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", t)
    if m: y,mo,d=m.groups(); return f"{y}-{int(mo):02d}-{int(d):02d}"

    m = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", t)
    if m: y,mo,d=m.groups(); return f"{y}-{int(mo):02d}-{int(d):02d}"

    m = re.search(r"(\d{1,2})\s+([\u0600-\u06FF]+)\s+(\d{4})", t)
    if m:
        d,mw,y=m.groups()
        if mw in MONTHS: return f"{y}-{MONTHS[mw]:02d}-{int(d):02d}"

    m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", t)
    if m:
        d,mo,y=m.groups()
        try: return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        except ValueError: pass

    m = re.search(r"(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(\d{4})", t)
    if m:
        d,mw,y=m.groups()
        if mw.lower() in MONTHS: return f"{y}-{MONTHS[mw.lower()]:02d}-{int(d):02d}"

    return None


def parse_time(text: str) -> Optional[str]:
    m = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?)", normalize(text))
    return m.group(1) if m else None


# ─── VENDOR ───────────────────────────────────────────────
VENDORS = [
    "rewe","lidl","edeka","aldi","kaufland","penny","rossmann","dm","netto",
    "real","globus","tegut","norma",
    "carrefour","auchan","intermarche","casino","monoprix","leclerc","franprix",
    "mercadona","dia","eroski","el corte ingles",
    "migros","bim","a101","şok","sok","carrefoursa",
    "이마트","롯데마트","홈플러스","세븐일레븐",
    "沃尔玛","家乐福","华润万家","大润发",
    "كارفور","لولو","بنده",
    "starbucks","mcdonald","burger king","kfc","subway","dominos","pizza hut",
    "shell","esso","aral","bp","opet","petrol ofisi",
    "mediamarkt","saturn","zara","h&m","c&a","primark",
]
_VFIX = {"rew e":"rewe","rew3":"rewe","lidi":"lidl","aldo":"aldi","mlgros":"migros","m1gros":"migros"}


def parse_vendor(text: str) -> Optional[str]:
    t = text.lower()
    for w, c in _VFIX.items(): t = t.replace(w, c)
    for v in VENDORS:
        if v in t:
            return v.upper() if len(v) <= 4 else v.title()
    # İlk büyük harf satırı (OCR başlığı genellikle firma adıdır)
    for line in text.split("\n"):
        cl = line.strip()
        if cl.isupper() and 3 < len(cl) < 50 and not re.match(r"^\d", cl):
            return cl
    return None


def parse_invoice_number(text: str) -> Optional[str]:
    t = normalize(text)
    for p in [
        r"invoice\s*(?:no|number|#)\s*[:\-]?\s*([A-Za-z0-9\-\/\.]{3,30})",
        r"rechnungs?(?:nummer|nr|no)\.?\s*[:\-]?\s*([A-Za-z0-9\-\/\.]{3,30})",
        r"(?:facture|n°\s*facture)\s*[:\-]?\s*([A-Za-z0-9\-\/\.]{3,30})",
        r"fatura\s*(?:no|nr|numarası)\s*[:\-]?\s*([A-Za-z0-9\-\/\.]{3,30})",
        r"(?:رقم\s*الفاتورة)\s*[:\-]?\s*([A-Za-z0-9\-\/٠-٩]{3,30})",
        r"(?:영수증\s*번호|청구서\s*번호)\s*[:\-]?\s*([A-Za-z0-9\-\/]{3,30})",
        r"(?:发票号码|发票编号)\s*[:\-]?\s*([A-Za-z0-9\-\/]{3,30})",
        r"(?:no|nr|#)\s*[:\-]?\s*([A-Za-z0-9\-\/\.]{4,20})",
    ]:
        m = re.search(p, t, re.IGNORECASE)
        if m: return m.group(1)
    return None


# ─── VAT ──────────────────────────────────────────────────
COMMON_VAT_RATES = {5, 7, 8, 10, 12, 16, 18, 19, 20, 21, 22, 23, 25}


def parse_vat_rate(text: str) -> Optional[int]:
    t = normalize(text)
    # Önce etiketli arama
    for p in [
        r"(?:vat|kdv|mwst|tva|iva|gst|부가세|增值税)\s*(?:rate|oranı|satz|taux|tasa)?\s*[:\-]?\s*(\d{1,2})\s?%",
        r"(\d{1,2})\s?%\s*(?:vat|kdv|mwst|tva|iva|gst)",
    ]:
        m = re.search(p, t, re.IGNORECASE)
        if m:
            v = int(m.group(1))
            if 0 < v <= 30: return v
    # Fallback: sadece bilinen KDV oranlarına eşleş
    for m in re.finditer(r"(\d{1,2})\s?%", t):
        v = int(m.group(1))
        if v in COMMON_VAT_RATES:
            return v
    return None


def parse_vat_amount(text: str) -> Optional[float]:
    ar = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    t  = normalize(text).translate(ar)
    for p in [
        # Yüzde işareti olmayan tutar (19% sonrasındaki asıl KDV tutarı)
        r"(?:vat|kdv|mwst|tva|iva|gst)\s*\d{0,2}%?\s*[:\-]?\s*([\d.,]+(?!\s?%))",
        r"(?:ضريبة القيمة المضافة|الضريبة)\s*[:\-]?\s*([\d.,]+)",
        r"(?:부가세|부가가치세)\s*[:\-]?\s*([\d.,]+)",
        r"(?:增值税|税额)\s*[:\-]?\s*([\d.,]+)",
    ]:
        for raw in re.findall(p, t, re.IGNORECASE):
            try:
                v = float(raw.replace(",", "."))
                if v > 0 and v < 1_000_000:
                    return v
            except ValueError:
                pass
    return None


# ─── CATEGORY ─────────────────────────────────────────────
CATS = {
    "food":        ["restaurant","food","meal","yemek","essen","مطعم","식당","餐厅","café","cafe"],
    "grocery":     ["market","supermarket","grocery","supermarkt","lebensmittel","بقالة","마트","超市"],
    "transport":   ["taxi","uber","transport","bus","bahn","metro","ulaşım","سيارة أجرة","택시","地铁"],
    "fuel":        ["fuel","benzin","diesel","petrol","tankstelle","akaryakıt","وقود","주유","加油"],
    "hotel":       ["hotel","otel","accommodation","motel","hostel","فندق","호텔","酒店"],
    "health":      ["pharmacy","apotheke","eczane","hospital","clinic","صيدلية","약국","药店"],
    "electronics": ["mediamarkt","saturn","electronic","elektro","إلكترونيات","전자","电器"],
    "clothing":    ["zara","h&m","primark","fashion","kleidung","giyim","ملابس","패션","服装"],
}


def parse_category(text: str) -> Optional[str]:
    t = normalize(text).lower()
    for cat, kws in CATS.items():
        if any(kw in t for kw in kws):
            return cat
    return None


def parse_payment_method(text: str) -> Optional[str]:
    t = normalize(text).lower()
    for method, kws in [
        ("visa",       ["visa"]),
        ("mastercard", ["mastercard","master card"]),
        ("amex",       ["amex","american express"]),
        ("maestro",    ["maestro"]),
        ("girocard",   ["girocard","ec-karte","ec karte"]),
        ("paypal",     ["paypal"]),
        ("apple_pay",  ["apple pay"]),
        ("google_pay", ["google pay"]),
        ("cash",       ["cash","nakit","نقدا","현금","现金"]),
        ("card",       ["kart","card","بطاقة","카드","刷卡"]),
    ]:
        if any(kw in t for kw in kws): return method
    return None


def parse_invoice(text: str) -> dict:
    return {
        "vendor":         parse_vendor(text),
        "date":           parse_date(text),
        "time":           parse_time(text),
        "total":          parse_total(text),
        "invoice_number": parse_invoice_number(text),
        "vat_rate":       parse_vat_rate(text),
        "vat_amount":     parse_vat_amount(text),
        "category":       parse_category(text),
        "payment_method": parse_payment_method(text),
    }

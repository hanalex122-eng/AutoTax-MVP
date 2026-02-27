from fastapi import APIRouter, Query
from datetime import date
from typing import Optional
import json
from pathlib import Path

router = APIRouter(prefix="/stats", tags=["Stats"])

DB_PATH = Path("storage/invoices_db.json")


def load_all() -> list:
    if not DB_PATH.exists():
        return []
    try:
        with DB_PATH.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict) and "invoices" in raw:
            return raw["invoices"]
        return []
    except Exception:
        return []


def get_data(inv: dict) -> dict:
    return inv.get("data") or inv.get("parsed") or {}


def safe_total(inv: dict) -> float:
    try:
        return float(get_data(inv).get("total") or 0)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------
# GET /stats/total — Tüm faturaların toplam tutarı
# ---------------------------------------------------------
@router.get("/total")
def total_sum():
    invoices = load_all()
    total = sum(safe_total(inv) for inv in invoices)
    return {
        "count": len(invoices),
        "total_sum": round(total, 2)
    }


# ---------------------------------------------------------
# GET /stats/by-date — Tarih aralığına göre filtrele
# ---------------------------------------------------------
@router.get("/by-date")
def by_date(
    start: date = Query(..., description="Başlangıç tarihi YYYY-MM-DD"),
    end: date = Query(..., description="Bitiş tarihi YYYY-MM-DD")
):
    invoices = load_all()
    filtered = []
    for inv in invoices:
        d_str = get_data(inv).get("date")
        if not d_str:
            continue
        try:
            d = date.fromisoformat(str(d_str)[:10])
        except ValueError:
            continue
        if start <= d <= end:
            filtered.append(inv)

    return {
        "start": str(start),
        "end": str(end),
        "count": len(filtered),
        "total_sum": round(sum(safe_total(i) for i in filtered), 2),
        "invoices": filtered
    }


# ---------------------------------------------------------
# GET /stats/by-vendor — Firma adına göre filtrele
# ---------------------------------------------------------
@router.get("/by-vendor")
def by_vendor(vendor: str = Query(..., description="Firma adı, örn: LIDL, REWE")):
    invoices = load_all()
    filtered = [
        inv for inv in invoices
        if vendor.lower() in (get_data(inv).get("vendor") or "").lower()
    ]
    return {
        "vendor": vendor,
        "count": len(filtered),
        "total_sum": round(sum(safe_total(i) for i in filtered), 2),
        "invoices": filtered
    }


# ---------------------------------------------------------
# GET /stats/by-category — Kategoriye göre filtrele
# ---------------------------------------------------------
@router.get("/by-category")
def by_category(category: str = Query(..., description="food, grocery, transport, fuel, hotel, health, electronics, clothing")):
    invoices = load_all()
    filtered = [
        inv for inv in invoices
        if (get_data(inv).get("category") or "").lower() == category.lower()
    ]
    return {
        "category": category,
        "count": len(filtered),
        "total_sum": round(sum(safe_total(i) for i in filtered), 2),
        "invoices": filtered
    }


# ---------------------------------------------------------
# GET /stats/by-invoice-no — Fatura numarasına göre ara
# ---------------------------------------------------------
@router.get("/by-invoice-no")
def by_invoice_no(invoice_no: str = Query(..., description="Fatura numarası")):
    invoices = load_all()
    filtered = [
        inv for inv in invoices
        if invoice_no.lower() in (get_data(inv).get("invoice_number") or "").lower()
    ]
    return {
        "invoice_no": invoice_no,
        "count": len(filtered),
        "invoices": filtered
    }


# ---------------------------------------------------------
# GET /stats/by-payment — Ödeme yöntemine göre filtrele
# ---------------------------------------------------------
@router.get("/by-payment")
def by_payment(method: str = Query(..., description="visa, mastercard, cash, card, paypal ...")):
    invoices = load_all()
    filtered = [
        inv for inv in invoices
        if (get_data(inv).get("payment_method") or "").lower() == method.lower()
    ]
    return {
        "payment_method": method,
        "count": len(filtered),
        "total_sum": round(sum(safe_total(i) for i in filtered), 2),
        "invoices": filtered
    }


# ---------------------------------------------------------
# GET /stats/summary — Tüm parametrelerle kombine sorgulama
# ---------------------------------------------------------
@router.get("/summary")
def summary(
    start: Optional[date] = Query(None, description="Başlangıç tarihi YYYY-MM-DD"),
    end: Optional[date] = Query(None, description="Bitiş tarihi YYYY-MM-DD"),
    vendor: Optional[str] = Query(None, description="Firma adı"),
    category: Optional[str] = Query(None, description="Kategori"),
    payment_method: Optional[str] = Query(None, description="Ödeme yöntemi"),
    invoice_no: Optional[str] = Query(None, description="Fatura numarası"),
    min_amount: Optional[float] = Query(None, description="Minimum tutar"),
    max_amount: Optional[float] = Query(None, description="Maksimum tutar"),
):
    invoices = load_all()
    filtered = []

    for inv in invoices:
        data = get_data(inv)

        if start or end:
            d_str = data.get("date")
            if not d_str:
                continue
            try:
                d = date.fromisoformat(str(d_str)[:10])
            except ValueError:
                continue
            if start and d < start:
                continue
            if end and d > end:
                continue

        if vendor and vendor.lower() not in (data.get("vendor") or "").lower():
            continue

        if category and (data.get("category") or "").lower() != category.lower():
            continue

        if payment_method and (data.get("payment_method") or "").lower() != payment_method.lower():
            continue

        if invoice_no and invoice_no.lower() not in (data.get("invoice_number") or "").lower():
            continue

        t = safe_total(inv)
        if min_amount is not None and t < min_amount:
            continue
        if max_amount is not None and t > max_amount:
            continue

        filtered.append(inv)

    vendor_totals: dict = {}
    category_totals: dict = {}
    for inv in filtered:
        data = get_data(inv)
        v = (data.get("vendor") or "unknown").lower()
        c = (data.get("category") or "unknown").lower()
        vendor_totals[v] = round(vendor_totals.get(v, 0) + safe_total(inv), 2)
        category_totals[c] = round(category_totals.get(c, 0) + safe_total(inv), 2)

    return {
        "count": len(filtered),
        "total_sum": round(sum(safe_total(i) for i in filtered), 2),
        "by_vendor": vendor_totals,
        "by_category": category_totals,
        "invoices": filtered
    }

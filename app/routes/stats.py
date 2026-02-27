from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from datetime import date
from typing import Optional
import time
import io
import csv

from app.services.invoice_db import query_invoices, iter_rows, get_data, safe_float, get_review_queue

router = APIRouter(prefix="/stats", tags=["Stats"])

# ─── Basit in-memory cache (60 sn TTL) ───────────────────
_cache: dict = {}
_CACHE_TTL = 60


def _cache_key(*args) -> str:
    return str(args)


def _cached(key: str, fn):
    now = time.time()
    if key in _cache and now - _cache[key]["ts"] < _CACHE_TTL:
        return _cache[key]["data"]
    result = fn()
    _cache[key] = {"ts": now, "data": result}
    return result


def _invalidate():
    _cache.clear()


# ─── GET /stats/total ─────────────────────────────────────
@router.get("/total")
def total():
    def _calc():
        r = query_invoices(per_page=1)
        return {
            "count":       r["count"],
            "total_sum":   r["total_sum"],
            "vat_sum":     r["vat_sum"],
            "by_vendor":   r["by_vendor"],
            "by_category": r["by_category"],
        }
    return _cached("total", _calc)


# ─── GET /stats/summary  (kombine filtre + pagination) ────
@router.get("/summary")
def summary(
    start:      Optional[date]  = Query(None),
    end:        Optional[date]  = Query(None),
    vendor:     Optional[str]   = Query(None, max_length=100),
    category:   Optional[str]   = Query(None, max_length=50),
    payment:    Optional[str]   = Query(None, max_length=50),
    invoice_no: Optional[str]   = Query(None, max_length=100),
    min_amount: Optional[float] = Query(None, ge=0),
    max_amount: Optional[float] = Query(None, ge=0),
    page:       int             = Query(1, ge=1),
    per_page:   int             = Query(100, ge=1, le=500),
):
    r = query_invoices(
        start=str(start) if start else None,
        end=str(end) if end else None,
        vendor=vendor,
        category=category,
        payment=payment,
        invoice_no=invoice_no,
        min_amt=min_amount,
        max_amt=max_amount,
        page=page,
        per_page=per_page,
    )
    return r


# ─── GET /stats/by-date ───────────────────────────────────
@router.get("/by-date")
def by_date(
    start:    date = Query(...),
    end:      date = Query(...),
    page:     int  = Query(1, ge=1),
    per_page: int  = Query(100, ge=1, le=500),
):
    r = query_invoices(start=str(start), end=str(end), page=page, per_page=per_page)
    return {"start": str(start), "end": str(end), **r}


# ─── GET /stats/by-vendor ─────────────────────────────────
@router.get("/by-vendor")
def by_vendor(
    vendor:   str = Query(..., max_length=100),
    page:     int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
):
    r = query_invoices(vendor=vendor, page=page, per_page=per_page)
    return {"vendor": vendor, **r}


# ─── GET /stats/by-category ───────────────────────────────
@router.get("/by-category")
def by_category(
    category: str = Query(..., max_length=50),
    page:     int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
):
    r = query_invoices(category=category, page=page, per_page=per_page)
    return {"category": category, **r}


# ─── GET /stats/by-payment ────────────────────────────────
@router.get("/by-payment")
def by_payment(
    method:   str = Query(..., max_length=50),
    page:     int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
):
    r = query_invoices(payment=method, page=page, per_page=per_page)
    return {"payment_method": method, **r}


# ─── GET /stats/by-invoice-no ─────────────────────────────
@router.get("/by-invoice-no")
def by_invoice_no(invoice_no: str = Query(..., max_length=100)):
    r = query_invoices(invoice_no=invoice_no, per_page=200)
    return {"invoice_no": invoice_no, "count": r["count"], "invoices": r["invoices"]}


# ─── GET /stats/export/excel  ─────────────────────────────
# openpyxl write_only = streaming writer — RAM sabit (N→∞)
# Excel hard limit: 1.048.576 satır → aşıldığında CSV önerilir
_EXCEL_ROW_LIMIT = 1_048_575  # başlık satırı hariç

@router.get("/export/excel")
def export_excel(
    start:      Optional[date]  = Query(None),
    end:        Optional[date]  = Query(None),
    vendor:     Optional[str]   = Query(None, max_length=100),
    category:   Optional[str]   = Query(None, max_length=50),
    min_amount: Optional[float] = Query(None, ge=0),
    max_amount: Optional[float] = Query(None, ge=0),
):
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "openpyxl kurulu değil"}, status_code=500)

    kwargs = dict(
        start=str(start) if start else None,
        end=str(end) if end else None,
        vendor=vendor,
        category=category,
        min_amt=min_amount,
        max_amt=max_amount,
    )

    # write_only: satırlar disk'e akış halinde yazılır, tüm workbook RAM'de tutulmaz
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet("Faturalar")

    headers = ["ID", "Dosya", "Firma", "Tarih", "Saat", "Tutar", "KDV%",
               "KDV Tutarı", "Fatura No", "Kategori", "Ödeme", "QR", "Timestamp"]

    hdr_fill = PatternFill("solid", fgColor="2563EB")
    hdr_font = Font(color="FFFFFF", bold=True, size=11)
    hdr_cells = []
    for h in headers:
        cell = openpyxl.cell.WriteOnlyCell(ws, value=h)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal="center")
        hdr_cells.append(cell)
    ws.append(hdr_cells)

    written = 0
    truncated = False
    for row in iter_rows(**kwargs):
        if written >= _EXCEL_ROW_LIMIT:
            truncated = True
            break
        ws.append([
            row["id"] or "", row["filename"] or "",
            row["vendor"] or "", row["date"] or "", row["time"] or "",
            row["total"] or 0, row["vat_rate"] or "",
            row["vat_amount"] or 0, row["invoice_number"] or "",
            row["category"] or "", row["payment_method"] or "",
            (row["qr_raw"] or "")[:200], row["timestamp"] or "",
        ])
        written += 1

    if truncated:
        note = openpyxl.cell.WriteOnlyCell(ws, value=(
            f"⚠ Excel limiti: ilk {_EXCEL_ROW_LIMIT:,} satır gösterildi. "
            f"Tüm veri için /stats/export/csv kullanın."
        ))
        note.font = Font(bold=True, color="FF0000")
        ws.append([note])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="autotax_faturalar.xlsx"'},
    )


# ─── GET /stats/export/csv  (true streaming, sınır yok) ───
@router.get("/export/csv")
def export_csv(
    start:      Optional[date]  = Query(None),
    end:        Optional[date]  = Query(None),
    vendor:     Optional[str]   = Query(None, max_length=100),
    category:   Optional[str]   = Query(None, max_length=50),
    payment:    Optional[str]   = Query(None, max_length=50),
    min_amount: Optional[float] = Query(None, ge=0),
    max_amount: Optional[float] = Query(None, ge=0),
):
    """HTTP chunked streaming CSV — 100M satırda RAM kullanımı sabit (~2 MB)."""

    kwargs = dict(
        start=str(start) if start else None,
        end=str(end) if end else None,
        vendor=vendor,
        category=category,
        payment=payment,
        min_amt=min_amount,
        max_amt=max_amount,
    )

    def _gen():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["ID", "Dosya", "Firma", "Tarih", "Saat", "Tutar",
                         "KDV%", "KDV_Tutar", "Fatura_No", "Kategori",
                         "Odeme", "QR", "Timestamp"])
        yield buf.getvalue()

        for row in iter_rows(**kwargs):
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow([
                row["id"] or "", row["filename"] or "",
                row["vendor"] or "", row["date"] or "", row["time"] or "",
                row["total"] or 0, row["vat_rate"] or "",
                row["vat_amount"] or 0, row["invoice_number"] or "",
                row["category"] or "", row["payment_method"] or "",
                (row["qr_raw"] or "")[:200], row["timestamp"] or "",
            ])
            yield buf.getvalue()

    return StreamingResponse(
        _gen(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="autotax_faturalar.csv"',
            "X-Content-Type-Options": "nosniff",
        },
    )


# ─── GET /stats/export/review-queue-excel  (sadece inceleme bekleyenler) ───
@router.get("/export/review-queue-excel")
def export_review_queue_excel():
    """needs_review=1 olan faturaları Excel olarak indir."""
    try:
        import openpyxl
        from openpyxl.styles import PatternFill, Font, Alignment
    except ImportError:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "openpyxl kurulu değil"}, status_code=500)

    from datetime import date as _date
    today = _date.today().isoformat()

    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet("İnceleme Bekleyenler")

    headers = ["ID", "Dosya", "Firma", "Tarih", "Saat", "Tutar", "KDV%",
               "KDV Tutarı", "Fatura No", "Kategori", "Ödeme", "İnceleme Nedeni", "Timestamp"]

    hdr_fill = PatternFill("solid", fgColor="DC2626")
    hdr_font = Font(color="FFFFFF", bold=True, size=11)
    hdr_cells = []
    for h in headers:
        cell = openpyxl.cell.WriteOnlyCell(ws, value=h)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal="center")
        hdr_cells.append(cell)
    ws.append(hdr_cells)

    page, per_page = 1, 1000
    written = 0
    while True:
        result = get_review_queue(page=page, per_page=per_page)
        rows = result.get("invoices", [])
        if not rows:
            break
        for row in rows:
            ws.append([
                row.get("id") or "", row.get("filename") or "",
                row.get("vendor") or "", row.get("date") or "", row.get("time") or "",
                row.get("total") or "", row.get("vat_rate") or "",
                row.get("vat_amount") or "", row.get("invoice_number") or "",
                row.get("category") or "", row.get("payment_method") or "",
                row.get("review_reason") or "", row.get("timestamp") or "",
            ])
            written += 1
        if page >= result.get("pages", 1):
            break
        page += 1

    if written == 0:
        summary = openpyxl.cell.WriteOnlyCell(ws, value="İnceleme bekleyen fatura yok.")
        summary.font = Font(bold=True, color="16A34A")
        ws.append([summary])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"autotax_inceleme_bekleyen_{today}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ─── GET /stats/export/review-queue-csv  (streaming, sınırsız) ───
@router.get("/export/review-queue-csv")
def export_review_queue_csv():
    """needs_review=1 olan tüm faturaları CSV olarak akış halinde indir."""
    from datetime import date as _date
    today = _date.today().isoformat()

    def _gen():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["ID", "Dosya", "Firma", "Tarih", "Saat", "Tutar",
                         "KDV%", "KDV_Tutar", "Fatura_No", "Kategori",
                         "Odeme", "Inceleme_Nedeni", "Timestamp"])
        yield buf.getvalue()

        page, per_page = 1, 2000
        while True:
            result = get_review_queue(page=page, per_page=per_page)
            rows = result.get("invoices", [])
            if not rows:
                break
            for row in rows:
                buf2 = io.StringIO()
                w2 = csv.writer(buf2)
                w2.writerow([
                    row.get("id") or "", row.get("filename") or "",
                    row.get("vendor") or "", row.get("date") or "", row.get("time") or "",
                    row.get("total") or "", row.get("vat_rate") or "",
                    row.get("vat_amount") or "", row.get("invoice_number") or "",
                    row.get("category") or "", row.get("payment_method") or "",
                    row.get("review_reason") or "", row.get("timestamp") or "",
                ])
                yield buf2.getvalue()
            if page >= result.get("pages", 1):
                break
            page += 1

    fname = f"autotax_inceleme_bekleyen_{today}.csv"
    return StreamingResponse(
        _gen(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "X-Content-Type-Options": "nosniff",
        },
    )

"""AutoTax.cloud — Vergi (KDV) Raporu API"""
from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse
from typing   import Optional
import io, csv, re
from datetime import datetime
from pathlib  import Path
from app.routes.auth import get_current_user
from app.config      import settings

router = APIRouter(prefix="/tax", tags=["Tax"])

_MONTH_RE   = re.compile(r"^\d{4}-\d{2}$")
_SQLITE_PATH = Path(settings.SQLITE_PATH)


def _uid(request: Request) -> str:
    return get_current_user(request)["sub"]


def _inv_conn():
    import sqlite3
    c = sqlite3.connect(str(_SQLITE_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    return c


def _validate_month(month: str) -> str:
    """YYYY-MM formatı doğrula — SQL injection engelle."""
    if not _MONTH_RE.match(month):
        from fastapi import HTTPException
        raise HTTPException(400, "Geçersiz ay formatı. YYYY-MM kullanın.")
    return month


def _build_report(user_id: str, year: int, quarter: int = None,
                  month: str = None) -> dict:
    params: list = [user_id]

    # Dönem filtresi — tümü parametrik
    if month:
        _validate_month(month)
        date_filter = "strftime('%Y-%m', date) = ?"
        params.append(month)
    elif quarter:
        q_map = {1: ("01","03"), 2: ("04","06"), 3: ("07","09"), 4: ("10","12")}
        m_start, m_end = q_map.get(quarter, ("01","12"))
        date_filter = "date >= ? AND date <= ?"
        params.append(f"{year}-{m_start}-01")
        params.append(f"{year}-{m_end}-31")
    else:
        date_filter = "strftime('%Y', date) = ?"
        params.append(str(year))

    base = f"WHERE user_id=? AND ({date_filter}) AND total IS NOT NULL"

    with _inv_conn() as c:
        # Genel özet
        summary = c.execute(
            f"SELECT COUNT(*) as invoice_count, "
            f"COALESCE(SUM(total),0) as gross_total, "
            f"COALESCE(SUM(vat_amount),0) as total_vat, "
            f"COALESCE(SUM(total - COALESCE(vat_amount,0)),0) as net_total "
            f"FROM invoices {base}",
            params
        ).fetchone()

        # KDV oranı bazlı gruplandırma
        by_rate = c.execute(
            f"SELECT COALESCE(vat_rate,'Bilinmiyor') as vat_rate, "
            f"COUNT(*) as count, COALESCE(SUM(total),0) as gross, "
            f"COALESCE(SUM(vat_amount),0) as vat, "
            f"COALESCE(SUM(total - COALESCE(vat_amount,0)),0) as net "
            f"FROM invoices {base} GROUP BY vat_rate ORDER BY vat_rate",
            params
        ).fetchall()

        # Aylık dağılım
        by_month = c.execute(
            f"SELECT strftime('%Y-%m', date) as month, COUNT(*) as count, "
            f"COALESCE(SUM(total),0) as gross, COALESCE(SUM(vat_amount),0) as vat "
            f"FROM invoices {base} GROUP BY month ORDER BY month",
            params
        ).fetchall()

        # Kategori bazlı (ilk 20)
        by_cat = c.execute(
            f"SELECT COALESCE(category,'Diğer') as category, COUNT(*) as count, "
            f"COALESCE(SUM(total),0) as gross, COALESCE(SUM(vat_amount),0) as vat "
            f"FROM invoices {base} GROUP BY category ORDER BY gross DESC LIMIT 20",
            params
        ).fetchall()

    period_label = month or (f"Q{quarter}/{year}" if quarter else str(year))
    return {
        "period":      period_label,
        "generated":   datetime.utcnow().isoformat()[:19],
        "summary":     dict(summary),
        "by_vat_rate": [dict(r) for r in by_rate],
        "by_month":    [dict(r) for r in by_month],
        "by_category": [dict(r) for r in by_cat],
    }


@router.get("/report")
def tax_report(
    request: Request,
    year:    int = Query(default=None),
    quarter: Optional[int] = Query(None, ge=1, le=4),
    month:   Optional[str] = Query(None, description="YYYY-MM"),
):
    if not year:
        year = datetime.utcnow().year
    return _build_report(_uid(request), year, quarter, month)


@router.get("/report/csv")
def tax_report_csv(
    request: Request,
    year:    int = Query(default=None),
    quarter: Optional[int] = Query(None, ge=1, le=4),
    month:   Optional[str] = Query(None),
):
    if not year:
        year = datetime.utcnow().year
    data = _build_report(_uid(request), year, quarter, month)

    buf = io.StringIO()
    w   = csv.writer(buf)

    w.writerow(["DÖNEM", data["period"]])
    w.writerow(["Oluşturulma", data["generated"]])
    w.writerow([])
    w.writerow(["GENEL ÖZET"])
    s = data["summary"]
    w.writerow(["Fatura Sayısı", s["invoice_count"]])
    w.writerow(["Brüt Toplam (€)", f'{s["gross_total"]:.2f}'])
    w.writerow(["Toplam KDV (€)",  f'{s["total_vat"]:.2f}'])
    w.writerow(["Net Toplam (€)",  f'{s["net_total"]:.2f}'])
    w.writerow([])

    w.writerow(["KDV ORANLARI"])
    w.writerow(["KDV %", "Fatura", "Brüt (€)", "KDV (€)", "Net (€)"])
    for r in data["by_vat_rate"]:
        w.writerow([r["vat_rate"], r["count"],
                    f'{r["gross"]:.2f}', f'{r["vat"]:.2f}', f'{r["net"]:.2f}'])
    w.writerow([])

    w.writerow(["AYLIK DAĞILIM"])
    w.writerow(["Ay", "Fatura", "Brüt (€)", "KDV (€)"])
    for r in data["by_month"]:
        w.writerow([r["month"], r["count"], f'{r["gross"]:.2f}', f'{r["vat"]:.2f}'])

    buf.seek(0)
    fname = f"vergi_raporu_{data['period'].replace('/','_')}.csv"
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )

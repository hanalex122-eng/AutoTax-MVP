"""AutoTax.cloud — Vergi (KDV) Raporu API"""
from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse
from typing   import Optional
import io, csv, json
from datetime import datetime
from app.routes.auth import get_current_user

router = APIRouter(prefix="/tax", tags=["Tax"])


def _uid(request: Request) -> str:
    return get_current_user(request)["sub"]


def _inv_conn():
    import sqlite3
    from pathlib import Path
    c = sqlite3.connect(str(Path("storage/invoices.db")), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def _build_report(user_id: str, year: int, quarter: int = None,
                  month: str = None) -> dict:
    with _inv_conn() as c:
        # Dönem filtresi
        if month:
            date_filter = f"strftime('%Y-%m', date) = '{month}'"
        elif quarter:
            q_map = {1: ("01","03"), 2: ("04","06"), 3: ("07","09"), 4: ("10","12")}
            m_start, m_end = q_map.get(quarter, ("01","12"))
            date_filter = (f"date >= '{year}-{m_start}-01' "
                           f"AND date <= '{year}-{m_end}-31'")
        else:
            date_filter = f"strftime('%Y', date) = '{year}'"

        base = f"WHERE ({date_filter}) AND total IS NOT NULL"

        # Genel özet
        summary = c.execute(f"""
            SELECT
                COUNT(*)                      as invoice_count,
                COALESCE(SUM(total),0)        as gross_total,
                COALESCE(SUM(vat_amount),0)   as total_vat,
                COALESCE(SUM(total - COALESCE(vat_amount,0)),0) as net_total
            FROM invoices {base}
        """).fetchone()

        # KDV oranı bazlı gruplandırma
        by_rate = c.execute(f"""
            SELECT
                COALESCE(vat_rate,'Bilinmiyor') as vat_rate,
                COUNT(*)                        as count,
                COALESCE(SUM(total),0)          as gross,
                COALESCE(SUM(vat_amount),0)     as vat,
                COALESCE(SUM(total - COALESCE(vat_amount,0)),0) as net
            FROM invoices {base}
            GROUP BY vat_rate
            ORDER BY vat_rate
        """).fetchall()

        # Aylık dağılım
        by_month = c.execute(f"""
            SELECT
                strftime('%Y-%m', date) as month,
                COUNT(*)               as count,
                COALESCE(SUM(total),0) as gross,
                COALESCE(SUM(vat_amount),0) as vat
            FROM invoices {base}
            GROUP BY month
            ORDER BY month
        """).fetchall()

        # Kategori bazlı
        by_cat = c.execute(f"""
            SELECT
                COALESCE(category,'Diğer') as category,
                COUNT(*)                   as count,
                COALESCE(SUM(total),0)     as gross,
                COALESCE(SUM(vat_amount),0) as vat
            FROM invoices {base}
            GROUP BY category
            ORDER BY gross DESC
            LIMIT 20
        """).fetchall()

    period_label = month or (f"Q{quarter}/{year}" if quarter else str(year))
    return {
        "period":     period_label,
        "generated":  datetime.utcnow().isoformat()[:19],
        "summary":    dict(summary),
        "by_vat_rate": [dict(r) for r in by_rate],
        "by_month":   [dict(r) for r in by_month],
        "by_category":[dict(r) for r in by_cat],
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

    # Özet
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

    # KDV oranı bazlı
    w.writerow(["KDV ORANLARI"])
    w.writerow(["KDV %", "Fatura", "Brüt (€)", "KDV (€)", "Net (€)"])
    for r in data["by_vat_rate"]:
        w.writerow([r["vat_rate"], r["count"],
                    f'{r["gross"]:.2f}', f'{r["vat"]:.2f}', f'{r["net"]:.2f}'])
    w.writerow([])

    # Aylık
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

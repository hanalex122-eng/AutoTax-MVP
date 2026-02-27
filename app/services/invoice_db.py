import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from threading import Lock

from app.config import settings

# ── Yollar ────────────────────────────────────────────────
_JSON_PATH = Path(settings.DB_PATH)
DB_PATH    = _JSON_PATH.parent / "invoices.db"
_LOCK      = Lock()


# ── Şema + Indexler ───────────────────────────────────────
_DDL = """
CREATE TABLE IF NOT EXISTS invoices (
    id             TEXT PRIMARY KEY,
    filename       TEXT,
    timestamp      TEXT,
    vendor         TEXT,
    date           TEXT,
    time           TEXT,
    total          REAL,
    vat_rate       INTEGER,
    vat_amount     REAL,
    invoice_number TEXT,
    category       TEXT,
    payment_method TEXT,
    qr_raw         TEXT,
    qr_parsed      TEXT,
    raw_text       TEXT,
    needs_review   INTEGER DEFAULT 0,
    review_reason  TEXT
);
CREATE INDEX IF NOT EXISTS idx_date     ON invoices(date);
CREATE INDEX IF NOT EXISTS idx_vendor   ON invoices(vendor COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_category ON invoices(category);
CREATE INDEX IF NOT EXISTS idx_total    ON invoices(total);
CREATE INDEX IF NOT EXISTS idx_payment  ON invoices(payment_method);
CREATE INDEX IF NOT EXISTS idx_ts       ON invoices(timestamp DESC);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")   # concurrent reads
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA cache_size=-32000")  # 32 MB page cache
    return c


def _init():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as c:
        c.executescript(_DDL)
    _migrate_json()


def _migrate_json():
    """Eski JSON DB → SQLite (ilk çalışmada otomatik)."""
    if not _JSON_PATH.exists():
        return
    try:
        with _conn() as c:
            if c.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] > 0:
                return           # zaten migrate edilmiş

        with _JSON_PATH.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        invs = raw.get("invoices", raw) if isinstance(raw, dict) else raw
        if not invs:
            return

        rows = []
        for inv in invs:
            d = inv.get("data") or inv.get("parsed") or {}
            rows.append(_record_to_row(
                inv.get("id", str(uuid.uuid4())),
                inv.get("filename", ""),
                inv.get("timestamp", datetime.now().isoformat()),
                d,
            ))

        with _conn() as c:
            c.executemany(
                "INSERT OR IGNORE INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )

        _JSON_PATH.rename(_JSON_PATH.with_suffix(".json.bak"))
        print(f"[AutoTax] {len(rows)} fatura JSON'dan SQLite'a taşındı.")
    except Exception as e:
        print(f"[AutoTax] Migrasyon hatası: {e}")


def _record_to_row(inv_id, filename, timestamp, d):
    return (
        inv_id, filename, timestamp,
        d.get("vendor"),  d.get("date"),   d.get("time"),
        _f(d.get("total")), _i(d.get("vat_rate")), _f(d.get("vat_amount")),
        d.get("invoice_number"), d.get("category"), d.get("payment_method"),
        (d.get("qr_raw") or "")[:500],
        json.dumps(d.get("qr_parsed"), ensure_ascii=False) if d.get("qr_parsed") else None,
        (d.get("raw_text") or "")[:5000],
        1 if d.get("needs_review") else 0,
        d.get("review_reason"),
    )


def _f(v):
    try: return float(v) if v is not None else None
    except (TypeError, ValueError): return None


def _i(v):
    try: return int(v) if v is not None else None
    except (TypeError, ValueError): return None


def _row_to_dict(row) -> dict:
    """Eski JSON formatıyla uyumlu çıktı (frontend değişmesin)."""
    qp = None
    if row["qr_parsed"]:
        try: qp = json.loads(row["qr_parsed"])
        except Exception: pass
    return {
        "id":        row["id"],
        "timestamp": row["timestamp"],
        "filename":  row["filename"],
        "needs_review": bool(row["needs_review"]),
        "data": {
            "vendor":          row["vendor"],
            "date":            row["date"],
            "time":            row["time"],
            "total":           row["total"],
            "vat_rate":        row["vat_rate"],
            "vat_amount":      row["vat_amount"],
            "invoice_number":  row["invoice_number"],
            "category":        row["category"],
            "payment_method":  row["payment_method"],
            "qr_raw":          row["qr_raw"],
            "qr_parsed":       qp,
            "raw_text":        row["raw_text"],
        },
    }


# ── YAZMA ─────────────────────────────────────────────────
def add_invoice(record: dict, filename: str) -> str:
    inv_id = str(uuid.uuid4())
    row    = _record_to_row(inv_id, filename, datetime.now().isoformat(), record)
    with _LOCK:
        with _conn() as c:
            c.execute(
                "INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                row,
            )
    return inv_id


def update_invoice(inv_id: str, fields: dict) -> bool:
    """Manuel düzeltme — yalnızca izin verilen alanları günceller."""
    allowed = {"vendor", "date", "time", "total", "vat_rate", "vat_amount",
               "invoice_number", "category", "payment_method", "needs_review", "review_reason"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    # needs_review otomatik kapat — total girilmişse
    if "total" in updates and updates["total"]:
        updates.setdefault("needs_review", 0)
        updates.setdefault("review_reason", None)
    set_clause = ", ".join(f"{k}=?" for k in updates)
    vals       = list(updates.values()) + [inv_id]
    with _LOCK:
        with _conn() as c:
            cur = c.execute(f"UPDATE invoices SET {set_clause} WHERE id=?", vals)
            return cur.rowcount > 0


def get_review_queue(page: int = 1, per_page: int = 50) -> dict:
    """needs_review=1 olan faturalar — elle düzeltme kuyruğu."""
    total_cnt = 0
    with _conn() as c:
        total_cnt = c.execute(
            "SELECT COUNT(*) FROM invoices WHERE needs_review=1"
        ).fetchone()[0]
        pages  = max(1, (total_cnt + per_page - 1) // per_page)
        page   = max(1, min(page, pages))
        offset = (page - 1) * per_page
        rows   = c.execute(
            "SELECT * FROM invoices WHERE needs_review=1 "
            "ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            [per_page, offset],
        ).fetchall()
    return {
        "count":    total_cnt,
        "page":     page,
        "pages":    pages,
        "per_page": per_page,
        "invoices": [_row_to_dict(r) for r in rows],
    }


def get_invoice(inv_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM invoices WHERE id=?", (inv_id,)).fetchone()
    return _row_to_dict(row) if row else None


# ── SORGULAMA (SQL — 10M kayıtta O(log n)) ────────────────
def query_invoices(
    start=None, end=None, vendor=None, category=None,
    payment=None, invoice_no=None, min_amt=None, max_amt=None,
    page: int = 1, per_page: int = 100,
) -> dict:
    where, params = _build_where(start, end, vendor, category,
                                 payment, invoice_no, min_amt, max_amt)
    w = ("WHERE " + " AND ".join(where)) if where else ""

    with _conn() as c:
        # Toplam + aggregate (tek geçiş, SQL'de)
        agg = c.execute(
            f"SELECT COUNT(*) cnt, "
            f"COALESCE(SUM(total),0) ts, COALESCE(SUM(vat_amount),0) vs "
            f"FROM invoices {w}", params
        ).fetchone()

        total_cnt = agg["cnt"]
        total_sum = round(agg["ts"], 2)
        vat_sum   = round(agg["vs"], 2)

        # Firma bazlı (ilk 50)
        by_vendor = {
            r["v"]: round(r["t"], 2)
            for r in c.execute(
                f"SELECT COALESCE(vendor,'bilinmiyor') v, COALESCE(SUM(total),0) t "
                f"FROM invoices {w} GROUP BY v ORDER BY t DESC LIMIT 50",
                params,
            )
        }

        # Kategori bazlı
        by_category = {
            r["c"]: round(r["t"], 2)
            for r in c.execute(
                f"SELECT COALESCE(category,'bilinmiyor') c, COALESCE(SUM(total),0) t "
                f"FROM invoices {w} GROUP BY c ORDER BY t DESC",
                params,
            )
        }

        # Sayfalı sonuçlar
        pages  = max(1, (total_cnt + per_page - 1) // per_page)
        page   = max(1, min(page, pages))
        offset = (page - 1) * per_page
        rows   = c.execute(
            f"SELECT * FROM invoices {w} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()

    return {
        "count":       total_cnt,
        "total_sum":   total_sum,
        "vat_sum":     vat_sum,
        "by_vendor":   by_vendor,
        "by_category": by_category,
        "page":        page,
        "per_page":    per_page,
        "pages":       pages,
        "invoices":    [_row_to_dict(r) for r in rows],
    }


def _build_where(start, end, vendor, category, payment, invoice_no, min_amt, max_amt):
    where, params = [], []
    if start:
        where.append("date >= ?"); params.append(str(start))
    if end:
        where.append("date <= ?"); params.append(str(end))
    if vendor:
        where.append("vendor LIKE ?"); params.append(f"%{vendor}%")
    if category:
        where.append("category = ?"); params.append(category)
    if payment:
        where.append("payment_method = ?"); params.append(payment)
    if invoice_no:
        where.append("invoice_number LIKE ?"); params.append(f"%{invoice_no}%")
    if min_amt is not None:
        where.append("total >= ?"); params.append(min_amt)
    if max_amt is not None:
        where.append("total <= ?"); params.append(max_amt)
    return where, params


# ── STREAMING EXPORT (RAM sabit, N→∞) ────────────────────
def iter_rows(
    start=None, end=None, vendor=None, category=None,
    payment=None, invoice_no=None, min_amt=None, max_amt=None,
    chunk: int = 2_000,
):
    """SQLite cursor'ı chunk'lar halinde iter — RAM asla şişmez.

    Kullanım:
        for row in iter_rows(...):
            # row: sqlite3.Row  (sözlük gibi erişim)
    """
    where, params = _build_where(start, end, vendor, category,
                                 payment, invoice_no, min_amt, max_amt)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"SELECT * FROM invoices {w} ORDER BY timestamp DESC"

    conn = _conn()
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.arraysize = chunk
        cur.execute(sql, params)
        while True:
            batch = cur.fetchmany(chunk)
            if not batch:
                break
            yield from batch
    finally:
        conn.close()


# ── BASIT YARDIMCILAR ─────────────────────────────────────
def count() -> int:
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]


def load_all() -> list:
    """Geriye dönük uyumluluk — sadece küçük veri setleri için."""
    with _conn() as c:
        return [_row_to_dict(r) for r in
                c.execute("SELECT * FROM invoices ORDER BY timestamp DESC")]


def load_page(page: int = 1, per_page: int = 100) -> tuple:
    res = query_invoices(page=page, per_page=per_page)
    return res["invoices"], res["count"]


def get_data(inv: dict) -> dict:
    return inv.get("data") or inv.get("parsed") or {}


def safe_float(inv: dict, field: str) -> float:
    try: return float(get_data(inv).get(field) or 0)
    except (TypeError, ValueError): return 0.0


# Başlatma
_init()

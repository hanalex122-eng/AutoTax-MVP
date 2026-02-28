import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from threading import Lock

from app.config import settings

# ── Yollar ────────────────────────────────────────────────
_JSON_PATH = Path(settings.DB_PATH)
DB_PATH    = Path(settings.SQLITE_PATH)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
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
    review_reason  TEXT,
    invoice_type   TEXT DEFAULT 'expense',
    user_id        TEXT
);
CREATE INDEX IF NOT EXISTS idx_date     ON invoices(date);
CREATE INDEX IF NOT EXISTS idx_vendor   ON invoices(vendor COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_category ON invoices(category);
CREATE INDEX IF NOT EXISTS idx_total    ON invoices(total);
CREATE INDEX IF NOT EXISTS idx_payment  ON invoices(payment_method);
CREATE INDEX IF NOT EXISTS idx_ts       ON invoices(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_type     ON invoices(invoice_type);
CREATE INDEX IF NOT EXISTS idx_uid      ON invoices(user_id);
"""

_MIGRATE_DDL = """
ALTER TABLE invoices ADD COLUMN invoice_type TEXT DEFAULT 'expense';
CREATE INDEX IF NOT EXISTS idx_type ON invoices(invoice_type);
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
        # Önce migration — mevcut DB'ye kolon ekle
        cols = [r[1] for r in c.execute("PRAGMA table_info(invoices)").fetchall()]
        if cols and "invoice_type" not in cols:
            try:
                c.execute("ALTER TABLE invoices ADD COLUMN invoice_type TEXT DEFAULT 'expense'")
                c.execute("CREATE INDEX IF NOT EXISTS idx_type ON invoices(invoice_type)")
                c.commit()
            except Exception as e:
                print(f"[AutoTax] invoice_type migration: {e}")
        if cols and "user_id" not in cols:
            try:
                c.execute("ALTER TABLE invoices ADD COLUMN user_id TEXT")
                c.execute("CREATE INDEX IF NOT EXISTS idx_uid ON invoices(user_id)")
                c.commit()
            except Exception as e:
                print(f"[AutoTax] user_id migration: {e}")
        # Sonra DDL (yeni tablo için)
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
                "INSERT OR IGNORE INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )

        _JSON_PATH.rename(_JSON_PATH.with_suffix(".json.bak"))
        print(f"[AutoTax] {len(rows)} fatura JSON'dan SQLite'a taşındı.")
    except Exception as e:
        print(f"[AutoTax] Migrasyon hatası: {e}")


def _record_to_row(inv_id, filename, timestamp, d, user_id=None):
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
        d.get("invoice_type", "expense"),
        user_id,
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
        "invoice_type": row["invoice_type"] if "invoice_type" in row.keys() else "expense",
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
def add_invoice(record: dict, filename: str, user_id: str = None) -> str:
    inv_id = str(uuid.uuid4())
    row    = _record_to_row(inv_id, filename, datetime.now().isoformat(), record, user_id)
    with _LOCK:
        with _conn() as c:
            c.execute(
                "INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                row,
            )
    return inv_id


def find_duplicate(vendor: str, date: str, total: float,
                   invoice_number: str = None,
                   user_id: str = None) -> dict | None:
    """
    Yeni fatura ile aynı (vendor + date + total) veya (invoice_number) olan
    mevcut kaydı döndürür. Kullanıcıya özgü arama — user_id zorunlu.
    """
    if not user_id:
        return None
    if not vendor and not invoice_number:
        return None
    with _conn() as c:
        # invoice_number ile tam eşleşme (en güvenilir)
        if invoice_number:
            row = c.execute(
                "SELECT id,vendor,date,total,timestamp FROM invoices "
                "WHERE invoice_number=? AND LOWER(vendor)=LOWER(?) AND user_id=? LIMIT 1",
                [invoice_number, vendor or "", user_id]
            ).fetchone()
            if row:
                return dict(row)
        # vendor + date + total ile yumuşak eşleşme (±%2 tutar toleransı)
        if vendor and date and total:
            tol = abs(total) * 0.02 or 0.01
            row = c.execute(
                "SELECT id,vendor,date,total,timestamp FROM invoices "
                "WHERE LOWER(vendor)=LOWER(?) AND date=? "
                "AND ABS(total - ?) <= ? AND user_id=? LIMIT 1",
                [vendor, date, total, tol, user_id]
            ).fetchone()
            if row:
                return dict(row)
    return None


def find_recurring(vendor: str, months: int = 3,
                   user_id: str = None) -> list[dict]:
    """
    Aynı firmadan son N ayda düzenli fatura var mı kontrol et.
    user_id zorunlu — verilmezse boş liste döner (anonim IDOR engeli).
    """
    if not vendor or not user_id:
        return []
    with _conn() as c:
        rows = c.execute(
            """
            SELECT strftime('%Y-%m', date) as month,
                   COUNT(*) as cnt,
                   AVG(total) as avg_total,
                   MIN(total) as min_total,
                   MAX(total) as max_total
            FROM invoices
            WHERE LOWER(vendor)=LOWER(?)
              AND date >= date('now', ?)
              AND user_id=?
            GROUP BY month
            ORDER BY month DESC
            """,
            [vendor, f"-{months} months", user_id]
        ).fetchall()
    return [dict(r) for r in rows]


def update_invoice(inv_id: str, fields: dict) -> bool:
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


# ── MUHASEBECI PAYLAŞIM YARDIMCILARI ─────────────────────
def get_invoices_page(
    page: int = 1, per_page: int = 50,
    user_id: str = None,
    date_from: str = None, date_to: str = None,
    vendor: str = None,
) -> dict:
    """Sayfalı fatura listesi — share.py ve diğerleri için."""
    where, params = [], []
    if user_id:
        where.append("user_id=?"); params.append(user_id)
    if date_from:
        where.append("date >= ?"); params.append(date_from)
    if date_to:
        where.append("date <= ?"); params.append(date_to)
    if vendor:
        where.append("vendor LIKE ?"); params.append(f"%{vendor}%")
    w = ("WHERE " + " AND ".join(where)) if where else ""

    with _conn() as c:
        total_cnt = c.execute(
            f"SELECT COUNT(*) FROM invoices {w}", params
        ).fetchone()[0]
        pages  = max(1, (total_cnt + per_page - 1) // per_page)
        page   = max(1, min(page, pages))
        offset = (page - 1) * per_page
        rows   = c.execute(
            f"SELECT * FROM invoices {w} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()
    return {
        "count":    total_cnt,
        "page":     page,
        "pages":    pages,
        "per_page": per_page,
        "invoices": [_row_to_dict(r) for r in rows],
    }


def get_ledger(
    user_id: str = None,
    date_from: str = None, date_to: str = None,
) -> dict:
    """Gelir/gider özeti — muhasebe defteri."""
    where, params = [], []
    if user_id:
        where.append("user_id=?"); params.append(user_id)
    if date_from:
        where.append("date >= ?"); params.append(date_from)
    if date_to:
        where.append("date <= ?"); params.append(date_to)
    w = ("WHERE " + " AND ".join(where)) if where else ""

    with _conn() as c:
        rows = c.execute(
            f"SELECT invoice_type, COUNT(*) as cnt, "
            f"COALESCE(SUM(total),0) as total_sum, "
            f"COALESCE(SUM(vat_amount),0) as vat_sum "
            f"FROM invoices {w} GROUP BY invoice_type",
            params
        ).fetchall()

    summary = {"income": {"count": 0, "total": 0.0, "vat": 0.0},
               "expense": {"count": 0, "total": 0.0, "vat": 0.0}}
    for r in rows:
        t = r["invoice_type"] or "expense"
        if t not in summary:
            summary[t] = {"count": 0, "total": 0.0, "vat": 0.0}
        summary[t]["count"] += r["cnt"]
        summary[t]["total"] += round(r["total_sum"], 2)
        summary[t]["vat"]   += round(r["vat_sum"],   2)

    income  = summary.get("income",  {}).get("total", 0)
    expense = summary.get("expense", {}).get("total", 0)
    return {
        "income":  summary.get("income",  {"count": 0, "total": 0.0, "vat": 0.0}),
        "expense": summary.get("expense", {"count": 0, "total": 0.0, "vat": 0.0}),
        "net":     round(income - expense, 2),
    }


# ── GDPR: Fatura Silme ────────────────────────────────────
def _unlink_file(filename: str) -> None:
    """Dosyayı diskten güvenli şekilde sil (hata olursa sessizce geç)."""
    if not filename:
        return
    try:
        Path(filename).unlink(missing_ok=True)
    except Exception:
        pass


def delete_user_invoices(user_id: str) -> int:
    """Kullanıcıya ait tüm faturaları ve dosyalarını sil. Silinen kayıt sayısını döndürür."""
    with _LOCK:
        with _conn() as c:
            # GDPR Madde 17: önce dosya yollarını al, sonra diskten sil
            rows = c.execute(
                "SELECT filename FROM invoices WHERE user_id=?", (user_id,)
            ).fetchall()
            for row in rows:
                _unlink_file(row[0])
            cur = c.execute("DELETE FROM invoices WHERE user_id=?", (user_id,))
    return cur.rowcount


def delete_invoice(invoice_id: str, user_id: str) -> bool:
    """Tek fatura sil — user_id koşuluyla (başka kullanıcı silemez)."""
    with _LOCK:
        with _conn() as c:
            row = c.execute(
                "SELECT filename FROM invoices WHERE id=? AND user_id=?",
                (invoice_id, user_id)
            ).fetchone()
            if not row:
                return False
            _unlink_file(row[0])
            cur = c.execute(
                "DELETE FROM invoices WHERE id=? AND user_id=?",
                (invoice_id, user_id)
            )
    return cur.rowcount > 0


def purge_old_invoice_files(days: int = 90) -> int:
    """
    90 günden eski fatura görsellerini diskten sil, DB kaydını koru.
    (privacy.html taahhüdünü yerine getirir — GDPR veri minimizasyonu Md.5/1-e)
    """
    from datetime import timedelta
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    with _LOCK:
        with _conn() as c:
            rows = c.execute(
                "SELECT id, filename FROM invoices WHERE created_at < ? AND filename IS NOT NULL",
                (cutoff,)
            ).fetchall()
            count = 0
            for row in rows:
                _unlink_file(row[1])
                c.execute("UPDATE invoices SET filename=NULL WHERE id=?", (row[0],))
                count += 1
    return count


# Başlatma
_init()


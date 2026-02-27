"""
AutoTax.cloud — Bütçe Takibi
Kategori bazlı aylık harcama limiti koyabilir,
limitin %80 ve %100'ünde uyarı alabilirsiniz.
"""
import sqlite3
from pathlib  import Path
from threading import Lock
from datetime  import datetime
from app.services.user_db import _DB_PATH, _LOCK
from app.config import settings

_INV_DB = Path(settings.SQLITE_PATH)


def _conn():
    c = sqlite3.connect(str(_DB_PATH), check_same_thread=False, timeout=30)
    c.row_factory = sqlite3.Row
    return c


_DDL = """
CREATE TABLE IF NOT EXISTS budgets (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    category   TEXT NOT NULL,
    amount     REAL NOT NULL,
    period     TEXT NOT NULL DEFAULT 'monthly',
    created_at TEXT NOT NULL,
    UNIQUE(user_id, category, period)
);
CREATE INDEX IF NOT EXISTS idx_budget_user ON budgets(user_id);
"""


def _init_budget():
    with _conn() as c:
        c.executescript(_DDL)

_init_budget()


# ── CRUD ──────────────────────────────────────────────────
def set_budget(user_id: str, category: str, amount: float, period: str = "monthly") -> dict:
    import uuid
    bid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with _LOCK:
        with _conn() as c:
            c.execute(
                "INSERT INTO budgets (id,user_id,category,amount,period,created_at) "
                "VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(user_id,category,period) DO UPDATE SET amount=excluded.amount",
                (bid, user_id, category.lower().strip(), amount, period, now)
            )
    return {"user_id": user_id, "category": category, "amount": amount, "period": period}


def get_budgets(user_id: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM budgets WHERE user_id=? ORDER BY category",
            (user_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_budget(user_id: str, category: str) -> bool:
    with _LOCK:
        with _conn() as c:
            c.execute(
                "DELETE FROM budgets WHERE user_id=? AND LOWER(category)=LOWER(?)",
                (user_id, category)
            )
    return True


def get_budget_status(user_id: str, month: str = None) -> list[dict]:
    """
    Her kategori için bütçe vs harcama karşılaştırması.
    month: "YYYY-MM" formatı, None = bu ay
    """
    if not month:
        month = datetime.utcnow().strftime("%Y-%m")

    budgets = get_budgets(user_id)
    if not budgets:
        return []

    # Tek sorguyla tüm kategorilerin harcamalarını çek (N+1 önlenir)
    # Yalnızca bu kullanıcının faturaları sorgulanır (IDOR önlenir)
    with sqlite3.connect(str(_INV_DB), check_same_thread=False) as ic:
        ic.row_factory = sqlite3.Row
        rows = ic.execute(
            "SELECT LOWER(category) as cat, COALESCE(SUM(total),0) as spent "
            "FROM invoices "
            "WHERE user_id=? AND strftime('%Y-%m',date)=? "
            "GROUP BY LOWER(category)",
            (user_id, month)
        ).fetchall()
    spent_map = {r["cat"]: float(r["spent"]) for r in rows}

    result = []
    for b in budgets:
        cat   = b["category"].lower()
        limit = b["amount"]
        spent = spent_map.get(cat, 0.0)
        pct   = round(spent / limit * 100, 1) if limit else 0
        result.append({
            "category":  b["category"],
            "budget":    limit,
            "spent":     round(spent, 2),
            "remaining": round(limit - spent, 2),
            "pct":       pct,
            "status":    "over" if pct >= 100 else "warn" if pct >= 80 else "ok",
            "month":     month,
        })
    return result

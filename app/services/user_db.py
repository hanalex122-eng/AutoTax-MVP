import sqlite3
import uuid
import bcrypt
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock

_DB_PATH = Path("storage/users.db")
_LOCK    = Lock()

# ── Plan tanımları ────────────────────────────────────────
PLANS = {
    "free": {
        "label":            "Ücretsiz",
        "monthly_invoices": 50,
        "max_members":      1,
        "languages":        3,
        "qr":               False,
        "api":              False,
        "price_eur":        0,
    },
    "personal": {
        "label":            "Kişisel",
        "monthly_invoices": 2_000,
        "max_members":      1,
        "languages":        8,
        "qr":               True,
        "api":              False,
        "price_eur":        4.99,
    },
    "family": {
        "label":            "Aile",
        "monthly_invoices": 10_000,
        "max_members":      5,
        "languages":        8,
        "qr":               True,
        "api":              False,
        "price_eur":        9.99,
    },
    "business": {
        "label":            "İşletme",
        "monthly_invoices": -1,
        "max_members":      -1,
        "languages":        8,
        "qr":               True,
        "api":              True,
        "price_eur":        29.99,
    },
}

_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id                      TEXT PRIMARY KEY,
    email                   TEXT UNIQUE NOT NULL,
    password_hash           TEXT NOT NULL,
    full_name               TEXT,
    plan                    TEXT NOT NULL DEFAULT 'free',
    plan_expires            TEXT,
    stripe_subscription_id  TEXT,
    family_id               TEXT,
    role                    TEXT NOT NULL DEFAULT 'owner',
    is_active               INTEGER NOT NULL DEFAULT 1,
    is_admin                INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT NOT NULL,
    last_login              TEXT
);
CREATE INDEX IF NOT EXISTS idx_user_email  ON users(email);
CREATE INDEX IF NOT EXISTS idx_family      ON users(family_id);

CREATE TABLE IF NOT EXISTS family_invites (
    id          TEXT PRIMARY KEY,
    family_id   TEXT NOT NULL,
    email       TEXT NOT NULL,
    invited_by  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_invite_email ON family_invites(email);
CREATE INDEX IF NOT EXISTS idx_invite_fam   ON family_invites(family_id);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    token      TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_rt_user ON refresh_tokens(user_id);

CREATE TABLE IF NOT EXISTS invoice_usage (
    user_id    TEXT NOT NULL,
    month      TEXT NOT NULL,
    count      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, month)
);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(_DB_PATH), check_same_thread=False, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    return c


def _init():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as c:
        c.executescript(_DDL)


# ── Şifre ─────────────────────────────────────────────────
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ── Kullanıcı CRUD ────────────────────────────────────────
def create_user(email: str, password: str, full_name: str = "", plan: str = "free") -> dict:
    uid  = str(uuid.uuid4())
    now  = datetime.utcnow().isoformat()
    with _LOCK:
        with _conn() as c:
            c.execute(
                "INSERT INTO users (id,email,password_hash,full_name,plan,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (uid, email.lower().strip(), hash_password(password), full_name, plan, now),
            )
    return get_user_by_id(uid)


def get_user_by_email(email: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE email=?",
                        (email.lower().strip(),)).fetchone()
    return dict(row) if row else None


def get_user_by_id(uid: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return dict(row) if row else None


def update_last_login(uid: str):
    with _conn() as c:
        c.execute("UPDATE users SET last_login=? WHERE id=?",
                  (datetime.utcnow().isoformat(), uid))


def update_plan(uid: str, plan: str, months: int = 1):
    expires = (datetime.utcnow() + timedelta(days=30 * months)).isoformat()
    with _conn() as c:
        c.execute("UPDATE users SET plan=?, plan_expires=? WHERE id=?",
                  (plan, expires, uid))


def update_user_plan(uid: str, plan: str, stripe_subscription_id: str | None):
    """Stripe webhook'tan plan güncelle."""
    expires = (datetime.utcnow() + timedelta(days=30)).isoformat()
    with _LOCK:
        with _conn() as c:
            # Migration: kolon yoksa ekle
            cols = [r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()]
            if "stripe_subscription_id" not in cols:
                c.execute("ALTER TABLE users ADD COLUMN stripe_subscription_id TEXT")
            c.execute(
                "UPDATE users SET plan=?, plan_expires=?, stripe_subscription_id=? WHERE id=?",
                (plan, expires, stripe_subscription_id, uid),
            )


# ── Refresh Token ─────────────────────────────────────────
def save_refresh_token(token: str, user_id: str, ttl_days: int = 30):
    expires = (datetime.utcnow() + timedelta(days=ttl_days)).isoformat()
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO refresh_tokens (token,user_id,expires_at,revoked) VALUES (?,?,?,0)",
            (token, user_id, expires),
        )


def get_refresh_token(token: str) -> dict | None:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM refresh_tokens WHERE token=? AND revoked=0", (token,)
        ).fetchone()
    if not row:
        return None
    if row["expires_at"] < datetime.utcnow().isoformat():
        return None
    return dict(row)


def revoke_refresh_token(token: str):
    with _conn() as c:
        c.execute("UPDATE refresh_tokens SET revoked=1 WHERE token=?", (token,))


def revoke_all_user_tokens(user_id: str):
    with _conn() as c:
        c.execute("UPDATE refresh_tokens SET revoked=1 WHERE user_id=?", (user_id,))


# ── Kullanım sayacı ───────────────────────────────────────
def get_usage(user_id: str) -> int:
    month = datetime.utcnow().strftime("%Y-%m")
    with _conn() as c:
        row = c.execute(
            "SELECT count FROM invoice_usage WHERE user_id=? AND month=?",
            (user_id, month),
        ).fetchone()
    return row["count"] if row else 0


def increment_usage(user_id: str) -> int:
    month = datetime.utcnow().strftime("%Y-%m")
    with _LOCK:
        with _conn() as c:
            c.execute(
                "INSERT INTO invoice_usage (user_id,month,count) VALUES (?,?,1) "
                "ON CONFLICT(user_id,month) DO UPDATE SET count=count+1",
                (user_id, month),
            )
            return c.execute(
                "SELECT count FROM invoice_usage WHERE user_id=? AND month=?",
                (user_id, month),
            ).fetchone()["count"]


def check_quota(user: dict) -> tuple[bool, int, int]:
    """(allowed, used, limit) döner. -1 = sınırsız."""
    plan   = user.get("plan", "free")
    limit  = PLANS.get(plan, PLANS["free"])["monthly_invoices"]
    if limit == -1:
        return True, 0, -1
    used   = get_usage(user["id"])
    return used < limit, used, limit


# ── Aile üyesi yönetimi ───────────────────────────────────
def get_family_members(family_id: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id,email,full_name,role,plan,created_at FROM users WHERE family_id=?",
            (family_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def invite_family_member(family_id: str, email: str, invited_by: str) -> dict:
    invite_id = str(uuid.uuid4())
    now       = datetime.utcnow().isoformat()
    expires   = (datetime.utcnow() + timedelta(days=7)).isoformat()
    with _LOCK:
        with _conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO family_invites (id,family_id,email,invited_by,status,created_at,expires_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (invite_id, family_id, email.lower().strip(), invited_by, "pending", now, expires),
            )
    return {"invite_id": invite_id, "email": email, "expires_at": expires}


def accept_family_invite(invite_id: str, user_id: str) -> bool:
    with _LOCK:
        with _conn() as c:
            inv = c.execute(
                "SELECT fi.* FROM family_invites fi "
                "JOIN users u ON LOWER(u.email)=LOWER(fi.email) "
                "WHERE fi.id=? AND fi.status='pending' AND u.id=?",
                (invite_id, user_id)
            ).fetchone()
            if not inv:
                return False
            if inv["expires_at"] < datetime.utcnow().isoformat():
                return False
            c.execute("UPDATE family_invites SET status='accepted' WHERE id=?", (invite_id,))
            c.execute(
                "UPDATE users SET family_id=?, role='member' WHERE id=?",
                (inv["family_id"], user_id)
            )
    return True


def remove_family_member(family_id: str, member_id: str) -> bool:
    with _LOCK:
        with _conn() as c:
            c.execute(
                "UPDATE users SET family_id=NULL, role='owner' WHERE id=? AND family_id=? AND role='member'",
                (member_id, family_id)
            )
    return True


_init()

"""AutoTax.cloud — Admin API"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing   import Optional
from app.routes.auth     import require_admin
from app.services.user_db import _conn, _LOCK, PLANS

router = APIRouter(prefix="/admin", tags=["Admin"])


# ── Yardımcılar ───────────────────────────────────────────
def _row(r) -> dict:
    return dict(r) if r else {}


# ── GET /admin/stats — özet ───────────────────────────────
@router.get("/stats")
def admin_stats(admin=Depends(require_admin)):
    with _conn() as c:
        total_users   = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        active_users  = c.execute("SELECT COUNT(*) FROM users WHERE is_active=1").fetchone()[0]
        plan_counts   = {row[0]: row[1] for row in
                         c.execute("SELECT plan, COUNT(*) FROM users GROUP BY plan").fetchall()}
        total_invoices = 0
        try:
            total_invoices = c.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
        except Exception:
            pass
    return {
        "total_users":    total_users,
        "active_users":   active_users,
        "plan_counts":    plan_counts,
        "total_invoices": total_invoices,
    }


# ── GET /admin/users — kullanıcı listesi ─────────────────
@router.get("/users")
def admin_list_users(
    page:   int = Query(1, ge=1),
    limit:  int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    plan:   Optional[str] = Query(None),
    admin=Depends(require_admin),
):
    offset = (page - 1) * limit
    where, params = [], []
    if search:
        where.append("(LOWER(email) LIKE ? OR LOWER(full_name) LIKE ?)")
        params += [f"%{search.lower()}%", f"%{search.lower()}%"]
    if plan:
        where.append("plan=?")
        params.append(plan)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    with _conn() as c:
        total = c.execute(f"SELECT COUNT(*) FROM users {clause}", params).fetchone()[0]
        rows  = c.execute(
            f"SELECT id,email,full_name,plan,is_active,is_admin,created_at,last_login,role "
            f"FROM users {clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset]
        ).fetchall()
    return {"total": total, "page": page, "users": [dict(r) for r in rows]}


# ── GET /admin/users/{id} ─────────────────────────────────
@router.get("/users/{user_id}")
def admin_get_user(user_id: str, admin=Depends(require_admin)):
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Kullanıcı bulunamadı.")
    u = dict(row)
    u.pop("password_hash", None)
    return u


# ── PATCH /admin/users/{id} — plan / aktiflik güncelle ───
class PatchUser(BaseModel):
    plan:      Optional[str] = None
    is_active: Optional[bool] = None
    is_admin:  Optional[bool] = None

@router.patch("/users/{user_id}")
def admin_patch_user(user_id: str, body: PatchUser, admin=Depends(require_admin)):
    if body.plan and body.plan not in PLANS:
        raise HTTPException(400, f"Geçersiz plan: {body.plan}")
    with _LOCK:
        with _conn() as c:
            if body.plan is not None:
                c.execute("UPDATE users SET plan=? WHERE id=?", (body.plan, user_id))
            if body.is_active is not None:
                c.execute("UPDATE users SET is_active=? WHERE id=?", (int(body.is_active), user_id))
            if body.is_admin is not None:
                c.execute("UPDATE users SET is_admin=? WHERE id=?", (int(body.is_admin), user_id))
    return {"ok": True}


# ── DELETE /admin/users/{id} — hesap sil ─────────────────
@router.delete("/users/{user_id}")
def admin_delete_user(user_id: str, admin=Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(400, "Kendi hesabınızı silemezsiniz.")
    with _LOCK:
        with _conn() as c:
            c.execute("DELETE FROM users WHERE id=?", (user_id,))
            c.execute("DELETE FROM refresh_tokens WHERE user_id=?", (user_id,))
    return {"ok": True}


# ── POST /admin/email — toplu e-posta ────────────────────
class BulkEmail(BaseModel):
    subject: str
    html:    str
    plan:    Optional[str] = None   # None = herkese

@router.post("/email")
def admin_bulk_email(body: BulkEmail, admin=Depends(require_admin)):
    where  = "WHERE plan=?" if body.plan else ""
    params = [body.plan] if body.plan else []
    with _conn() as c:
        rows = c.execute(f"SELECT email FROM users WHERE is_active=1 {where}", params).fetchall()
    emails = [r[0] for r in rows]
    from app.services.email_service import send_async
    for email in emails:
        send_async(email, body.subject, body.html)
    return {"sent": len(emails)}

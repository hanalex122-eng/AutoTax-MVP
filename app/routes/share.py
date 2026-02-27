"""AutoTax.cloud — Muhasebeci Paylaşım API"""
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing   import Optional

from app.routes.auth       import get_current_user
from app.services.user_db  import (
    create_share_token, list_share_tokens,
    revoke_share_token, get_share_token, get_user_by_id,
)
from app.services.invoice_db import get_invoices_page, get_ledger

router = APIRouter(prefix="/share", tags=["Share"])


def _auth(request: Request) -> dict:
    return get_current_user(request)


# ── POST /share/create — yeni link oluştur ────────────────
class CreateShareIn(BaseModel):
    label: Optional[str] = "Muhasebeci"
    days:  int = 90

@router.post("/create")
def create_share(body: CreateShareIn, request: Request):
    user = _auth(request)
    return create_share_token(user["sub"], body.label or "", body.days)


# ── GET /share/list — kullanıcının linkleri ───────────────
@router.get("/list")
def list_shares(request: Request):
    user = _auth(request)
    return list_share_tokens(user["sub"])


# ── DELETE /share/{token} — iptal ────────────────────────
@router.delete("/{token}")
def revoke_share(token: str, request: Request):
    user = _auth(request)
    revoke_share_token(token, user["sub"])
    return {"ok": True}


# ── GET /share/view/{token} — salt-okunur erişim ─────────
@router.get("/view/{token}")
def view_share(
    token:     str,
    page:      int = Query(1, ge=1),
    per_page:  int = Query(50, ge=1, le=200),
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    vendor:    Optional[str] = None,
):
    share = get_share_token(token)
    if not share:
        raise HTTPException(status_code=404, detail="Link geçersiz veya süresi dolmuş.")

    user_id = share["user_id"]
    owner   = get_user_by_id(user_id)
    owner_name = (owner.get("full_name") or owner["email"]) if owner else "?"

    # Fatura listesi — owner'ın verisi
    params: dict = {}
    if date_from: params["date_from"] = date_from
    if date_to:   params["date_to"]   = date_to
    if vendor:    params["vendor"]    = vendor

    invoices = get_invoices_page(
        page=page, per_page=per_page,
        user_id=user_id, **params
    )

    # Muhasebe defteri özeti
    ledger = get_ledger(user_id=user_id, date_from=date_from, date_to=date_to)

    return {
        "owner":    owner_name,
        "label":    share.get("label"),
        "expires":  share.get("expires_at", "")[:10],
        "invoices": invoices,
        "ledger":   ledger,
    }

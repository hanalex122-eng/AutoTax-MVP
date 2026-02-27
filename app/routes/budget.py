"""AutoTax.cloud — Bütçe API"""
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel
from typing   import Optional
from app.routes.auth      import get_current_user
from app.services.budget  import (
    set_budget, get_budgets, delete_budget, get_budget_status
)
from app.services.email_service import send_async

router = APIRouter(prefix="/budget", tags=["Budget"])


def _uid(request: Request) -> str:
    return get_current_user(request)["sub"]


class BudgetIn(BaseModel):
    category: str
    amount:   float
    period:   str = "monthly"


@router.post("")
def create_or_update(body: BudgetIn, request: Request):
    if body.amount <= 0:
        raise HTTPException(400, "Bütçe tutarı sıfırdan büyük olmalı.")
    return set_budget(_uid(request), body.category, body.amount, body.period)


@router.get("")
def list_budgets(request: Request):
    return get_budgets(_uid(request))


@router.get("/status")
def budget_status(
    request: Request,
    month: Optional[str] = Query(None, description="YYYY-MM"),
):
    uid    = _uid(request)
    status = get_budget_status(uid, month)

    # Uyarı gereken kategoriler için e-posta
    from app.services.user_db import get_user_by_id
    from app.services.email_service import _base
    warnings = [s for s in status if s["status"] in ("warn", "over")]
    if warnings:
        u = get_user_by_id(uid)
        if u:
            rows = "".join(
                f"<div class='stat' style='background:{'#fee2e2' if w['status']=='over' else '#fef3c7'}'>"
                f"<strong>{w['category'].title()}</strong>: "
                f"€{w['spent']:.2f} / €{w['budget']:.2f} (%{w['pct']})</div>"
                for w in warnings
            )
            html = _base(
                "Bütçe Uyarısı",
                f"<p>Merhaba <strong>{u.get('full_name') or u['email']}</strong>,</p>"
                f"<p>Aşağıdaki kategorilerde bütçenize yaklaştınız veya aştınız:</p>"
                f"{rows}"
            )
            send_async(u["email"], "Bütçe Uyarısı — AutoTax.cloud", html)

    return status


@router.delete("/{category}")
def remove_budget(category: str, request: Request):
    delete_budget(_uid(request), category)
    return {"ok": True}

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, RedirectResponse
import os, json

router = APIRouter(prefix="/stripe", tags=["Stripe"])

STRIPE_SECRET_KEY      = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET  = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_SUCCESS_URL     = os.getenv("STRIPE_SUCCESS_URL", "http://localhost:8000/app?payment=success")
STRIPE_CANCEL_URL      = os.getenv("STRIPE_CANCEL_URL",  "http://localhost:8000/landing.html?payment=cancelled")

# Stripe fiyat ID'leri (Stripe Dashboard'dan alın)
PRICE_IDS = {
    "personal": os.getenv("STRIPE_PRICE_PERSONAL", "price_personal_monthly"),
    "family":   os.getenv("STRIPE_PRICE_FAMILY",   "price_family_monthly"),
    "business": os.getenv("STRIPE_PRICE_BUSINESS",  "price_business_monthly"),
}

PLAN_LIMITS = {
    "free":     {"invoices": 50,     "languages": 3,  "members": 1},
    "personal": {"invoices": 2000,   "languages": 8,  "members": 1},
    "family":   {"invoices": 10000,  "languages": 8,  "members": 5},
    "business": {"invoices": -1,     "languages": 8,  "members": -1},
}


def _stripe():
    """Stripe modülünü lazy import et."""
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        return stripe
    except ImportError:
        raise HTTPException(status_code=500, detail="Stripe kurulu değil. pip install stripe")


def get_current_user(request: Request):
    """JWT token'dan kullanıcıyı al."""
    from app.routes.auth import decode_access
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Oturum açmanız gerekiyor.")
    return decode_access(auth.split(" ", 1)[1])


# ── POST /stripe/create-checkout  ─────────────────────────────────────────
@router.post("/create-checkout")
async def create_checkout(request: Request):
    """Stripe Checkout Session oluştur."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe henüz yapılandırılmadı.")

    user  = get_current_user(request)
    body  = await request.json()
    plan  = body.get("plan", "pro")

    if plan not in PRICE_IDS:
        raise HTTPException(status_code=400, detail="Geçersiz plan.")

    stripe = _stripe()
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            line_items=[{"price": PRICE_IDS[plan], "quantity": 1}],
            success_url=STRIPE_SUCCESS_URL + "&session_id={CHECKOUT_SESSION_ID}",
            cancel_url=STRIPE_CANCEL_URL,
            client_reference_id=user["sub"],
            customer_email=user.get("email"),
            metadata={"user_id": user["sub"], "plan": plan},
            subscription_data={"trial_period_days": 14},
        )
        return {"checkout_url": session.url, "session_id": session.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── POST /stripe/webhook  ──────────────────────────────────────────────────
@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Stripe webhook — ödeme başarılı/iptal olduğunda planı güncelle."""
    payload   = await request.body()
    sig       = request.headers.get("stripe-signature", "")

    stripe = _stripe()
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Webhook imzası geçersiz.")

    from app.services.user_db import update_user_plan

    if event["type"] == "checkout.session.completed":
        session  = event["data"]["object"]
        user_id  = session.get("client_reference_id")
        plan     = session.get("metadata", {}).get("plan", "pro")
        sub_id   = session.get("subscription")
        if user_id:
            update_user_plan(user_id, plan, sub_id)

    elif event["type"] in ("customer.subscription.deleted", "customer.subscription.paused"):
        sub      = event["data"]["object"]
        meta     = sub.get("metadata", {})
        user_id  = meta.get("user_id")
        if user_id:
            update_user_plan(user_id, "free", None)

    elif event["type"] == "customer.subscription.updated":
        sub      = event["data"]["object"]
        meta     = sub.get("metadata", {})
        user_id  = meta.get("user_id")
        status   = sub.get("status")
        if user_id and status == "active":
            plan = meta.get("plan", "pro")
            update_user_plan(user_id, plan, sub["id"])

    return {"status": "ok"}


# ── GET /stripe/plan  ──────────────────────────────────────────────────────
@router.get("/plan")
async def get_plan(request: Request):
    """Mevcut kullanıcının planını ve limitlerini döndür."""
    user    = get_current_user(request)
    user_id = user["sub"]

    from app.services.user_db import get_user_by_id
    db_user = get_user_by_id(user_id)
    plan    = db_user.get("plan", "free") if db_user else "free"
    limits  = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])

    return {
        "plan":    plan,
        "limits":  limits,
        "display": {
            "free":     "Ücretsiz",
            "personal": "Kişisel",
            "family":   "Aile",
            "business": "İşletme",
        }.get(plan, plan),
    }


# ── POST /stripe/cancel  ──────────────────────────────────────────────────
@router.post("/cancel")
async def cancel_subscription(request: Request):
    """Aboneliği iptal et."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe henüz yapılandırılmadı.")

    user    = get_current_user(request)
    user_id = user["sub"]

    from app.services.user_db import get_user_by_id, update_user_plan
    db_user = get_user_by_id(user_id)
    sub_id  = db_user.get("stripe_subscription_id") if db_user else None

    if not sub_id:
        raise HTTPException(status_code=400, detail="Aktif abonelik bulunamadı.")

    stripe = _stripe()
    try:
        stripe.Subscription.modify(sub_id, cancel_at_period_end=True)
        return {"status": "ok", "message": "Abonelik dönem sonunda iptal edilecek."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

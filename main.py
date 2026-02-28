import os
import logging
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder

from app.routes.ocr   import router as ocr_router
from app.routes.stats import router as stats_router
from app.routes.auth  import router as auth_router, get_current_user
from app.routes.stripe_payments import router as stripe_router
from app.routes.admin import router as admin_router
from app.routes.share  import router as share_router
from app.routes.budget import router as budget_router
from app.routes.tax    import router as tax_router

# ── GDPR Uyumlu Loglama (PII içermez) ────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("autotax")

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000").split(",")

app = FastAPI(
    title="AutoTax.cloud API",
    description="Çok dilli fatura OCR, QR okuma, analiz ve SaaS abonelik platformu",
    version="4.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=True,
)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"status": "error", "message": "Geçersiz veri.",
                 "errors": jsonable_encoder(exc.errors())},
    )


@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Sunucu hatası. Lütfen tekrar deneyin."},
    )


@app.middleware("http")
async def inject_user(request: Request, call_next):
    """JWT varsa user'ı request.state'e ekle (plan kontrolü için)."""
    from app.routes.auth import decode_access
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            payload = decode_access(auth.split(" ", 1)[1])
            from app.services.user_db import get_user_by_id
            user = get_user_by_id(payload.get("sub", ""))
            request.state.user = user
        except Exception:
            request.state.user = None
    else:
        request.state.user = None
    return await call_next(request)


# Auth (public)
app.include_router(auth_router,   prefix="/api")
app.include_router(stripe_router, prefix="/api")

# Korumalı route'lar — JWT zorunlu
app.include_router(ocr_router,   prefix="/api", dependencies=[Depends(get_current_user)])
app.include_router(stats_router, prefix="/api", dependencies=[Depends(get_current_user)])

# Admin route — JWT + is_admin kontrolü
app.include_router(admin_router, prefix="/api")
# Muhasebeci paylaşım (token bazlı, JWT gerekmez)
app.include_router(share_router,  prefix="/api")
# Bütçe takibi
app.include_router(budget_router, prefix="/api", dependencies=[Depends(get_current_user)])
# Vergi / KDV raporu
app.include_router(tax_router,    prefix="/api", dependencies=[Depends(get_current_user)])


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "4.0.0"}


# ── GDPR: Hesap Silme Endpoint'i ─────────────────────────
from fastapi import HTTPException

@app.delete("/api/user/delete-account", summary="GDPR hesap silme")
async def delete_account(current_user: dict = Depends(get_current_user)):
    """
    Kullanıcının tüm verilerini (hesap + faturalar) kalıcı siler.
    GDPR Madde 17 — Unutulma Hakkı.
    """
    from app.services.user_db     import delete_user
    from app.services.invoice_db  import delete_user_invoices
    user_id = current_user["id"]
    try:
        inv_count = delete_user_invoices(user_id)
        delete_user(user_id)
        logger.info("GDPR account_deleted invoices=%d", inv_count)  # PII yok
        return {"status": "deleted", "invoices_removed": inv_count}
    except Exception as e:
        logger.error("GDPR delete_account failed: %s", type(e).__name__)
        raise HTTPException(status_code=500, detail="Hesap silinemedi. Lütfen tekrar deneyin.")


# PWA dosyaları root'ta erişilebilir olmalı (service worker scope için)
from fastapi.responses import FileResponse

@app.get("/sw.js", include_in_schema=False)
def sw():
    return FileResponse("frontend/sw.js", media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/"})

@app.get("/offline.html", include_in_schema=False)
def offline():
    return FileResponse("frontend/offline.html", media_type="text/html")

# Statik dosyalar: icon'lar ve manifest → /static/
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static_root")

# Frontend uygulama dosyaları → /app/ prefix + SPA fallback
if os.path.isdir("frontend"):
    app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

import os
import logging
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("autotax")

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000").split(",")

app = FastAPI(
    title="AutoTax.cloud API",
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
        content={"detail": "Geçersiz veri.", "errors": jsonable_encoder(exc.errors())},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Sunucu hatası. Lütfen tekrar deneyin."},
    )


@app.middleware("http")
async def inject_user(request: Request, call_next):
    from app.routes.auth import decode_access
    auth = request.headers.get("Authorization", "")
    if not auth and "access_token" in request.cookies:
        auth = "Bearer " + request.cookies["access_token"]
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


app.include_router(auth_router,   prefix="/api")
app.include_router(stripe_router, prefix="/api")
app.include_router(ocr_router,   prefix="/api", dependencies=[Depends(get_current_user)])
app.include_router(stats_router, prefix="/api", dependencies=[Depends(get_current_user)])
app.include_router(admin_router, prefix="/api")
app.include_router(share_router,  prefix="/api")
app.include_router(budget_router, prefix="/api", dependencies=[Depends(get_current_user)])
app.include_router(tax_router,    prefix="/api", dependencies=[Depends(get_current_user)])


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "4.0.0"}


@app.get("/api/setup-admin")
@app.post("/api/setup-admin")
def setup_admin():
    """Sadece hiç admin yoksa ilk admin hesabını oluşturur."""
    from app.services.user_db import _conn, _LOCK
    import bcrypt, uuid
    from datetime import datetime
    with _conn() as c:
        admin_count = c.execute("SELECT COUNT(*) FROM users WHERE is_admin=1").fetchone()[0]
        if admin_count > 0:
            raise HTTPException(status_code=403, detail="Admin zaten mevcut.")
        user_id = str(uuid.uuid4())
        pw_hash = bcrypt.hashpw("Autotax2026!".encode(), bcrypt.gensalt()).decode()
        with _LOCK:
            c.execute(
                "INSERT INTO users (id,email,full_name,password_hash,plan,is_active,is_admin,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (user_id, "hanalex122@gmail.com", "Alex Han", pw_hash, "personal", 1, 1, datetime.utcnow().isoformat())
            )
    return {"ok": True, "email": "hanalex122@gmail.com", "password": "Autotax2026!"}


@app.delete("/api/user/delete-account")
async def delete_account(current_user: dict = Depends(get_current_user)):
    from app.services.user_db    import delete_user
    from app.services.invoice_db import delete_user_invoices
    user_id = current_user["id"]
    try:
        inv_count = delete_user_invoices(user_id)
        delete_user(user_id)
        return {"status": "deleted", "invoices_removed": inv_count}
    except Exception:
        raise HTTPException(status_code=500, detail="Hesap silinemedi.")


@app.get("/sw.js", include_in_schema=False)
def sw():
    return FileResponse("frontend/sw.js", media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/"})

@app.get("/offline.html", include_in_schema=False)
def offline():
    return FileResponse("frontend/offline.html", media_type="text/html")

if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static_root")

if os.path.isdir("frontend"):
    app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

from fastapi import FastAPI, Request, Header, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
import time
import redis

# Router modülleri
from app.routes import news
from app.routes import ocr_router as ocr
from app.routers import stats_router as stats

# ---------------------------------------------------------
# REDIS RATE LIMITER (Production Ready)
# ---------------------------------------------------------
redis_client = redis.Redis(host="localhost", port=6379, db=0)

API_KEYS = {
    "FREE_KEY_123": {"limit": 50, "window": 3600},     # 50 istek / saat
    "PRO_KEY_456": {"limit": 300, "window": 3600},     # 300 istek / saat
    "ENTERPRISE_999": {"limit": 5000, "window": 3600}, # 5000 istek / saat
}

def verify_api_key(x_api_key: str = Header(None)):
    if not x_api_key or x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Geçersiz veya eksik API anahtarı.")
    return x_api_key

def rate_limit(api_key: str):
    cfg = API_KEYS[api_key]
    limit = cfg["limit"]
    window = cfg["window"]

    key = f"ratelimit:{api_key}:{int(time.time() // window)}"
    current = redis_client.incr(key)

    if current == 1:
        redis_client.expire(key, window)

    if current > limit:
        raise HTTPException(status_code=429, detail="Rate limit aşıldı. Daha sonra tekrar deneyin.")

def limiter_dependency(api_key: str = Depends(verify_api_key)):
    rate_limit(api_key)


# ---------------------------------------------------------
# FASTAPI UYGULAMASI
# ---------------------------------------------------------
app = FastAPI(
    title="AutoTax OCR API",
    description="Fatura işleme, OCR, QR, parser ve istatistik API'si",
    version="2.0.0"
)

# ---------------------------------------------------------
# ROUTER'LARI BAĞLA (Sıra önemli değil)
# ---------------------------------------------------------
app.include_router(news.router)
app.include_router(ocr.router, dependencies=[Depends(limiter_dependency)])
app.include_router(stats.router, dependencies=[Depends(limiter_dependency)])


# ---------------------------------------------------------
# GLOBAL VALIDATION ERROR HANDLER
# ---------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "message": "Geçersiz veri gönderildi. Lütfen alanları kontrol edin.",
            "errors": jsonable_encoder(exc.errors())
        },
    )


# ---------------------------------------------------------
# GLOBAL 500 ERROR HANDLER (PRODUCTION)
# ---------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Sunucu hatası oluştu. Loglara bakın.",
            "detail": str(exc)
        },
    )

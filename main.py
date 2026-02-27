import os
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder

from app.routes.ocr   import router as ocr_router
from app.routes.stats import router as stats_router
from app.routes.auth  import router as auth_router, get_current_user

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000").split(",")

app = FastAPI(
    title="AutoTax OCR API",
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


# Auth (public)
app.include_router(auth_router, prefix="/api")

# Korumalı route'lar — JWT zorunlu
app.include_router(ocr_router,   prefix="/api", dependencies=[Depends(get_current_user)])
app.include_router(stats_router, prefix="/api", dependencies=[Depends(get_current_user)])


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "4.0.0"}


if os.path.isdir("frontend"):
    app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

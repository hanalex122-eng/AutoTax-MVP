import os
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request, Response, Cookie
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, field_validator
from jose import JWTError, jwt

from app.services.user_db import (
    create_user, get_user_by_email, get_user_by_id,
    verify_password, update_last_login,
    save_refresh_token, get_refresh_token, revoke_refresh_token,
    revoke_all_user_tokens, check_quota, PLANS,
)

router = APIRouter(prefix="/auth", tags=["Auth"])

# ── JWT config (env'den çek, yoksa dev secret) ────────────
JWT_SECRET      = os.getenv("JWT_SECRET", "CHANGE_THIS_IN_PRODUCTION_autotax_secret_2026")
JWT_ALGORITHM   = "HS256"
ACCESS_TTL_MIN  = int(os.getenv("JWT_ACCESS_TTL_MIN", "60"))    # 1 saat
REFRESH_TTL_DAY = int(os.getenv("JWT_REFRESH_TTL_DAYS", "30"))  # 30 gün
COOKIE_SECURE   = os.getenv("COOKIE_SECURE", "false").lower() == "true"

_bearer = HTTPBearer(auto_error=False)


# ── Pydantic modeller ─────────────────────────────────────
class RegisterIn(BaseModel):
    email:     EmailStr
    password:  str
    full_name: str = ""

    @field_validator("password")
    @classmethod
    def pw_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Şifre en az 8 karakter olmalıdır.")
        return v


class LoginIn(BaseModel):
    email:    EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: Optional[str] = None


# ── JWT yardımcıları ──────────────────────────────────────
def _make_access(user_id: str, email: str, plan: str) -> str:
    exp = datetime.utcnow() + timedelta(minutes=ACCESS_TTL_MIN)
    return jwt.encode(
        {"sub": user_id, "email": email, "plan": plan,
         "type": "access", "exp": exp},
        JWT_SECRET, algorithm=JWT_ALGORITHM,
    )


def _make_refresh(user_id: str) -> str:
    token = str(uuid.uuid4())
    save_refresh_token(token, user_id, REFRESH_TTL_DAY)
    return token


def decode_access(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise JWTError("wrong type")
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Geçersiz veya süresi dolmuş token.")


# ── Dependency: mevcut kullanıcı ──────────────────────────
def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    access_token: Optional[str] = Cookie(default=None),
) -> dict:
    raw = None
    if creds:
        raw = creds.credentials
    elif access_token:
        raw = access_token

    if not raw:
        raise HTTPException(status_code=401, detail="Oturum açmanız gerekiyor.")

    payload = decode_access(raw)
    user    = get_user_by_id(payload["sub"])
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı veya devre dışı.")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Yönetici yetkisi gerekiyor.")
    return user


# ── Endpoint'ler ──────────────────────────────────────────
@router.post("/register", status_code=201)
def register(data: RegisterIn, response: Response):
    if get_user_by_email(data.email):
        raise HTTPException(status_code=409, detail="Bu e-posta zaten kayıtlı.")
    user    = create_user(data.email, data.password, data.full_name)
    access  = _make_access(user["id"], user["email"], user["plan"])
    refresh = _make_refresh(user["id"])
    _set_cookies(response, access, refresh)
    return _token_response(access, refresh, user)


@router.post("/login")
def login(data: LoginIn, response: Response):
    user = get_user_by_email(data.email)
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="E-posta veya şifre hatalı.")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Hesabınız askıya alınmış.")
    update_last_login(user["id"])
    access  = _make_access(user["id"], user["email"], user["plan"])
    refresh = _make_refresh(user["id"])
    _set_cookies(response, access, refresh)
    return _token_response(access, refresh, user)


@router.post("/refresh")
def refresh_token(
    response: Response,
    body: RefreshIn = RefreshIn(),
    refresh_token_cookie: Optional[str] = Cookie(default=None, alias="refresh_token"),
):
    raw = body.refresh_token or refresh_token_cookie
    if not raw:
        raise HTTPException(status_code=401, detail="Refresh token bulunamadı.")
    record = get_refresh_token(raw)
    if not record:
        raise HTTPException(status_code=401, detail="Geçersiz veya süresi dolmuş refresh token.")
    user = get_user_by_id(record["user_id"])
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı.")
    revoke_refresh_token(raw)
    access      = _make_access(user["id"], user["email"], user["plan"])
    new_refresh = _make_refresh(user["id"])
    _set_cookies(response, access, new_refresh)
    return _token_response(access, new_refresh, user)


@router.post("/logout")
def logout(
    response: Response,
    body: RefreshIn = RefreshIn(),
    refresh_token_cookie: Optional[str] = Cookie(default=None, alias="refresh_token"),
    user: dict = Depends(get_current_user),
):
    raw = body.refresh_token or refresh_token_cookie
    if raw:
        revoke_refresh_token(raw)
    _clear_cookies(response)
    return {"message": "Oturum kapatıldı."}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    allowed, used, limit = check_quota(user)
    return {
        "id":          user["id"],
        "email":       user["email"],
        "full_name":   user["full_name"],
        "plan":        user["plan"],
        "plan_label":  PLANS.get(user["plan"], PLANS["free"])["label"],
        "plan_expires": user.get("plan_expires"),
        "is_admin":    bool(user["is_admin"]),
        "created_at":  user["created_at"],
        "usage": {
            "used":    used,
            "limit":   limit,
            "allowed": allowed,
        },
    }


# ── Cookie yardımcıları ───────────────────────────────────
def _set_cookies(response: Response, access: str, refresh: str):
    kw = dict(httponly=True, samesite="lax", secure=COOKIE_SECURE)
    response.set_cookie("access_token",  access,  max_age=ACCESS_TTL_MIN * 60, **kw)
    response.set_cookie("refresh_token", refresh, max_age=REFRESH_TTL_DAY * 86400, **kw)


def _clear_cookies(response: Response):
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")


def _token_response(access: str, refresh: str, user: dict) -> dict:
    allowed, used, limit = check_quota(user)
    return {
        "access_token":  access,
        "refresh_token": refresh,
        "token_type":    "bearer",
        "expires_in":    ACCESS_TTL_MIN * 60,
        "user": {
            "id":         user["id"],
            "email":      user["email"],
            "full_name":  user["full_name"],
            "plan":       user["plan"],
            "plan_label": PLANS.get(user["plan"], PLANS["free"])["label"],
            "usage": {"used": used, "limit": limit},
        },
    }

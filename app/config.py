import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# Railway'de /data kalıcı Volume mount noktası — yoksa /app/storage kullan
_BASE = Path(os.getenv("STORAGE_PATH", "/data" if Path("/data").exists() else "storage"))
_BASE.mkdir(parents=True, exist_ok=True)


class Settings:
    REDIS_HOST: str        = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int        = int(os.getenv("REDIS_PORT", "6379"))
    TESSERACT_CMD: str     = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    SR_MODEL_PATH: str     = os.getenv("SR_MODEL_PATH", "models/ESPCN_x2.pb")
    DB_PATH: str           = os.getenv("DB_PATH",      str(_BASE / "invoices_db.json"))
    SQLITE_PATH: str       = os.getenv("SQLITE_PATH",  str(_BASE / "invoices.db"))
    USERS_DB_PATH: str     = os.getenv("USERS_DB_PATH", str(_BASE / "users.db"))
    UPLOAD_DIR: str        = os.getenv("UPLOAD_DIR",   str(_BASE / "uploads"))
    OCR_LANG: str          = os.getenv("OCR_LANG", "deu+eng+fra+spa+ara+kor+chi_sim")
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"

    def __post_init__(self):
        Path(self.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


settings = Settings()

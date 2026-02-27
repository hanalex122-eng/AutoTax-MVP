import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    REDIS_HOST: str        = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int        = int(os.getenv("REDIS_PORT", "6379"))
    TESSERACT_CMD: str     = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    SR_MODEL_PATH: str     = os.getenv("SR_MODEL_PATH", "models/ESPCN_x2.pb")
    DB_PATH: str           = os.getenv("DB_PATH", "storage/invoices_db.json")
    SQLITE_PATH: str       = os.getenv("SQLITE_PATH", "storage/invoices.db")
    OCR_LANG: str          = os.getenv("OCR_LANG", "deu+eng+fra+spa+ara+kor+chi_sim")
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"


settings = Settings()

import os
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

class Settings:
    NEWS_API_KEY = os.getenv("NEWS_API_KEY")

settings = Settings()

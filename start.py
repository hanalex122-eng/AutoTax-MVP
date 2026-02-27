# AutoTax — Production Başlatma
# Kullanım: python start.py
import subprocess, sys, os

os.makedirs("storage/incoming",  exist_ok=True)
os.makedirs("storage/processed", exist_ok=True)
os.makedirs("models",            exist_ok=True)

if not os.path.exists("storage/invoices_db.json"):
    import json
    with open("storage/invoices_db.json", "w") as f:
        json.dump({"invoices": []}, f)

subprocess.run([
    sys.executable, "-m", "uvicorn", "main:app",
    "--host",    "0.0.0.0",
    "--port",    "8000",
    "--workers", "2",
    "--log-level", "info",
])

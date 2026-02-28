"""Railway / production başlatıcı — PORT env'i güvenli okur."""
import os, sys, traceback

def main():
    port = int(os.environ.get("PORT", 8000))
    print(f"[AutoTax] Python {sys.version}", flush=True)
    print(f"[AutoTax] PORT={port}", flush=True)
    print(f"[AutoTax] CWD={os.getcwd()}", flush=True)
    print(f"[AutoTax] SQLITE_PATH={os.environ.get('SQLITE_PATH','storage/invoices.db')}", flush=True)

    try:
        print("[AutoTax] main.py import ediliyor...", flush=True)
        import main as app_module
        print("[AutoTax] Import OK", flush=True)
    except Exception as e:
        print(f"[AutoTax] IMPORT HATASI: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)

    try:
        import uvicorn
        print(f"[AutoTax] Sunucu başlatılıyor: 0.0.0.0:{port}", flush=True)
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=port,
            workers=1,
            proxy_headers=True,
            forwarded_allow_ips="*",
            access_log=True,
        )
    except Exception as e:
        print(f"[AutoTax] UVICORN HATASI: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

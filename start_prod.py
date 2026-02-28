"""Railway / production başlatıcı."""
import os, sys, traceback

def main():
    # Railway domain port 8000 olarak ayarlandı — sabit kullan
    port = 8000
    print(f"[AutoTax] Python {sys.version}", flush=True)
    print(f"[AutoTax] PORT={port} (sabit)", flush=True)
    print(f"[AutoTax] CWD={os.getcwd()}", flush=True)
    print(f"[AutoTax] ENV_PORT={os.environ.get('PORT','YOK')}", flush=True)

    try:
        print("[AutoTax] Importing main...", flush=True)
        import main as _
        print("[AutoTax] Import OK", flush=True)
    except Exception as e:
        print(f"[AutoTax] IMPORT ERROR: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)

    try:
        import uvicorn
        print(f"[AutoTax] Starting on 0.0.0.0:{port}", flush=True)
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
        print(f"[AutoTax] UVICORN ERROR: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

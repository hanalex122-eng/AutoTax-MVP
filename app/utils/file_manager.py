import os
import json
from datetime import datetime
from PIL import Image

STORAGE_PATH = "storage"
INCOMING_PATH = "storage/incoming"
PROCESSED_PATH = "storage/processed"
FAILED_PATH = "storage/failed"
DB_FILE = "invoices_db.json"


# ---------------------------------------------------------
# 1) Dosyayı sıkıştır
# ---------------------------------------------------------
def compress_image(input_path, output_path, quality=75):
    try:
        img = Image.open(input_path)
        img = img.convert("RGB")
        img.save(output_path, "JPEG", optimize=True, quality=quality)
        return True
    except Exception as e:
        print("Sıkıştırma hatası:", e)
        return False


# ---------------------------------------------------------
# 2) JSON kayıt ekle
# ---------------------------------------------------------
def save_invoice_record(invoice_id, customer_id, total, status, file_path):
    record = {
        "invoice_id": invoice_id,
        "customer_id": customer_id,
        "total": total,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "status": status,
        "file_path": file_path
    }

    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=4)

    with open(DB_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    data.append(record)

    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


# ---------------------------------------------------------
# 3) Faturayı işleme al
# ---------------------------------------------------------
def process_invoice(filename, success=True, customer_id="UNKNOWN", total=0.0):
    input_path = os.path.join(INCOMING_PATH, filename)

    # Yeni dosya adı
    invoice_id = f"INV-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    output_filename = f"{invoice_id}.jpg"

    if success:
        output_path = os.path.join(PROCESSED_PATH, output_filename)
        status = "processed"
    else:
        output_path = os.path.join(FAILED_PATH, output_filename)
        status = "failed"

    # Sıkıştır ve taşı
    compress_image(input_path, output_path)

    # JSON kayıt ekle
    save_invoice_record(
        invoice_id=invoice_id,
        customer_id=customer_id,
        total=total,
        status=status,
        file_path=output_path
    )

    # incoming dosyasını sil
    os.remove(input_path)

    return invoice_id, status

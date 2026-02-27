import os
import shutil

# Bu dosya: app/services/file_manager.py
# Storage: AutoTax-MVP/storage
BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage")

INCOMING_DIR = os.path.join(BASE_DIR, "incoming")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")
FAILED_DIR = os.path.join(BASE_DIR, "failed")

def ensure_dirs():
    os.makedirs(INCOMING_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(FAILED_DIR, exist_ok=True)

def save_incoming(filename: str, content: bytes):
    ensure_dirs()
    path = os.path.join(INCOMING_DIR, filename)
    with open(path, "wb") as f:
        f.write(content)
    return path

def move_to_processed(path: str):
    ensure_dirs()
    new_path = os.path.join(PROCESSED_DIR, os.path.basename(path))
    shutil.move(path, new_path)
    return new_path

def move_to_failed(path: str):
    ensure_dirs()
    new_path = os.path.join(FAILED_DIR, os.path.basename(path))
    shutil.move(path, new_path)
    return new_path

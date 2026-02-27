import os
import shutil

INCOMING_FOLDER = "storage/incoming"
PROCESSED_FOLDER = "storage/processed"

def get_new_files():
    files = []
    for filename in os.listdir(INCOMING_FOLDER):
        full_path = os.path.join(INCOMING_FOLDER, filename)
        if os.path.isfile(full_path):
            files.append(full_path)
    return files

def move_to_processed(file_path):
    filename = os.path.basename(file_path)
    new_path = os.path.join(PROCESSED_FOLDER, filename)
    shutil.move(file_path, new_path)
    return new_path

def process_incoming_files():
    files = get_new_files()
    if not files:
        print("Yeni dosya yok.")
        return

    for file_path in files:
        print(f"İşleniyor: {file_path}")
        move_to_processed(file_path)
        print(f"Taşındı -> processed/: {file_path}")

if __name__ == "__main__":
    process_incoming_files()

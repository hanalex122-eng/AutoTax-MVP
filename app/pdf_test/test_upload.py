import requests

url = "http://localhost:8000/ocr/upload"

with open("app/pdf_test/deneme.pdf", "rb") as f:
    files = {"file": f}
    response = requests.post(url, files=files)

print("Status:", response.status_code)
print("Response:", response.text)

from pydantic import BaseModel
from typing import Optional


class InvoiceModel(BaseModel):
    invoice_id: str
    filename: str
    raw_text: Optional[str] = None
    qr_raw: Optional[str] = None
    qr_parsed: Optional[dict] = None
    vendor: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    total: Optional[float] = None
    vat_amount: Optional[float] = None
    vat_rate: Optional[int] = None
    invoice_no: Optional[str] = None
    category: Optional[str] = None
    payment_method: Optional[str] = None
    company_from_qr: Optional[str] = None
    needs_review: bool = False
    review_reason: Optional[str] = None
    message: str = "OCR tamamlandı"

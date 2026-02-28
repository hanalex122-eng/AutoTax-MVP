from pydantic import BaseModel
from typing import Optional, Any


class InvoiceResult(BaseModel):
    invoice_id: str
    filename: str
    vendor: Optional[str]          = None
    date: Optional[str]            = None
    time: Optional[str]            = None
    total: Optional[float]         = None
    vat_rate: Optional[int]        = None
    vat_amount: Optional[float]    = None
    invoice_no: Optional[str]      = None
    category: Optional[str]        = None
    payment_method: Optional[str]  = None
    qr_raw: Optional[str]          = None
    qr_parsed: Optional[Any]       = None
    raw_text: Optional[str]        = None
    needs_review: bool             = False
    review_reason: Optional[str]   = None
    message: str                   = "OK"


class SummaryResponse(BaseModel):
    count: int
    total_sum: float
    vat_sum: float
    by_vendor: dict
    by_category: dict
    invoices: list

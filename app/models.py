from pydantic import BaseModel, Field
from typing import List, Optional

class InvoiceCorrectionRequest(BaseModel):
    filename: str
    user_total_value: float = Field(..., gt=0)
    user_total_confirmed: bool
    fast_mode: Optional[bool] = False

class ValidationErrorDetail(BaseModel):
    loc: List[str]
    msg: str
    type: str

class ValidationErrorResponse(BaseModel):
    detail: List[ValidationErrorDetail]

class InvoiceSummary(BaseModel):
    filename: str
    vendor_name: Optional[str]
    total_amount: Optional[float]
    date: Optional[str]
    country: Optional[str]
    status: str  # "ok" veya "needs_correction"

class SummaryReportResponse(BaseModel):
    status: str
    invoices: List[InvoiceSummary]

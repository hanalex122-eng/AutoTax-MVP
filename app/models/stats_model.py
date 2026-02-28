from pydantic import BaseModel

class StatsModel(BaseModel):
    total_invoices: int
    total_amount: float
    vendors: int

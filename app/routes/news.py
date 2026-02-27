from fastapi import APIRouter, Query
from typing import Optional
from app.utils.news_api import get_news_from_api

router = APIRouter(
    prefix="/news",
    tags=["News"]
)

@router.get("/search")
def search_news(
    query: str = Query(..., description="Anahtar kelime (örnek: 'vergi', 'fatura')"),
    language: str = Query("en", description="Dil kodu (örnek: 'en', 'de', 'tr')"),
    from_date: Optional[str] = Query(None, description="Başlangıç tarihi (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="Bitiş tarihi (YYYY-MM-DD)"),
    category: Optional[str] = Query(None, description="Kategori (örnek: 'business', 'technology')"),
    country: Optional[str] = Query(None, description="Ülke kodu (örnek: 'us', 'de', 'tr')"),
    source: Optional[str] = Query(None, description="Haber kaynağı (örnek: 'reuters', 'bbc-news')"),
    page_size: int = Query(10, description="Sayfa başına haber sayısı"),
    sort_by: str = Query("publishedAt", description="Sıralama (örnek: 'publishedAt', 'popularity')")
):
    result = get_news_from_api(
        query=query,
        language=language,
        from_date=from_date,
        to_date=to_date,
        category=category,
        country=country,
        source=source,
        page_size=page_size,
        sort_by=sort_by
    )
    return result

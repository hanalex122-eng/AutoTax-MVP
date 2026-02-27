import requests
from app.secrets_config import settings

def get_news_from_api(query, language, from_date, to_date, category, country, source, page_size, sort_by):
    url = "https://newsapi.org/v2/everything"

    params = {
        "q": query,
        "language": language,
        "from": from_date,
        "to": to_date,
        "pageSize": page_size,
        "sortBy": sort_by,
        "apiKey": settings.NEWS_API_KEY
    }

    if source:
        params["sources"] = source

    response = requests.get(url, params=params)
    return response.json()

"""
news.py — NewsAPI integration (free plan: 100 req/day)
Usage per run: 3 calls (EMBASSY + BIRET + macro) — well within free limits.
"""
import requests
from datetime import datetime, timedelta
from config import NEWS_API_KEY, NEWS_QUERIES, MACRO_QUERY


def _fetch(query: str, days_back: int = 3, page_size: int = 5) -> list:
    """
    Core fetch helper. Returns list of article dicts.
    Each article has: title, description, url, publishedAt, source.name
    """
    if not NEWS_API_KEY:
        print("[news] NEWS_API_KEY not set — skipping news fetch.")
        return []

    from_date = (datetime.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    url = "https://newsapi.org/v2/everything"
    params = {
        "q":        query,
        "from":     from_date,
        "sortBy":   "relevancy",
        "language": "en",
        "pageSize": page_size,
        "apiKey":   NEWS_API_KEY,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("articles", [])
    except requests.RequestException as e:
        print(f"[news] API error for query '{query}': {e}")
        return []


def fetch_stock_news(stock_name: str, days_back: int = 3) -> list:
    """Fetch news for a specific stock (EMBASSY or BIRET)."""
    query = NEWS_QUERIES.get(stock_name, stock_name)
    return _fetch(query, days_back=days_back, page_size=5)


def fetch_macro_news() -> list:
    """Fetch macro India REIT / interest rate news."""
    return _fetch(MACRO_QUERY, days_back=3, page_size=3)


def fetch_all_news() -> dict:
    """
    Fetch all news in one call. Returns:
    {
        "EMBASSY": [...articles],
        "BIRET":   [...articles],
        "macro":   [...articles],
    }
    """
    return {
        "EMBASSY": fetch_stock_news("EMBASSY"),
        "BIRET":   fetch_stock_news("BIRET"),
        "macro":   fetch_macro_news(),
    }

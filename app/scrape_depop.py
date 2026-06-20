"""
scrape_depop.py — search Depop for active listings matching a query.

Uses Depop's internal API (same endpoints their website calls).
Returns a list of dicts: {title, price, url, photo, source}.
"""

import logging
import time
from typing import Any, Dict, List

import requests

log = logging.getLogger(__name__)

_DEPOP_SEARCH = "https://api.depop.com/api/v2/search/products/"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.depop.com",
    "Referer": "https://www.depop.com/",
    "depop-app-type": "web",
}


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_HEADERS)
    return s


def search_depop(query: str, limit: int = 24, session=None) -> List[Dict[str, Any]]:
    """
    Search Depop for active listings matching query.
    Returns list of {title, price, url, photo, source, condition}.
    """
    sess = session or _make_session()
    params = {
        "q": query,
        "country": "us",
        "currency": "USD",
        "lang": "en",
        "limit": limit,
        "offset": 0,
        "availability": "sold_out=false",
    }
    try:
        r = sess.get(_DEPOP_SEARCH, params=params, timeout=12)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("[depop] search failed for %r: %s", query, e)
        return []

    results = []
    for item in data.get("objects", []):
        p = item.get("preview") or {}
        pictures = item.get("pictures") or []
        photo = pictures[0].get("url") if pictures else None

        price_info = item.get("price") or {}
        try:
            price = float(price_info.get("priceAmount") or price_info.get("amount") or 0)
        except (TypeError, ValueError):
            price = 0.0

        slug = item.get("slug") or item.get("id")
        seller = (item.get("seller") or {}).get("username", "")
        url = f"https://www.depop.com/products/{slug}/" if slug else ""

        if not price or not url:
            continue

        condition_raw = item.get("condition") or ""
        condition = condition_raw.replace("_", " ").title() if condition_raw else None

        results.append({
            "title": item.get("description") or item.get("title") or query,
            "price": price,
            "url": url,
            "photo": photo,
            "source": "depop",
            "condition": condition,
        })

    log.info("[depop] %r → %d listings", query, len(results))
    return results

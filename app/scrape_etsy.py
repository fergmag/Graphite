"""
scrape_etsy.py — search Etsy for active listings via their official API v3.

Requires ETSY_API_KEY env var. Get a free key at:
https://www.etsy.com/developers/register

No OAuth needed for public listing search.
"""

import logging
import os
from typing import Any, Dict, List

import requests

log = logging.getLogger(__name__)

_ETSY_BASE = "https://openapi.etsy.com/v3/application"


def search_etsy(query: str, limit: int = 25, timeout: int = 12) -> List[Dict[str, Any]]:
    """
    Search Etsy active listings matching query.
    Returns list of {title, price, url, photo, source}.
    """
    api_key = os.environ.get("ETSY_API_KEY", "")
    if not api_key:
        log.warning("[etsy] ETSY_API_KEY not set, skipping")
        return []

    # Prepend "carhartt" so Etsy finds the brand even when query is just a model code
    search_terms = query if "carhartt" in query.lower() else f"carhartt {query}"

    log.info("[etsy] using key starting with %s... for %r", api_key[:6], query)
    headers = {"x-api-key": api_key}
    # includes must be repeated params, not a list — use a list of tuples
    params = [
        ("keywords", search_terms),
        ("limit", str(limit)),
        ("sort_on", "score"),
        ("includes[]", "Images"),
        ("includes[]", "MainImage"),
    ]

    try:
        r = requests.get(
            f"{_ETSY_BASE}/listings/active",
            params=params,
            headers=headers,
            timeout=timeout,
        )
        log.info("[etsy] GET %s → %d", r.url, r.status_code)
        if r.status_code != 200:
            log.warning("[etsy] non-200 for %r: %d %s", query, r.status_code, r.text[:200])
            return []
        data = r.json()
    except Exception as e:
        log.warning("[etsy] request failed for %r: %s: %s", query, type(e).__name__, e)
        return []

    results = []
    for listing in data.get("results", []):
        listing_id = listing.get("listing_id")
        if not listing_id:
            continue

        price_info = listing.get("price") or {}
        try:
            price = float(price_info.get("amount", 0)) / float(price_info.get("divisor") or 100)
        except (TypeError, ValueError, ZeroDivisionError):
            price = 0.0

        if not price:
            continue

        url = listing.get("url") or f"https://www.etsy.com/listing/{listing_id}"

        main_image = listing.get("MainImage") or {}
        photo = main_image.get("url_570xN") or main_image.get("url_fullxfull")

        results.append({
            "title": listing.get("title") or query,
            "price": price,
            "url": url,
            "photo": photo,
            "source": "etsy",
            "condition": None,  # Etsy doesn't have a standard condition field
        })

    raw_count = len(data.get("results", []))
    log.info("[etsy] %r → %d raw / %d parsed", query, raw_count, len(results))
    return results

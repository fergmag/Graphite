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


def search_etsy(query: str, limit: int = 25) -> List[Dict[str, Any]]:
    """
    Search Etsy active listings matching query.
    Returns list of {title, price, url, photo, source}.
    """
    api_key = os.environ.get("ETSY_API_KEY", "")
    if not api_key:
        log.warning("[etsy] ETSY_API_KEY not set, skipping")
        return []

    params = {
        "keywords": query,
        "limit": limit,
        "sort_on": "score",
        "includes": ["Images", "MainImage"],
    }
    headers = {"x-api-key": api_key}

    try:
        r = requests.get(
            f"{_ETSY_BASE}/listings/active",
            params=params,
            headers=headers,
            timeout=12,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("[etsy] search failed for %r: %s", query, e)
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

    log.info("[etsy] %r → %d listings", query, len(results))
    return results

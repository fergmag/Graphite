"""
scrape_grailed.py — search Grailed for active listings via their Algolia index.

Grailed's search is powered by Algolia. Their app ID and search-only API key
are embedded in their public JS bundle and are safe to use for read queries.
"""

import logging
from typing import Any, Dict, List

import requests

log = logging.getLogger(__name__)

# Grailed's public Algolia credentials (search-only, embedded in their JS)
_ALGOLIA_APP_ID = "XW7SBCT9AD"
_ALGOLIA_SEARCH_KEY = "a0b38c4e7f40fec1bd8f3beb44e21d9c"
_ALGOLIA_INDEX = "Listing_production"
_ALGOLIA_URL = f"https://{_ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{_ALGOLIA_INDEX}/query"

_HEADERS = {
    "X-Algolia-Application-Id": _ALGOLIA_APP_ID,
    "X-Algolia-API-Key": _ALGOLIA_SEARCH_KEY,
    "Content-Type": "application/json",
}


def search_grailed(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Search Grailed for active listings matching query.
    Returns list of {title, price, url, photo, source, condition, size}.
    """
    body = {
        "query": query,
        "hitsPerPage": limit,
        "filters": "sold=0 AND NOT is_draft=1",
        "attributesToRetrieve": [
            "id", "title", "price", "cover_photo", "condition",
            "size", "seller", "category_path",
        ],
    }
    try:
        r = requests.post(_ALGOLIA_URL, headers=_HEADERS, json=body, timeout=12)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("[grailed] search failed for %r: %s", query, e)
        return []

    results = []
    for hit in data.get("hits", []):
        listing_id = hit.get("id")
        if not listing_id:
            continue

        try:
            price = float(hit.get("price") or 0)
        except (TypeError, ValueError):
            price = 0.0

        if not price:
            continue

        cover = hit.get("cover_photo") or {}
        photo = cover.get("url") if isinstance(cover, dict) else None

        url = f"https://www.grailed.com/listings/{listing_id}"

        condition_map = {
            "is_gently_used": "Gently Used",
            "is_used": "Used",
            "is_worn": "Worn",
            "is_new": "New / Never Worn",
        }
        condition = next(
            (label for key, label in condition_map.items() if hit.get(key)),
            None,
        )

        results.append({
            "title": hit.get("title") or query,
            "price": price,
            "url": url,
            "photo": photo,
            "source": "grailed",
            "condition": condition,
            "size": hit.get("size"),
        })

    log.info("[grailed] %r → %d listings", query, len(results))
    return results

"""
scrape_etsy.py — search Etsy for active listings via their official API v3.

Requires ETSY_API_KEY env var. Get a free key at:
https://www.etsy.com/developers/register

No OAuth needed for public listing search.
"""

import logging
import os
import re
from typing import Any, Dict, List

import requests

# Model code pattern: e.g. "jb0817", "j97", "j65", "js1235", "jr0115"
_MODEL_CODE_RE = re.compile(r'\b(?:carhartt\s+)?[a-z]{1,3}\d{3,5}\b', re.IGNORECASE)

log = logging.getLogger(__name__)

_ETSY_BASE = "https://openapi.etsy.com/v3/application"


def search_etsy(query: str, limit: int = 25, timeout: int = 12) -> List[Dict[str, Any]]:
    """
    Search Etsy active listings matching query.
    Returns list of {title, price, url, photo, source}.
    """
    api_key = os.environ.get("ETSY_API_KEY", "")
    shared_secret = os.environ.get("ETSY_SHARED_SECRET", "")
    if not api_key:
        log.warning("[etsy] ETSY_API_KEY not set, skipping")
        return []

    # Etsy v3 requires "{keystring}:{shared_secret}" in x-api-key for public endpoints.
    # If only the keystring is set, the API returns 403 "Shared secret is required".
    if shared_secret:
        auth_value = f"{api_key}:{shared_secret}"
        log.warning("[etsy] using keystring:sharedsecret format (key prefix %s...) for %r", api_key[:6], query)
    else:
        auth_value = api_key
        log.warning("[etsy] ETSY_SHARED_SECRET not set — requests will likely fail with 403")

    # Prepend "carhartt" so Etsy finds the brand even when query is just a model code
    search_terms = query if "carhartt" in query.lower() else f"carhartt {query}"

    headers = {"x-api-key": auth_value}
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

        # Etsy v3 may return images under MainImage or images[]
        photo = None
        main_image = listing.get("MainImage") or {}
        photo = main_image.get("url_570xN") or main_image.get("url_fullxfull")
        if not photo:
            images = listing.get("images") or []
            if images:
                first = images[0] if isinstance(images[0], dict) else {}
                photo = first.get("url_570xN") or first.get("url_fullxfull") or first.get("url_170x135")

        results.append({
            "title": listing.get("title") or query,
            "price": price,
            "url": url,
            "photo": photo,
            "source": "etsy",
            "condition": None,
        })

    raw_count = len(data.get("results", []))
    photos = sum(1 for r in results if r.get("photo"))
    log.warning("[etsy] %r → %d raw / %d parsed / %d with photo", query, raw_count, len(results), photos)

    # If Etsy returned 0 results for a model-code query, retry with descriptive color terms.
    # Etsy sellers don't use model codes — "carhartt j97 moss" finds nothing,
    # but "vintage carhartt moss" might find the same jackets.
    if not results and _MODEL_CODE_RE.search(search_terms):
        color_words = _MODEL_CODE_RE.sub('', search_terms).strip()
        # also strip "carhartt" from the residue so we rebuild cleanly
        color_words = re.sub(r'\bcarhartt\b', '', color_words, flags=re.IGNORECASE).strip()
        if color_words:
            broader = f"vintage carhartt {color_words}"
            log.warning("[etsy] 0 results for %r — retrying broader: %r", query, broader)
            broader_params = [
                ("keywords", broader),
                ("limit", str(limit)),
                ("sort_on", "score"),
                ("includes[]", "Images"),
                ("includes[]", "MainImage"),
            ]
            try:
                r2 = requests.get(
                    f"{_ETSY_BASE}/listings/active",
                    params=broader_params,
                    headers=headers,
                    timeout=timeout,
                )
                if r2.status_code == 200:
                    data2 = r2.json()
                    for listing in data2.get("results", []):
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
                        photo = None
                        main_image = listing.get("MainImage") or {}
                        photo = main_image.get("url_570xN") or main_image.get("url_fullxfull")
                        if not photo:
                            images = listing.get("images") or []
                            if images:
                                first = images[0] if isinstance(images[0], dict) else {}
                                photo = first.get("url_570xN") or first.get("url_fullxfull") or first.get("url_170x135")
                        results.append({
                            "title": listing.get("title") or query,
                            "price": price,
                            "url": url,
                            "photo": photo,
                            "source": "etsy",
                            "condition": None,
                        })
                    log.warning("[etsy] broader retry %r → %d raw / %d parsed", broader, len(data2.get("results", [])), len(results))
            except Exception as e:
                log.warning("[etsy] broader retry failed: %s", e)

    return results

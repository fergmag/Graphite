"""
scrape_etsy.py — search Etsy for active listings via their official API v3.

Requires ETSY_API_KEY and ETSY_SHARED_SECRET env vars.

Note: findAllListingsActive does not support includes[]. Images are fetched
in a separate batch call to getListings?listing_ids=...&includes[]=Images.
"""

import logging
import os
import re
from typing import Any, Dict, List, Tuple, Optional

import requests

log = logging.getLogger(__name__)

_ETSY_BASE = "https://openapi.etsy.com/v3/application"
_MODEL_CODE_RE = re.compile(r'\b(?:carhartt\s+)?[a-z]{1,3}\d{3,5}\b', re.IGNORECASE)


def _parse_etsy_listings(raw: List[dict], query: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Parse raw Etsy listing dicts. Returns (results, listing_id_strings). photo=None; caller fills."""
    results, ids = [], []
    for listing in raw:
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
        results.append({
            "_lid": listing_id,
            "title": listing.get("title") or query,
            "price": price,
            "url": listing.get("url") or f"https://www.etsy.com/listing/{listing_id}",
            "photo": None,
            "source": "etsy",
            "condition": None,
        })
        ids.append(str(listing_id))
    return results, ids


def _fetch_etsy_images(listing_ids: List[str], headers: dict, timeout: int) -> Dict[int, str]:
    """
    Fetch images via GET /listings/{id}/images — the dedicated image endpoint.
    Returns first image URL per listing. Runs concurrently, capped at 15.
    """
    if not listing_ids:
        return {}

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from typing import Optional, Tuple

    def fetch_one(lid: str) -> Optional[Tuple[int, str]]:
        try:
            url = f"{_ETSY_BASE}/listings/{lid}/images"
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code != 200:
                log.warning("[etsy] /images %s → %d", lid, r.status_code)
                return None
            images = r.json().get("results", [])
            for img in images:
                if not isinstance(img, dict):
                    continue
                photo = img.get("url_570xN") or img.get("url_fullxfull") or img.get("url_170x135")
                if photo:
                    return (int(lid), photo)
            return None
        except Exception:
            return None

    ids_to_fetch = listing_ids[:15]
    image_map: Dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(fetch_one, lid): lid for lid in ids_to_fetch}
        for future in as_completed(futures):
            result = future.result()
            if result:
                image_map[result[0]] = result[1]

    log.warning("[etsy] image fetch: %d/%d with photo", len(image_map), len(ids_to_fetch))
    return image_map


def search_etsy(query: str, limit: int = 25, timeout: int = 12) -> List[Dict[str, Any]]:
    """
    Search Etsy active listings matching query.
    Returns list of {title, price, url, photo, source, condition}.
    """
    api_key = os.environ.get("ETSY_API_KEY", "")
    shared_secret = os.environ.get("ETSY_SHARED_SECRET", "")
    if not api_key:
        log.warning("[etsy] ETSY_API_KEY not set, skipping")
        return []

    if shared_secret:
        auth_value = f"{api_key}:{shared_secret}"
        log.warning("[etsy] using keystring:sharedsecret format (key prefix %s...) for %r", api_key[:6], query)
    else:
        auth_value = api_key
        log.warning("[etsy] ETSY_SHARED_SECRET not set — requests will likely fail with 403")

    search_terms = query if "carhartt" in query.lower() else f"carhartt {query}"
    headers = {"x-api-key": auth_value}

    try:
        r = requests.get(
            f"{_ETSY_BASE}/listings/active",
            params=[
                ("keywords", search_terms),
                ("limit", str(limit)),
                ("sort_on", "score"),
            ],
            headers=headers,
            timeout=timeout,
        )
        log.info("[etsy] GET → %d for %r", r.status_code, query)
        if r.status_code != 200:
            log.warning("[etsy] non-200 for %r: %d %s", query, r.status_code, r.text[:200])
            return []
        data = r.json()
    except Exception as e:
        log.warning("[etsy] request failed for %r: %s", query, e)
        return []

    results, listing_ids = _parse_etsy_listings(data.get("results", []), query)
    if results:
        image_map = _fetch_etsy_images(listing_ids, headers, timeout)
        for item in results:
            item["photo"] = image_map.get(item.pop("_lid"))

    raw_count = len(data.get("results", []))
    photos = sum(1 for item in results if item.get("photo"))
    log.warning("[etsy] %r → %d raw / %d parsed / %d with photo", query, raw_count, len(results), photos)

    # If 0 results for a model-code query, strip the code and retry with color keywords.
    # Etsy sellers don't use Carhartt model codes — "carhartt j97 moss" finds nothing,
    # but "vintage carhartt moss" will find matching jackets.
    if not results and _MODEL_CODE_RE.search(search_terms):
        color_words = _MODEL_CODE_RE.sub('', search_terms).strip()
        color_words = re.sub(r'\bcarhartt\b', '', color_words, flags=re.IGNORECASE).strip()
        if color_words:
            broader = f"vintage carhartt {color_words}"
            log.warning("[etsy] retrying broader: %r", broader)
            try:
                r2 = requests.get(
                    f"{_ETSY_BASE}/listings/active",
                    params=[
                        ("keywords", broader),
                        ("limit", str(limit)),
                        ("sort_on", "score"),
                    ],
                    headers=headers,
                    timeout=timeout,
                )
                if r2.status_code == 200:
                    data2 = r2.json()
                    retry_results, retry_ids = _parse_etsy_listings(data2.get("results", []), query)
                    if retry_results:
                        image_map2 = _fetch_etsy_images(retry_ids, headers, timeout)
                        for item in retry_results:
                            item["photo"] = image_map2.get(item.pop("_lid"))
                    photos2 = sum(1 for item in retry_results if item.get("photo"))
                    log.warning("[etsy] broader %r → %d parsed / %d with photo", broader, len(retry_results), photos2)
                    results.extend(retry_results)
            except Exception as e:
                log.warning("[etsy] broader retry error: %s", e)

    return results

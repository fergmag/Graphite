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


def _extract_inline_photo(listing: dict) -> Optional[str]:
    """Pull image URL from inline includes[] data if Etsy returned it."""
    main = listing.get("main_image") or listing.get("MainImage") or {}
    if main:
        return main.get("url_570xN") or main.get("url_fullxfull") or main.get("url_170x135")
    for key in ("images", "listing_images", "Images"):
        imgs = listing.get(key)
        if imgs and isinstance(imgs, list):
            for img in imgs:
                if isinstance(img, dict):
                    url = img.get("url_570xN") or img.get("url_fullxfull") or img.get("url_170x135")
                    if url:
                        return url
    return None


def _parse_etsy_listings(raw: List[dict], query: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Parse raw Etsy listing dicts. Extracts inline photo if present; caller fetches missing ones."""
    results, ids_needing_photo = [], []
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
        photo = _extract_inline_photo(listing)
        results.append({
            "_lid": listing_id,
            "title": listing.get("title") or query,
            "price": price,
            "url": listing.get("url") or f"https://www.etsy.com/listing/{listing_id}",
            "photo": photo,
            "source": "etsy",
        })
        if not photo:
            ids_needing_photo.append(str(listing_id))
    return results, ids_needing_photo


def _fetch_etsy_images(listing_ids: List[str], headers: dict, timeout: int) -> Dict[int, str]:
    """
    Batch-fetch photos via GET /listings?listing_ids=...&includes[]=MainImage.
    One request for up to 100 IDs — avoids per-listing rate limits.
    Falls back to chunked requests if batch returns no images.
    """
    if not listing_ids:
        return {}

    image_map: Dict[int, str] = {}

    def _extract_photo(listing: dict) -> Optional[str]:
        main = listing.get("main_image") or listing.get("MainImage") or {}
        if main:
            return main.get("url_570xN") or main.get("url_fullxfull") or main.get("url_170x135")
        for key in ("images", "listing_images", "Images"):
            imgs = listing.get(key)
            if imgs and isinstance(imgs, list):
                for img in imgs:
                    if isinstance(img, dict):
                        url = img.get("url_570xN") or img.get("url_fullxfull") or img.get("url_170x135")
                        if url:
                            return url
        return None

    # Process in chunks of 100 (Etsy API max per request)
    for i in range(0, len(listing_ids), 100):
        chunk = listing_ids[i:i+100]
        ids_csv = ",".join(chunk)
        try:
            url = (f"{_ETSY_BASE}/listings"
                   f"?listing_ids={ids_csv}"
                   f"&includes[]=MainImage&includes[]=Images")
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 429:
                log.warning("[etsy] batch photo fetch 429 — backing off 2s")
                import time as _time; _time.sleep(2)
                r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code != 200:
                log.warning("[etsy] batch /listings → %d %s", r.status_code, r.text[:80])
                continue
            for listing in r.json().get("results", []):
                lid = listing.get("listing_id")
                photo = _extract_photo(listing)
                if lid and photo:
                    image_map[int(lid)] = photo
        except Exception as e:
            log.warning("[etsy] batch photo fetch error: %s", e)

    log.warning("[etsy] batch image fetch: %d/%d with photo", len(image_map), len(listing_ids))
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
        # Build URL manually — requests.get(params=...) encodes [] as %5B%5D which Etsy ignores
        from urllib.parse import quote as _quote
        _kw = _quote(search_terms, safe='')
        _url = f"{_ETSY_BASE}/listings/active?keywords={_kw}&limit={limit}&sort_on=score&includes[]=MainImage&includes[]=Images"
        r = requests.get(_url, headers=headers, timeout=timeout)
        log.info("[etsy] GET → %d for %r", r.status_code, query)
        if r.status_code != 200:
            log.warning("[etsy] non-200 for %r: %d %s", query, r.status_code, r.text[:200])
            return []
        data = r.json()
    except Exception as e:
        log.warning("[etsy] request failed for %r: %s", query, e)
        return []

    # _parse_etsy_listings extracts inline photos if includes[] worked;
    # ids_needing_photo lists those still missing a photo for the fallback fetch
    results, ids_needing_photo = _parse_etsy_listings(data.get("results", []), query)
    inline_photos = sum(1 for r in results if r.get("photo"))
    log.warning("[etsy] %r → %d parsed, %d inline photos", query, len(results), inline_photos)

    if ids_needing_photo:
        image_map = _fetch_etsy_images(ids_needing_photo, headers, timeout)
        for item in results:
            if not item.get("photo"):
                item["photo"] = image_map.get(item["_lid"])

    # Remove internal _lid key
    for item in results:
        item.pop("_lid", None)

    photos = sum(1 for item in results if item.get("photo"))
    log.warning("[etsy] %r → %d raw / %d parsed / %d with photo", query, len(data.get("results", [])), len(results), photos)

    # If 0 results for a model-code query, strip the code and retry with color keywords.
    if not results and _MODEL_CODE_RE.search(search_terms):
        color_words = _MODEL_CODE_RE.sub('', search_terms).strip()
        color_words = re.sub(r'\bcarhartt\b', '', color_words, flags=re.IGNORECASE).strip()
        if color_words:
            broader = f"vintage carhartt {color_words}"
            log.warning("[etsy] retrying broader: %r", broader)
            try:
                _kw2 = _quote(broader, safe='')
                _url2 = f"{_ETSY_BASE}/listings/active?keywords={_kw2}&limit={limit}&sort_on=score&includes[]=MainImage&includes[]=Images"
                r2 = requests.get(_url2, headers=headers, timeout=timeout)
                if r2.status_code == 200:
                    data2 = r2.json()
                    retry_results, retry_ids2 = _parse_etsy_listings(data2.get("results", []), query)
                    if retry_ids2:
                        image_map2 = _fetch_etsy_images(retry_ids2, headers, timeout)
                        for item in retry_results:
                            if not item.get("photo"):
                                item["photo"] = image_map2.get(item["_lid"])
                    for item in retry_results:
                        item.pop("_lid", None)
                    log.warning("[etsy] broader %r → %d parsed", broader, len(retry_results))
                    results.extend(retry_results)
            except Exception as e:
                log.warning("[etsy] broader retry error: %s", e)

    return results

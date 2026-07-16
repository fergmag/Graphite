"""
scrape_ebay.py — eBay active listings via Browse API (OAuth application token).

eBay sold comps are permanently removed: the Finding API (svcs.ebay.com) and
HTML scraping are blocked from Render/AWS IPs. CASP comes from manual prices
in models.json; deal-alert scanning uses search_ebay_active.

Requires EBAY_APP_ID + EBAY_CERT_ID env vars for Browse API OAuth token.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger(__name__)

_browse_token: dict = {"token": None, "expires_at": 0.0}
_BROWSE_SCOPE = "https%3A%2F%2Fapi.ebay.com%2Foauth%2Fapi_scope"


def _fetch_ebay_token(cache: dict, scope: str) -> Optional[str]:
    import base64
    import time as _time
    app_id = os.environ.get("EBAY_APP_ID", "")
    cert_id = os.environ.get("EBAY_CERT_ID", "")
    if not app_id or not cert_id:
        return None
    now = _time.time()
    if cache["token"] and now < cache["expires_at"] - 60:
        return cache["token"]
    creds = base64.b64encode(f"{app_id}:{cert_id}".encode()).decode()
    try:
        r = requests.post(
            "https://api.ebay.com/identity/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {creds}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=f"grant_type=client_credentials&scope={scope}",
            timeout=10,
        )
        if r.status_code != 200:
            log.warning("[ebay-token] failed: %d %s", r.status_code, r.text[:200])
            return None
        d = r.json()
        cache["token"] = d.get("access_token")
        cache["expires_at"] = now + int(d.get("expires_in", 7200))
        log.warning("[ebay-token] got token, expires in %ds", d.get("expires_in", 0))
        return cache["token"]
    except Exception as e:
        log.warning("[ebay-token] error: %s", e)
        return None


def _get_browse_token() -> Optional[str]:
    return _fetch_ebay_token(_browse_token, _BROWSE_SCOPE)


def search_ebay_active(query: str, max_results: int = 30) -> List[Dict[str, Any]]:
    """
    Search eBay active listings via Browse API.
    Returns list of {title, price, url, photo, source, size}.
    """
    token = _get_browse_token()
    if not token:
        log.debug("[ebay-browse] no token — need EBAY_APP_ID + EBAY_CERT_ID")
        return []

    search_terms = f"carhartt {query}" if "carhartt" not in query.lower() else query
    try:
        r = requests.get(
            "https://api.ebay.com/buy/browse/v1/item_summary/search",
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
                "Content-Type": "application/json",
            },
            params={
                "q": search_terms,
                "limit": str(min(max_results, 50)),
                "filter": "conditions:{USED|VERY_GOOD|GOOD|ACCEPTABLE},buyingOptions:{FIXED_PRICE}",
                "sort": "price",
            },
            timeout=12,
        )
        log.warning("[ebay-browse] GET → %d for %r", r.status_code, query)
        if r.status_code != 200:
            log.warning("[ebay-browse] %d %s", r.status_code, r.text[:200])
            return []
        data = r.json()
    except Exception as e:
        log.warning("[ebay-browse] request error: %s", e)
        return []

    results = []
    for item in data.get("itemSummaries", []):
        try:
            price_info = item.get("price", {})
            price = float(price_info.get("value", 0))
            if not price:
                continue
            shipping_options = item.get("shippingOptions", [])
            ship_cost = 0.0
            if shipping_options:
                sc = shipping_options[0].get("shippingCost", {})
                ship_cost = float(sc.get("value", 0))
            image = item.get("image", {}).get("imageUrl")
            size = None
            for aspect in item.get("localizedAspects", []):
                if aspect.get("name", "").lower() == "size":
                    from app.filters import normalize_size as _ns
                    size = _ns(aspect.get("value"))
                    break
            results.append({
                "title": item.get("title", ""),
                "price": price + ship_cost,
                "url": item.get("itemWebUrl", ""),
                "photo": image,
                "source": "ebay",
                "size": size,
            })
        except Exception:
            continue

    log.warning("[ebay-browse] %r → %d active listings", query, len(results))
    return results

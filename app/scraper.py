"""
scraper.py — background scrape-and-save logic.

Extracted from the /estimate route so it can be called by the APScheduler
job without going through HTTP.  The scheduler lives in main.py.
"""

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.scrape_ebay import scrape_ebay_sold, _make_session
from app.pricing import comps_to_prices, summarize_prices, to_dict
from app.cache import write_cache
from app.public_view import build_public_payload
from app.filters import filter_comps, normalize_query
from app.db import list_watches, insert_comps, insert_estimate

log = logging.getLogger(__name__)

try:
    from app.model_profiles import get_manual_casp_for_query  # type: ignore
except Exception:
    get_manual_casp_for_query = None  # type: ignore

# ── In-memory state (resets on process restart, good enough) ──
_last_ran_at: Optional[str] = None
_last_summary: Dict[str, Any] = {}


def _normalize_comp(c: Dict[str, Any], source: str) -> Dict[str, Any]:
    url = c.get("url")
    m = re.search(r"/itm/(?:[^/]+/)?(\d+)", url or "")
    listing_id = c.get("listing_id") or (m.group(1) if m else None)
    return {
        "title": c.get("title"),
        "price": c.get("price"),
        "shipping": c.get("shipping"),
        "currency": c.get("currency") or c.get("shipping_currency"),
        "url": url,
        "ended": c.get("ended"),
        "ended_at": c.get("ended_at") or c.get("ended"),
        "source": source,
        "model_guess": c.get("model_guess"),
        "listing_id": listing_id,
    }


def scrape_and_save(raw_query: str, session=None) -> Dict[str, Any]:
    """
    Scrape eBay for one query, compute CASP, write to cache + DB.
    Returns a small result dict (ok, n, casp, reason).
    """
    query = normalize_query(raw_query)
    try:
        raw_comps = scrape_ebay_sold(query, pages=1, delay=0.5, session=session)
    except RuntimeError as e:
        log.warning("[scraper] %s — scrape failed: %s", query, e)
        return {"query": query, "ok": False, "reason": str(e)}

    # Normalise + dedupe
    seen: set = set()
    normalized: List[Dict[str, Any]] = []
    for c in raw_comps:
        nc = _normalize_comp(c.__dict__, "ebay")
        key = nc.get("listing_id") or nc.get("url")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        normalized.append(nc)

    normalized = filter_comps(normalized, query)
    prices = comps_to_prices(normalized, include_shipping=False)
    summary = summarize_prices(prices)
    summary_dict = to_dict(summary)

    casp = summary_dict.get("median")
    if get_manual_casp_for_query:
        try:
            override = get_manual_casp_for_query(query)
            if override is not None:
                casp = override
        except Exception:
            pass

    public = build_public_payload(
        casp=casp,
        confidence=float(summary_dict.get("confidence") or 0.0),
    )
    payload = {
        "n": summary.n,
        "public": public,
        "summary": summary_dict,
        "sample": normalized[:5],
    }

    write_cache(query, payload)
    insert_comps(query, normalized)
    insert_estimate(query, public_payload=public, summary_payload=summary_dict)

    log.info("[scraper] %s — n=%d casp=%s", query, summary.n, casp)
    return {"query": query, "ok": True, "n": summary.n, "casp": casp}


def refresh_all_watchlist(delay_seconds: float = 55.0) -> Dict[str, Any]:
    """
    Iterate every watchlist query, scrape and save each one.
    Called by the APScheduler job and the manual /admin/refresh-now endpoint.
    delay_seconds: pause between queries to avoid eBay rate-limits.
    """
    global _last_ran_at, _last_summary

    queries = list_watches()
    log.info("[scheduler] Starting refresh — %d queries", len(queries))

    # One shared session per refresh run — keeps cookies across queries
    sess = _make_session()

    ok_count = 0
    fail_count = 0
    for i, q in enumerate(queries):
        result = scrape_and_save(q, session=sess)
        if result["ok"]:
            ok_count += 1
        else:
            fail_count += 1
        # Don't sleep after the last one
        if i < len(queries) - 1:
            time.sleep(delay_seconds)

    _last_ran_at = datetime.now(timezone.utc).isoformat()
    _last_summary = {
        "ran_at": _last_ran_at,
        "total": len(queries),
        "ok": ok_count,
        "failed": fail_count,
    }
    log.info("[scheduler] Done — %d ok, %d failed", ok_count, fail_count)
    return _last_summary


def get_refresh_status() -> Dict[str, Any]:
    return {"ran_at": _last_ran_at, **_last_summary}

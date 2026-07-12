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

from app.scrape_ebay import scrape_ebay_sold, search_ebay_active, _make_session
from app.scrape_depop import search_depop
from app.scrape_grailed import search_grailed
from app.scrape_etsy import search_etsy
from app.scrape_whatnot import search_whatnot
from app.pricing import comps_to_prices, summarize_prices, to_dict
from app.cache import write_cache
from app.public_view import build_public_payload
from app.filters import filter_comps, normalize_query, parse_size_from_title
from app.db import list_watches, insert_comps, insert_estimate, insert_alert, clear_old_alerts, alert_url_exists
from app.vision import grade_condition

_VISION_CAP = 5  # max new vision API calls per query per scan

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
    raw_comps = []
    ebay_error = None
    try:
        raw_comps = scrape_ebay_sold(query, pages=1, delay=0.5, session=session)
    except RuntimeError as e:
        ebay_error = str(e)
        log.warning("[scraper] %s — eBay scrape failed: %s", query, e)

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

    # If eBay failed and we got no comps, only proceed if we have a manual CASP
    if not normalized and ebay_error:
        if casp is None:
            return {"query": query, "ok": False, "reason": ebay_error}
        log.info("[scraper] %s — eBay failed but manual CASP=%.0f, proceeding with platform scan", query, casp)
        return {"query": query, "ok": True, "n": 0, "casp": casp}

    log.info("[scraper] %s — n=%d casp=%s", query, summary.n, casp)
    return {"query": query, "ok": True, "n": summary.n, "casp": casp}


_SIZE_MULT: Dict[str, float] = {"M": 1.0, "L": 0.80, "XL": 0.50, "XXL": 0.20}


def _deal_score(price: float, casp: float, size: Optional[str] = None) -> int:
    """Return deal score 1–5 based on price vs size-adjusted CASP."""
    if casp <= 0:
        return 1
    adjusted = casp * _SIZE_MULT.get(size or "", 1.0)
    ratio = price / adjusted
    if ratio <= 0.50:
        return 5
    if ratio <= 0.65:
        return 4
    if ratio <= 0.80:
        return 3
    if ratio <= 0.95:
        return 2
    return 1


def scan_platforms_for_query(query: str, casp: Optional[float]) -> int:
    """
    Search Depop, Grailed, and Etsy for active listings matching query.
    Saves any listing with deal_score >= 3 as an alert.
    Returns count of alerts saved.
    """
    saved = 0

    # Platforms where sellers use model codes in titles → strict code filter
    strict_listings: List[Dict[str, Any]] = []
    strict_listings.extend(search_ebay_active(query))
    strict_listings.extend(search_grailed(query))
    strict_listings = filter_comps(strict_listings, query, require_code=True)

    # Platforms with targeted search (already sent "carhartt {query}") → junk filter only
    relaxed_listings: List[Dict[str, Any]] = []
    relaxed_listings.extend(search_depop(query))
    relaxed_listings.extend(search_etsy(query))
    relaxed_listings.extend(search_whatnot(query))
    relaxed_listings = filter_comps(relaxed_listings, query, require_code=False)

    all_listings = strict_listings + relaxed_listings

    vision_calls = 0
    for listing in all_listings:
        price = listing.get("price") or 0
        if not price:
            continue
        url = listing.get("url", "")
        size = listing.get("size") or parse_size_from_title(listing.get("title", ""))
        score = _deal_score(price, casp or 0, size) if casp else 1
        if score >= 1:
            vision_grade = vision_notes = None
            photo = listing.get("photo")
            # Only call vision for new listings not already in DB, capped per scan
            if photo and not alert_url_exists(url) and vision_calls < _VISION_CAP:
                result = grade_condition(photo)
                vision_calls += 1
                if result:
                    vision_grade = result.get("grade")
                    vision_notes = result.get("notes")
            insert_alert(
                query=query,
                source=listing["source"],
                title=listing.get("title", ""),
                price=price,
                url=url,
                photo=photo,
                casp=casp,
                deal_score=score,
                size=size,
                vision_grade=vision_grade,
                vision_notes=vision_notes,
            )
            saved += 1

    return saved


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

    clear_old_alerts(days=30)

    ok_count = 0
    fail_count = 0
    alerts_saved = 0
    for i, q in enumerate(queries):
        result = scrape_and_save(q, session=sess)
        if result["ok"]:
            ok_count += 1
            casp = result.get("casp")
            try:
                n = scan_platforms_for_query(q, casp)
                alerts_saved += n
                if n > 0:
                    try:
                        from app.main import _persist_alerts
                        _persist_alerts()
                    except Exception:
                        pass
            except Exception as e:
                log.warning("[scheduler] platform scan failed for %r: %s", q, e)
        else:
            fail_count += 1
        if i < len(queries) - 1:
            time.sleep(delay_seconds)

    _last_ran_at = datetime.now(timezone.utc).isoformat()
    _last_summary = {
        "ran_at": _last_ran_at,
        "total": len(queries),
        "ok": ok_count,
        "failed": fail_count,
        "alerts_saved": alerts_saved,
    }
    log.info("[scheduler] Done — %d ok, %d failed, %d alerts", ok_count, fail_count, alerts_saved)
    return _last_summary


def get_refresh_status() -> Dict[str, Any]:
    return {"ran_at": _last_ran_at, **_last_summary}

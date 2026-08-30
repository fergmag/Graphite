"""
scraper.py — background watchlist refresh and deal-alert scanning.

scrape_and_save: writes the manual CASP from models.json to cache + DB each
refresh cycle. This is what populates the price-history graph.

scan_platforms_for_query: scans Grailed, eBay Browse, Depop, Etsy, Whatnot
for active listings and saves any good deals as alerts.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.scrape_ebay import search_ebay_active
from app.scrape_depop import search_depop
from app.scrape_grailed import search_grailed
from app.scrape_etsy import search_etsy
from app.scrape_whatnot import search_whatnot
from app.cache import write_cache
from app.public_view import build_public_payload
from app.filters import filter_comps, normalize_query, parse_size_from_title, search_terms_for_query
from app.db import list_watches, insert_comps, insert_estimate, insert_alert, clear_old_alerts, insert_refresh_log, get_refresh_log

log = logging.getLogger(__name__)

try:
    from app.model_profiles import get_manual_casp_for_query  # type: ignore
except Exception:
    get_manual_casp_for_query = None  # type: ignore

_last_ran_at: Optional[str] = None
_last_summary: Dict[str, Any] = {}


def scrape_and_save(raw_query: str, session=None) -> Dict[str, Any]:
    """
    Per refresh cycle:
    - Fetch active Grailed + eBay listings → market_casp for display
    - Write manual CASP from models.json to the graph (DB estimates)
    - Cache market_casp (shown as Estimated Value) + manual_casp in summary (for deal scoring)
    """
    query = normalize_query(raw_query)

    # Manual CASP: flat reference price from models.json (for graph + deal scoring)
    manual_casp: Optional[float] = None
    if get_manual_casp_for_query:
        try:
            manual_casp = get_manual_casp_for_query(query)
        except Exception:
            pass

    # Market CASP: mean of active Grailed + eBay Browse listings (for display).
    # Search with both canonical name and abbreviation (e.g. "j97 timber" + "j97 tmb")
    # because sellers often use abbreviations that the canonical search misses.
    active: List[Dict[str, Any]] = []
    seen_urls: set = set()
    for term in search_terms_for_query(query):
        try:
            for g in filter_comps(search_grailed(term), query, require_code=False):
                if g.get("price") and g.get("url") not in seen_urls:
                    active.append(g)
                    seen_urls.add(g.get("url", ""))
        except Exception as e:
            log.warning("[scraper] %s — grailed(%s): %s", query, term, e)
        try:
            for item in filter_comps(search_ebay_active(term), query, require_code=False):
                if item.get("price") and item.get("url") not in seen_urls:
                    active.append(item)
                    seen_urls.add(item.get("url", ""))
        except Exception as e:
            log.warning("[scraper] %s — ebay(%s): %s", query, term, e)

    prices = sorted(c["price"] for c in active if c.get("price"))
    market_casp: Optional[float] = sum(prices) / len(prices) if prices else None
    confidence = min(1.0, len(prices) / 10.0) if prices else 0.0

    if manual_casp is None and market_casp is None:
        log.warning("[scraper] %s — no CASP available, skipping", query)
        return {"query": query, "ok": False, "reason": "no CASP available"}

    # Graph gets market CASP so the chart shows real price trends over time.
    # Falls back to manual CASP if no market data was found this run.
    graph_casp = market_casp or manual_casp
    graph_public = build_public_payload(casp=graph_casp, confidence=confidence)
    insert_estimate(query, public_payload=graph_public, summary_payload={"median": graph_casp, "confidence": confidence, "n": len(active)})

    # Cache stores market_casp for Estimated Value display; manual_casp for deal scoring
    display_casp = market_casp or manual_casp
    display_public = build_public_payload(casp=display_casp, confidence=confidence)
    summary_dict: Dict[str, Any] = {
        "median": display_casp,
        "confidence": confidence,
        "n": len(active),
        "manual_casp": manual_casp,
    }
    payload: Dict[str, Any] = {
        "n": len(active),
        "public": display_public,
        "summary": summary_dict,
        "sample": active[:5],
    }
    write_cache(query, payload)
    insert_comps(query, active)

    log.warning("[scraper] %s — market=%.0f (n=%d), manual=%s → graph", query, display_casp or 0, len(active), manual_casp)
    return {"query": query, "ok": True, "n": len(active), "casp": display_casp, "manual_casp": manual_casp}


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
    Search all platforms for active listings matching query.
    Saves any listing as an alert (deal_score >= 1 always saves for visibility).
    Returns count of alerts saved.
    """
    saved = 0

    # Search with canonical name AND abbreviation to catch sellers using either form
    search_aliases = search_terms_for_query(query)

    # Grailed sellers reliably include model codes in titles → strict code filter
    strict_raw: List[Dict[str, Any]] = []
    seen_strict: set = set()
    for term in search_aliases:
        for item in search_grailed(term):
            u = item.get("url", "")
            if u not in seen_strict:
                strict_raw.append(item)
                seen_strict.add(u)
    strict_listings = filter_comps(strict_raw, query, require_code=True)

    # eBay/Etsy/Depop/Whatnot: search engine does the scoping, sellers often omit
    # model codes from titles ("Detroit Jacket Moss" not "J97 Moss") → relaxed filter
    relaxed_raw: List[Dict[str, Any]] = []
    seen_relaxed: set = set()
    for term in search_aliases:
        for item in search_ebay_active(term) + search_depop(term) + search_etsy(term) + search_whatnot(term):
            u = item.get("url", "")
            if u not in seen_relaxed:
                relaxed_raw.append(item)
                seen_relaxed.add(u)
    relaxed_listings = filter_comps(relaxed_raw, query, require_code=False)

    for listing in strict_listings + relaxed_listings:
        price = listing.get("price") or 0
        if not price:
            continue
        # Skip Etsy listings without a photo — they're almost always scam/spam
        if listing.get("source") == "etsy" and not listing.get("photo"):
            continue
        url = listing.get("url", "")
        size = listing.get("size") or parse_size_from_title(listing.get("title", ""))
        score = _deal_score(price, casp or 0, size) if casp else 1
        if score >= 1:
            insert_alert(
                query=query,
                source=listing["source"],
                title=listing.get("title", ""),
                price=price,
                url=url,
                photo=listing.get("photo"),
                casp=casp,
                deal_score=score,
                size=size,
                vision_grade=None,
                vision_notes=None,
            )
            saved += 1

    return saved


def refresh_all_watchlist(delay_seconds: float = 5.0) -> Dict[str, Any]:
    """
    Iterate every watchlist query, write CASP data point and scan for deals.
    5s delay between queries — polite to Grailed/Etsy but fast enough for the
    6h APScheduler interval to work without overlapping runs.
    """
    global _last_ran_at, _last_summary

    queries = list_watches()
    log.info("[scheduler] Starting refresh — %d queries", len(queries))

    clear_old_alerts(days=7)

    ok_count = 0
    fail_count = 0
    alerts_saved = 0
    for i, q in enumerate(queries):
        result = scrape_and_save(q)
        if result["ok"]:
            ok_count += 1
            # Deal scoring uses manual CASP (owner's reference price), not the market median
            casp = result.get("manual_casp") or result.get("casp")
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
    try:
        insert_refresh_log(_last_summary)
    except Exception as e:
        log.warning("[scheduler] refresh_log insert failed: %s", e)
    log.info("[scheduler] Done — %d ok, %d failed, %d alerts", ok_count, fail_count, alerts_saved)
    return _last_summary


def get_refresh_status() -> Dict[str, Any]:
    try:
        history = get_refresh_log(limit=20)
    except Exception:
        history = []
    return {"ran_at": _last_ran_at, **_last_summary, "history": history}

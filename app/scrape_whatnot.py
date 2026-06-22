"""
scrape_whatnot.py — Whatnot active listing scraper.

Whatnot uses Cloudflare with JS challenge, which blocks all server-side
requests (403 from Render). Requires Playwright + cf-clearance cookie rotation
to access. Returning [] until a bypass solution is implemented.
"""
import logging
from typing import Any, Dict, List

log = logging.getLogger(__name__)


def search_whatnot(query: str) -> List[Dict[str, Any]]:
    log.debug("[whatnot] scraping blocked (Cloudflare) — skipping")
    return []

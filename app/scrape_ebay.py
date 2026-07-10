import argparse
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass
from typing import List, Optional, Tuple
from urllib.parse import urlencode, quote_plus

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_FINDING_API_URL = "https://svcs.ebay.com/services/search/FindingService/v1"

EBAY_SEARCH_URL = "https://www.ebay.com/sch/i.html"

@dataclass
class EbayComp:
    title: str
    price: Optional[float]
    currency: Optional[str]
    shipping: Optional[float]
    shipping_currency: Optional[str]
    url: str
    ended: Optional[str]

def _clean_title(raw: str) -> str:
    t = raw.strip()
    t = re.sub(r"^\s*New Listing\s*", "", t, flags=re.IGNORECASE).strip()
    return t

def _parse_money(text: str) -> Tuple[Optional[float], Optional[str]]:
    if not text:
        return None, None
    t = text.strip()

    currency = None
    if "C $" in t:
        currency = "CAD"
    elif "US $" in t:
        currency = "USD"
    elif "AU $" in t:
        currency = "AUD"
    elif "£" in t or "GBP" in t:
        currency = "GBP"
    elif "€" in t or "EUR" in t:
        currency = "EUR"
    elif "$" in t:
        currency = "USD"

    m = re.search(r"(\d[\d,]*\.?\d*)", t)
    if not m:
        return None, currency
    
    num_str = m.group(1).replace(",", "")
    try:
        return float(num_str), currency
    except ValueError:
        return None, currency
    
def _parse_shipping(text: str) -> Tuple[Optional[float], Optional[str]]:
    if not text:
        return None, None

    t = text.strip()
    if "Free" in t:
        return 0.0, None

    value, currency = _parse_money(t)
    return value, currency

def build_sold_search_url(query: str, page: int = 1) -> str:
    params = {
        "_nkw": query,
        "LH_Sold": "1",
        "LH_Complete": "1",
        "_sop": "13",
        "_pgn": str(page),
    }
    return f"{EBAY_SEARCH_URL}?{urlencode(params)}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "DNT": "1",
    "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def _make_session() -> requests.Session:
    """Return a session pre-warmed with eBay cookies."""
    s = requests.Session()
    s.headers.update(_HEADERS)
    try:
        r = s.get("https://www.ebay.com/", timeout=10)
        # If warmup itself gets a bot page, add a delay
        if "Pardon Our Interruption" in r.text:
            time.sleep(5)
    except Exception:
        pass
    return s


def _is_bot_page(text: str) -> bool:
    return "Pardon Our Interruption" in text or "Robot Check" in text


def fetch_html(url: str, timeout: int = 15, max_retries: int = 3,
               session: Optional[requests.Session] = None) -> str:
    own_session = session is None
    s = session or _make_session()

    last_status = None
    for attempt in range(1, max_retries + 1):
        try:
            r = s.get(url, timeout=timeout)
        except requests.RequestException as e:
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 10))
                continue
            raise RuntimeError(f"eBay request error: {e}") from e

        last_status = r.status_code

        if r.status_code == 200:
            if _is_bot_page(r.text):
                # Soft bot block — fail fast, Render has a 30s request timeout
                if attempt < max_retries:
                    time.sleep(2)
                    continue
                raise RuntimeError(f"eBay bot detection (soft block) for {url}")
            return r.text

        if r.status_code == 403:
            if attempt < max_retries:
                time.sleep(3)
                continue
            break

        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(2 ** attempt, 10))
            continue

        break

    raise RuntimeError(f"eBay request failed: {last_status} for {url}")


def parse_sold_results(html: str) -> List[EbayComp]:
    soup = BeautifulSoup(html, "lxml")
    comps: List[EbayComp] = []

    for li in soup.select("li.s-item"):
        title_el = li.select_one(".s-item__title")
        link_el = li.select_one("a.s-item__link")
        price_el = li.select_one(".s-item__price")

        if not title_el or not link_el or not price_el:
            continue

        raw_title = title_el.get_text(" ", strip=True)

        if not raw_title or raw_title.lower() in {"shop on ebay"}:
            continue

        title = _clean_title(raw_title)
        url = link_el.get("href", "").strip()
        if not url:
            continue

        price_text = price_el.get_text(" ", strip=True)
        price, currency = _parse_money(price_text)

        ship_el = li.select_one(".s-item__shipping, .s-item__logisticsCost")
        ship_text = ship_el.get_text(" ", strip=True) if ship_el else ""
        shipping, ship_currency = _parse_shipping(ship_text)

        ended_el = li.select_one(".s-item__ended-date")
        ended = ended_el.get_text(" ", strip=True) if ended_el else None

        comps.append(
            EbayComp(
                title=title,
                price=price,
                currency=currency,
                shipping=shipping,
                shipping_currency=ship_currency,
                url=url,
                ended=ended,
            )
        )

    return comps

def _ebay_finding_api(query: str, max_results: int = 50) -> List[EbayComp]:
    """
    Use the eBay Finding API (findCompletedItems) to get sold listings.
    Requires EBAY_APP_ID env var. Works from datacenter IPs unlike HTML scraping.
    """
    app_id = os.environ.get("EBAY_APP_ID", "")
    if not app_id:
        raise RuntimeError("EBAY_APP_ID not configured")

    params = {
        "OPERATION-NAME": "findCompletedItems",
        "SERVICE-VERSION": "1.0.0",
        "SECURITY-APPNAME": app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "REST-PAYLOAD": "",
        "keywords": query,
        "itemFilter(0).name": "SoldItemsOnly",
        "itemFilter(0).value": "true",
        "itemFilter(1).name": "Currency",
        "itemFilter(1).value": "USD",
        "sortOrder": "EndTimeSoonest",
        "paginationInput.entriesPerPage": str(min(max_results, 100)),
        "outputSelector": "SellerInfo",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Graphite/1.0)",
        "Accept": "application/json",
    }
    r = requests.get(_FINDING_API_URL, params=params, headers=headers, timeout=15)
    if r.status_code != 200:
        log.warning("[ebay-api] %d for %r — body: %s", r.status_code, query, r.text[:300])
        raise RuntimeError(f"eBay Finding API returned {r.status_code}")

    try:
        data = r.json()
    except Exception as e:
        raise RuntimeError(f"eBay Finding API bad JSON: {e}") from e

    try:
        items = (
            data
            .get("findCompletedItemsResponse", [{}])[0]
            .get("searchResult", [{}])[0]
            .get("item", [])
        )
    except (IndexError, KeyError):
        items = []

    comps: List[EbayComp] = []
    for item in items:
        try:
            title = item.get("title", [""])[0]
            url = item.get("viewItemURL", [""])[0]
            price_raw = float(
                item.get("sellingStatus", [{}])[0]
                    .get("convertedCurrentPrice", [{}])[0]
                    .get("__value__", 0)
            )
            shipping_raw = item.get("shippingInfo", [{}])[0]
            ship_cost_list = shipping_raw.get("shippingServiceCost", [])
            if ship_cost_list:
                shipping = float(ship_cost_list[0].get("__value__", 0))
            else:
                shipping = None
            ended = item.get("listingInfo", [{}])[0].get("endTime", [""])[0]
            comps.append(EbayComp(
                title=title,
                price=price_raw,
                currency="USD",
                shipping=shipping,
                shipping_currency="USD" if shipping is not None else None,
                url=url,
                ended=ended,
            ))
        except Exception:
            continue

    log.info("[ebay-api] findCompletedItems query=%r → %d items", query, len(comps))
    return comps


def scrape_ebay_sold(query: str, pages: int = 1, delay: float = 1.0,
                     session: Optional[requests.Session] = None) -> List[EbayComp]:
    # Try the official Finding API first — works from datacenter IPs
    if os.environ.get("EBAY_APP_ID"):
        log.info("[ebay] EBAY_APP_ID set — trying Finding API for %r", query)
        try:
            comps = _ebay_finding_api(query, max_results=pages * 50)
            log.info("[ebay] Finding API returned %d comps for %r", len(comps), query)
            if comps:
                return comps
            log.warning("[ebay] Finding API returned 0 results for %r", query)
        except Exception as e:
            log.warning("[ebay] Finding API failed for %r: %s", query, e)
    else:
        log.info("[ebay] EBAY_APP_ID not set — skipping Finding API for %r", query)

    # HTML scrape fallback (blocked from Render/AWS IPs without a proxy)
    s = session or _make_session()
    all_comps: List[EbayComp] = []
    for p in range(1, pages + 1):
        url = build_sold_search_url(query, page=p)
        html = fetch_html(url, session=s)
        comps = parse_sold_results(html)
        all_comps.extend(comps)

        if p != pages:
            time.sleep(delay)

    seen = set()
    unique: List[EbayComp] = []
    for c in all_comps:
        if c.url in seen:
            continue
        seen.add(c.url)
        unique.append(c)

    return unique

def search_ebay_active(query: str, max_results: int = 30) -> List[dict]:
    """
    Search eBay for active (Buy It Now) listings using the Finding API.
    Returns dicts compatible with the deal-alert pipeline.
    Requires EBAY_APP_ID env var.
    """
    app_id = os.environ.get("EBAY_APP_ID", "")
    if not app_id:
        log.debug("[ebay] EBAY_APP_ID not set — skipping active scan")
        return []

    params = {
        "OPERATION-NAME": "findItemsByKeywords",
        "SERVICE-VERSION": "1.0.0",
        "SECURITY-APPNAME": app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "REST-PAYLOAD": "",
        "keywords": query,
        "itemFilter(0).name": "ListingType",
        "itemFilter(0).value(0)": "FixedPrice",
        "itemFilter(0).value(1)": "AuctionWithBIN",
        "itemFilter(1).name": "Currency",
        "itemFilter(1).value": "USD",
        "itemFilter(2).name": "Condition",
        "itemFilter(2).value(0)": "3000",
        "itemFilter(2).value(1)": "4000",
        "itemFilter(2).value(2)": "5000",
        "sortOrder": "PricePlusShippingLowest",
        "paginationInput.entriesPerPage": str(min(max_results, 100)),
    }
    try:
        r = requests.get(_FINDING_API_URL, params=params, timeout=15)
        if r.status_code != 200:
            log.warning("[ebay] findItemsByKeywords %d", r.status_code)
            return []
        data = r.json()
        items = (
            data
            .get("findItemsByKeywordsResponse", [{}])[0]
            .get("searchResult", [{}])[0]
            .get("item", [])
        )
    except Exception as e:
        log.warning("[ebay] findItemsByKeywords error: %s", e)
        return []

    results = []
    for item in items:
        try:
            title = item.get("title", [""])[0]
            url = item.get("viewItemURL", [""])[0]
            price_raw = float(
                item.get("sellingStatus", [{}])[0]
                    .get("convertedCurrentPrice", [{}])[0]
                    .get("__value__", 0)
            )
            ship_list = item.get("shippingInfo", [{}])[0].get("shippingServiceCost", [])
            shipping = float(ship_list[0].get("__value__", 0)) if ship_list else 0.0
            photo_list = item.get("galleryURL", [])
            photo = photo_list[0] if photo_list else None
            results.append({
                "title": title,
                "price": price_raw + shipping,
                "url": url,
                "photo": photo,
                "source": "ebay",
            })
        except Exception:
            continue

    log.info("[ebay] findItemsByKeywords query=%r → %d items", query, len(results))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape eBay SOLD listings for a query.")
    parser.add_argument("query", type=str, help='Search query, e.g. "Carhartt J01"')
    parser.add_argument("--pages", type=int, default=1, help="Number of pages to scrape (default: 1)")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between pages in seconds (default: 1.0)")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of comps printed (0 = no limit)")
    parser.add_argument("--fail-soft", action="store_true", help="On request errors, print [] instead of raising.")

    args = parser.parse_args()

    try:
        comps = scrape_ebay_sold(args.query, pages=args.pages, delay=args.delay)
    except RuntimeError as e:
        if args.fail_soft:
            print("[]")
            return
        raise

    if args.limit and args.limit > 0:
        comps = comps[: args.limit]

    print(json.dumps([asdict(c) for c in comps], indent = 2, ensure_ascii = False))

if __name__ == "__main__":
    main()

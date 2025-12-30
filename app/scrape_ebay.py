import argparse
import json
import re
import time
from dataclasses import asdict, dataclass
from typing import List, Optional, Tuple
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

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

def fetch_html(url: str, timeout: int = 8, max_retries: int = 2) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Connection": "keep-alive",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
    }

    session = requests.Session()

    last_status = None
    for attempt in range(1, max_retries + 1):
        try:
            r = session.get(url, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            if attempt != max_retries:
                time.sleep(min(2 ** attempt, 6))
                continue
            raise RuntimeError(f"eBay request error: {e}") from e

        last_status = r.status_code 

        if r.status_code == 200:
            return r.text

        if r.status_code in (429, 500, 502, 503, 504):
            sleep_s = min(2 ** attempt, 8)  # 2, 4, 8, 16, 20...
            time.sleep(sleep_s)
            continue

        break

    raise RuntimeError(f"eBay request failed: {last_status} for {url}")


def parse_sold_results(html: str) -> List[EbayComp]:
    soup = BeautifulSoup(html, "lmxl")
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

def scrape_ebay_sold(query: str, pages: int = 1, delay: float = 1.0) -> List[EbayComp]:
    all_comps: List[EbayComp] = []
    for p in range(1, pages + 1):
        url = build_sold_search_url(query, page=p)
        html = fetch_html(url)
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

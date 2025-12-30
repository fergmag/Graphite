from flask import Flask, jsonify, request, render_template
from typing import Any, Dict, List

from app.scrape_ebay import scrape_ebay_sold
from app.pricing import comps_to_prices, summarize_prices, to_dict
from app.cache import read_cache, write_cache
from app.db import init_db, insert_comps, insert_estimate
from app.public_view import build_public

def create_app() -> Flask:
    app = Flask(__name__)
    init_db()

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post("/seed")
    def seed():
        data = request.get_json(silent=True) or {}
        query = (data.get("query") or "").strip()
        comps = data.get("comps") or []

        if not query or not isinstance(comps, list):
            return jsonify(
                {
                    "error": "Bad request. Expected JSON with fields: query (string), comps (list).",
                    "example": {
                        "query": "Carhartt J01",
                        "comps": [{"title": "Carhartt J01 jacket", "price": 180.0}],
                    },
                }
            ), 400
        
        prices: List[float] = []
        clean_sample: List[Dict[str, Any]] = []

        for c in comps:
            if not isinstance(c, dict):
                continue
            p = c.get("price")
            if p is None:
                continue
            try:
                p = float(p)
            except (TypeError, ValueError):
                continue
            if p <= 0:
                continue

            clean_sample.append(
                {
                    "title": str(c.get("title") or ""),
                    "price": p,
                    "shipping": c.get("shipping"),
                    "url": c.get("url"),
                    "ended": c.get("ended"),
                }
            )
            prices.append(p)
        
        summary = summarize_prices(prices)
        payload = {
            "n": summary.n,
            "summary": to_dict(summary),
            "sample": clean_sample[:5],
        }

        public = build_public(payload["summary"], asking = None)

        write_cache(query, payload)

        inserted = insert_comps(query, clean_sample)
        insert_estimate(query, payload["summary"])

        return jsonify(
            {
                "ok": True,
                "query": query,
                "cached": True,
                "db_inserted_comps": inserted,
                "public": public,
                **payload,
            }
        ), 200

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.get("/estimate")
    def estimate():
        query = (request.args.get("query") or "").strip()
        pages = int(request.args.get("pages") or 1)
        include_shipping = (request.args.get("include_shipping") or "false").lower() in ("1", "true", "yes", "y")
        use_cache = (request.args.get("use_cache") or "true").lower() in ("1", "true", "yes", "y")
        cache_first = (request.args.get("cache_first") or "false").lower() in ("1", "true", "yes", "y")
        asking_raw = (request.args.get("asking") or "").strip()
        asking = None
        if asking_raw:
            try:
                asking = float(asking_raw)
            except ValueError:
                return jsonify({"error": "Invalid asking price. Use a number like 175 or 175.50"}), 400

        if not query:
            return jsonify(
                {
                    "error": "Missing required query parameter: ?query=Carhartt+J01",
                    "example": "/estimate?query=Carhartt+J01",
                }
            ), 400

        pages = max(1, min(pages, 3))

        if cache_first and use_cache:
            cached = read_cache(query)
            if cached:
                payload = cached["payload"]
                public = build_public(payload["summary"], asking = asking)

                return jsonify(
                    {
                        "query": query,
                        "platform": "ebay",
                        "ok": True,
                        "from_cache": True,
                        "cached_at": cached.get("cached_at"),
                        "include_shipping": include_shipping,
                        "public": public,
                        **cached["payload"],
                        "note": "Served cached result (cache_first=true).",
                    }
                ), 200

        try:
            comps = scrape_ebay_sold(query, pages=pages, delay=0.5)
        except RuntimeError as e:
            cached = read_cache(query) if use_cache else None
            if cached:
                payload = cached["payload"]
                public = build_public(payload["summary"], asking = asking)
                return jsonify(
                    {
                        "query": query,
                        "platform": "ebay",
                        "ok": True,
                        "from_cache": True,
                        "include_shipping": include_shipping,
                        "cached_at": cached.get("cached_at"),
                        "public": public,
                        **payload,
                        "note": "Live scrape failed; served last cached result.",
                        "reason": str(e),
                    }
                ), 200
            
            return jsonify(
                {
                    "query": query,
                    "platform": "ebay",
                    "ok": False,
                    "reason": str(e),
                    "n": 0,
                    "summary": None,
                    "sample": [],
                    "hint": "Try again later, or reduce pages. eBay sometimes rate-limits automated requests.",
                }
            ), 503

        prices = comps_to_prices([c.__dict__ for c in comps], include_shipping=include_shipping)
        summary = summarize_prices(prices)

        sample = [c.__dict__ for c in comps[:5]]

        payload = {
            "n": summary.n,
            "summary": to_dict(summary),
            "sample": sample,
        }
        write_cache(query, payload)

        public = build_public(payload["summary"], asking = asking)

        return jsonify(
            {
                "query": query,
                "platform": "ebay",
                "ok": True,
                "from_cache": False,
                "include_shipping": include_shipping,
                "public": public,
                **payload,
            }
        )


    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)

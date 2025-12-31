from typing import Any, Dict, List

from flask import Flask, jsonify, render_template, request

from app.cache import read_cache, write_cache
from app.pricing import comps_to_prices, summarize_prices, to_dict
from app.public_view import build_public_response
from app.scrape_ebay import scrape_ebay_sold


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.post("/seed")
    def seed():
        data = request.get_json(silent=True) or {}
        query = (data.get("query") or "").strip()
        comps = data.get("comps") or []

        if not query or not isinstance(comps, list):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "Bad request. Expected JSON: { query: string, comps: list }",
                        "example": {
                            "query": "Carhartt J01",
                            "comps": [{"title": "Carhartt J01 jacket", "price": 180.0}],
                        },
                    }
                ),
                400,
            )

        clean_sample: List[Dict[str, Any]] = []
        prices: List[float] = []

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

        summary_obj = summarize_prices(prices)
        summary = to_dict(summary_obj)
        public = build_public_response(summary)

        payload = {
            "n": summary_obj.n,
            "summary": summary,          # debug / internal (kept for now)
            "public": public,            # clean / user-facing
            "sample": clean_sample[:5],  # small sample only
        }

        write_cache(query, payload)

        return jsonify(
            {
                "ok": True,
                "query": query,
                "cached": True,
                **payload,
            }
        ), 200

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
                asking = None

        if not query:
            return jsonify(
                {
                    "ok": False,
                    "error": "Missing required query parameter: ?query=Carhartt+J01",
                    "example": "/estimate?query=Carhartt+J01",
                }
            ), 400

        pages = max(1, min(pages, 3))

        # Cache-first mode
        if cache_first and use_cache:
            cached = read_cache(query)
            if cached:
                payload = cached.get("payload") or {}
                summary = payload.get("summary") or {}
                public = build_public_response(summary, asking=asking)

                return jsonify(
                    {
                        "ok": True,
                        "platform": "ebay",
                        "query": query,
                        "from_cache": True,
                        "cached_at": cached.get("cached_at"),
                        "include_shipping": include_shipping,
                        **payload,
                        "public": public,  # rebuilt so deal score reflects asking
                        "note": "Served cached result (cache_first=true).",
                    }
                ), 200

        # Live scrape attempt
        try:
            comps = scrape_ebay_sold(query, pages=pages, delay=0.5)
        except RuntimeError as e:
            cached = read_cache(query) if use_cache else None
            if cached:
                payload = cached.get("payload") or {}
                summary = payload.get("summary") or {}
                public = build_public_response(summary, asking=asking)

                return jsonify(
                    {
                        "ok": True,
                        "platform": "ebay",
                        "query": query,
                        "from_cache": True,
                        "cached_at": cached.get("cached_at"),
                        "include_shipping": include_shipping,
                        **payload,
                        "public": public,
                        "note": "Live scrape failed; served last cached result.",
                        "reason": str(e),
                    }
                ), 200

            return jsonify(
                {
                    "ok": False,
                    "platform": "ebay",
                    "query": query,
                    "reason": str(e),
                    "n": 0,
                    "summary": None,
                    "public": {
                        "casp": None,
                        "casp_label": "Calculated average sold price",
                        "accuracy_pct": 0,
                        "accuracy_label": "Very Low",
                    },
                    "sample": [],
                    "hint": "Try again later, or reduce pages. eBay sometimes rate-limits automated requests.",
                }
            ), 503

        # Compute pricing
        sample = [c.__dict__ for c in comps[:5]]
        prices = comps_to_prices([c.__dict__ for c in comps], include_shipping=include_shipping)

        summary_obj = summarize_prices(prices)
        summary = to_dict(summary_obj)
        public = build_public_response(summary, asking=asking)

        payload = {
            "n": summary_obj.n,
            "summary": summary,
            "public": public,
            "sample": sample,
        }

        write_cache(query, payload)

        return jsonify(
            {
                "ok": True,
                "platform": "ebay",
                "query": query,
                "from_cache": False,
                "include_shipping": include_shipping,
                **payload,
            }
        ), 200

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)

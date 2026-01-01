from flask import Flask, jsonify, request, render_template
from typing import Any, Dict, List, Optional

from app.scrape_ebay import scrape_ebay_sold
from app.pricing import comps_to_prices, summarize_prices, to_dict
from app.cache import read_cache, write_cache
from app.public_view import build_public_payload
from app.db import (
    init_db,
    insert_comps,
    insert_estimate,
    add_watch,
    list_watches,
    delete_watch,
)

# Optional: Step 13 manual model overrides (keep compatibility)
try:
    from app.model_profiles import get_manual_casp_for_query  # type: ignore
except Exception:
    get_manual_casp_for_query = None  # type: ignore


def _parse_bool(x: str, default: bool = False) -> bool:
    if x is None:
        return default
    return str(x).strip().lower() in ("1", "true", "yes", "y", "on")


def _parse_float(x: Optional[str]) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def create_app() -> Flask:
    app = Flask(__name__)
    init_db()

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/")
    def home():
        return render_template("index.html")

    # -----------------------
    # Watchlist API
    # -----------------------
    @app.get("/watchlist")
    def watchlist_get():
        return jsonify({"ok": True, "items": list_watches()}), 200

    @app.post("/watchlist")
    def watchlist_add():
        data = request.get_json(silent=True) or {}
        q = (data.get("query") or "").strip()
        if not q:
            return jsonify({"ok": False, "error": "Missing query"}), 400
        add_watch(q)
        return jsonify({"ok": True, "items": list_watches()}), 200

    @app.delete("/watchlist")
    def watchlist_delete():
        q = (request.args.get("query") or "").strip()
        if q:
            delete_watch(q)
        return jsonify({"ok": True, "items": list_watches()}), 200

    # -----------------------
    # Seed demo comps to cache + DB
    # -----------------------
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

        summary = summarize_prices(prices)
        summary_dict = to_dict(summary)

        # CASP: use manual override if available, otherwise median
        casp = summary_dict.get("median")
        if get_manual_casp_for_query:
            try:
                override = get_manual_casp_for_query(query)
                if override is not None:
                    casp = override
            except Exception:
                pass

        public = build_public_payload(casp=casp, confidence=float(summary_dict.get("confidence") or 0.0))

        payload = {
            "n": summary.n,
            "public": public,
            "summary": summary_dict,
            "sample": clean_sample[:5],
        }

        write_cache(query, payload)

        # DB writes
        insert_comps(query, clean_sample)
        insert_estimate(query, public_payload=public, summary_payload=summary_dict)

        return jsonify({"ok": True, "query": query, "cached": True, **payload}), 200

    # -----------------------
    # Estimate endpoint
    # -----------------------
    @app.get("/estimate")
    def estimate():
        query = (request.args.get("query") or "").strip()
        pages = int(request.args.get("pages") or 1)
        include_shipping = _parse_bool(request.args.get("include_shipping") or "false", False)
        use_cache = _parse_bool(request.args.get("use_cache") or "true", True)
        cache_first = _parse_bool(request.args.get("cache_first") or "false", False)
        asking = _parse_float(request.args.get("asking"))

        if not query:
            return jsonify({"ok": False, "error": "Missing required ?query=..."}), 400

        pages = max(1, min(pages, 3))

        if cache_first and use_cache:
            cached = read_cache(query)
            if cached and cached.get("payload"):
                payload = cached["payload"]
                # If asking is provided, recompute deal score using cached CASP
                pub = payload.get("public") or {}
                casp = pub.get("casp")
                if casp is not None and asking is not None:
                    pub = build_public_payload(
                        casp=float(casp),
                        confidence=float(pub.get("confidence_raw") or payload.get("summary", {}).get("confidence") or 0.0),
                        asking=asking,
                    )
                    payload["public"] = pub

                return jsonify(
                    {
                        "ok": True,
                        "platform": "ebay",
                        "query": query,
                        "from_cache": True,
                        "cached_at": cached.get("cached_at"),
                        "include_shipping": include_shipping,
                        "note": "Served cached result (cache_first=true).",
                        **payload,
                    }
                ), 200

        # live scrape
        try:
            comps = scrape_ebay_sold(query, pages=pages, delay=0.5)
        except RuntimeError as e:
            cached = read_cache(query) if use_cache else None
            if cached and cached.get("payload"):
                payload = cached["payload"]
                return jsonify(
                    {
                        "ok": True,
                        "platform": "ebay",
                        "query": query,
                        "from_cache": True,
                        "cached_at": cached.get("cached_at"),
                        "include_shipping": include_shipping,
                        "note": "Live scrape failed; served last cached result.",
                        "reason": str(e),
                        **payload,
                    }
                ), 200

            return jsonify(
                {
                    "ok": False,
                    "platform": "ebay",
                    "query": query,
                    "n": 0,
                    "public": None,
                    "summary": None,
                    "sample": [],
                    "reason": str(e),
                    "hint": "Try again later, or reduce pages. eBay sometimes rate-limits automated requests.",
                }
            ), 503

        # compute
        comps_dicts = [c.__dict__ for c in comps]
        prices = comps_to_prices(comps_dicts, include_shipping=include_shipping)
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
            asking=asking,
        )

        payload = {
            "n": summary.n,
            "public": public,
            "summary": summary_dict,
            "sample": comps_dicts[:5],
        }

        write_cache(query, payload)
        insert_estimate(query, public_payload=public, summary_payload=summary_dict)

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

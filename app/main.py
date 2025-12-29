from flask import Flask, jsonify, request

from app.scrape_ebay import scrape_ebay_sold
from app.pricing import comps_to_prices, summarize_prices, to_dict


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/estimate")
    def estimate():
        query = (request.args.get("query") or "").strip()
        pages = int(request.args.get("pages") or 1)
        include_shipping = (request.args.get("include_shipping") or "false").lower() in ("1", "true", "yes", "y")

        if not query:
            return jsonify(
                {
                    "error": "Missing required query parameter: ?query=Carhartt+J01",
                    "example": "/estimate?query=Carhartt+J01",
                }
            ), 400

        pages = max(1, min(pages, 3))

        try:
            comps = scrape_ebay_sold(query, pages=pages, delay=1.0)
        except RuntimeError as e:
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

        return jsonify(
            {
                "query": query,
                "platform": "ebay",
                "ok": True,
                "include_shipping": include_shipping,
                "n": summary.n,
                "summary": to_dict(summary),
                "sample": sample,
            }
        )

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)

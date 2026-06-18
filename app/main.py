from flask import Flask, jsonify, request, render_template, session, redirect, url_for, send_from_directory
from functools import wraps
from typing import Any, Dict, List, Optional, Sequence
import json
import logging
import os
import re
import threading

import base64
import uuid
import requests as _req
import stripe
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
load_dotenv()

from app.scrape_ebay import scrape_ebay_sold
from app.pricing import comps_to_prices, summarize_prices, to_dict
from app.cache import read_cache, write_cache
from app.public_view import build_public_payload
from app.filters import filter_comps, normalize_query
from app.db import (
    init_db,
    insert_comps,
    insert_estimate,
    add_watch,
    list_watches,
    delete_watch,
    list_comps,
    count_comps,
    count_comps_for_queries,
    get_casp_history,
    db_list_listings,
    db_insert_listing,
    db_update_listing,
    db_toggle_sold,
    db_delete_listing,
    db_set_listing_photos,
    db_load_archive,
    db_add_section,
    db_update_section,
    db_delete_section,
)

# Optional: Step 13 manual model overrides (keep compatibility)
try:
    from app.model_profiles import get_manual_casp_for_query  # type: ignore
except Exception:
    get_manual_casp_for_query = None  # type: ignore


_APP_DATA_DIR = os.path.dirname(os.path.abspath(__file__))


def _github_sync_file(rel_path: str, content: str, message: str) -> None:
    """Push a file to the GitHub repo via API. No-op if env vars not set."""
    token = os.environ.get("GITHUB_TOKEN", "")
    repo  = os.environ.get("GITHUB_REPO", "")   # e.g. "fergmag/Graphite"
    if not token or not repo:
        return
    try:
        url = f"https://api.github.com/repos/{repo}/contents/{rel_path}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        r = _req.get(url, headers=headers, timeout=8, params={"ref": "main"})
        sha = r.json().get("sha") if r.status_code == 200 else None
        body: Dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": "main",
        }
        if sha:
            body["sha"] = sha
        _req.put(url, headers=headers, json=body, timeout=12)
    except Exception as e:
        logging.getLogger(__name__).warning("[github-sync] %s: %s", rel_path, e)


def _persist_listings() -> None:
    """Write listings to JSON and sync to GitHub so data survives redeploys."""
    data = db_list_listings()
    content = json.dumps(data, indent=2, ensure_ascii=False)
    path = os.path.join(_APP_DATA_DIR, "listings.json")
    try:
        with open(path, "w") as f:
            f.write(content)
    except Exception:
        pass
    _github_sync_file("app/listings.json", content, "sync: listings updated")


def _persist_archive() -> None:
    """Write archive sections to JSON and sync to GitHub so data survives redeploys."""
    data = db_load_archive()
    content = json.dumps(data, indent=2, ensure_ascii=False)
    path = os.path.join(_APP_DATA_DIR, "archive.json")
    try:
        with open(path, "w") as f:
            f.write(content)
    except Exception:
        pass
    _github_sync_file("app/archive.json", content, "sync: archive updated")


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


def _listing_id_from_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    match = re.search(r"/itm/(?:[^/]+/)?(\d+)", url)
    if match:
        return match.group(1)
    match = re.search(r"itm/(\d+)", url)
    if match:
        return match.group(1)
    return None


def _normalize_comps(comps: Sequence[Dict[str, Any]], source: str) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    seen_keys = set()

    for comp in comps:
        if not isinstance(comp, dict):
            continue
        url = comp.get("url")
        listing_id = comp.get("listing_id") or _listing_id_from_url(url)
        dedupe_key = listing_id or url
        if dedupe_key and dedupe_key in seen_keys:
            continue
        if dedupe_key:
            seen_keys.add(dedupe_key)

        ended_at = comp.get("ended_at") or comp.get("ended")
        currency = comp.get("currency") or comp.get("shipping_currency")

        normalized.append(
            {
                "title": comp.get("title"),
                "price": comp.get("price"),
                "shipping": comp.get("shipping"),
                "currency": currency,
                "url": url,
                "ended": comp.get("ended"),
                "ended_at": ended_at,
                "source": source,
                "model_guess": comp.get("model_guess"),
                "listing_id": listing_id,
            }
        )

    return normalized


def _login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    init_db()

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/login")
    def login():
        return render_template("login.html", error=False)

    @app.post("/login")
    def login_post():
        password = request.form.get("password", "")
        expected = os.environ.get("TOOL_PASSWORD", "graphite")
        if password == expected:
            session["logged_in"] = True
            return redirect(url_for("admin"))
        return render_template("login.html", error=True)

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/tool")
    @_login_required
    def home():
        return redirect("/admin#estimator")


    _DEFAULT_PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "static", "images", "listings")
    _PHOTOS_DIR = os.environ.get("GRAPHITE_PHOTOS_DIR", _DEFAULT_PHOTOS_DIR)

    def _cloudinary_configured() -> bool:
        return bool(
            os.environ.get("CLOUDINARY_CLOUD_NAME") and
            os.environ.get("CLOUDINARY_API_KEY") and
            os.environ.get("CLOUDINARY_API_SECRET")
        )

    def _save_photo(file) -> Optional[str]:
        log = logging.getLogger(__name__)
        if _cloudinary_configured():
            try:
                import cloudinary
                import cloudinary.uploader
                cloudinary.config(
                    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
                    api_key=os.environ.get("CLOUDINARY_API_KEY"),
                    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
                )
                result = cloudinary.uploader.upload(file, folder="graphite")
                url = result.get("secure_url")
                if not url:
                    log.error("[cloudinary] Upload returned no URL: %s", result)
                    return None
                return url
            except Exception as e:
                log.error("[cloudinary] Upload failed: %s", e)
                return None
        # Fallback: save locally
        try:
            ext = (file.filename.rsplit(".", 1)[-1] if "." in file.filename else "jpg").lower()
            filename = f"{uuid.uuid4().hex}.{ext}"
            os.makedirs(_PHOTOS_DIR, exist_ok=True)
            file.save(os.path.join(_PHOTOS_DIR, filename))
            return filename
        except Exception as e:
            log.error("[local-photo] Save failed: %s", e)
            return None

    @app.template_filter("photo_url")
    def photo_url_filter(photo: str) -> str:
        """Return the correct URL for a photo — Cloudinary URL or local /photos/ path."""
        if photo and (photo.startswith("http://") or photo.startswith("https://")):
            return photo
        return f"/photos/{photo}"

    @app.get("/photos/<path:filename>")
    def serve_photo(filename):
        return send_from_directory(_PHOTOS_DIR, filename)

    @app.get("/")
    @app.get("/shop")
    def shop():
        all_listings = db_list_listings()
        return render_template("shop.html",
            listings=[l for l in all_listings if not l.get("sold")],
            page="shop",
            paypal_client_id=os.environ.get("PAYPAL_CLIENT_ID", ""))

    @app.get("/sold")
    def sold():
        all_listings = db_list_listings()
        return render_template("shop.html",
            listings=[l for l in all_listings if l.get("sold")],
            page="sold",
            paypal_client_id=os.environ.get("PAYPAL_CLIENT_ID", ""))

    @app.get("/archive")
    def archive():
        return render_template("archive.html", page="archive", archive=db_load_archive())

    @app.get("/about")
    def about():
        return render_template("about.html", page="about")

    # -----------------------
    # Admin
    # -----------------------
    @app.get("/admin")
    @_login_required
    def admin():
        return render_template("admin.html", listings=db_list_listings(), archive=db_load_archive())

    @app.post("/admin/add")
    @_login_required
    def admin_add():
        from datetime import datetime, timezone
        title       = request.form.get("title", "").strip()
        size        = request.form.get("size", "").strip()
        price       = request.form.get("price", "").strip()
        description = request.form.get("description", "").strip()
        if not title or not price:
            return redirect("/admin#listings")
        photos = []
        for f in request.files.getlist("photos"):
            if f and f.filename:
                _p = _save_photo(f); photos.append(_p) if _p else None
        db_insert_listing({
            "id": uuid.uuid4().hex[:10],
            "title": title,
            "size": size,
            "price": float(price),
            "description": description,
            "photos": photos,
            "sold": False,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        })
        _persist_listings()
        return redirect("/admin#listings")

    @app.post("/admin/toggle-sold/<listing_id>")
    @_login_required
    def admin_toggle_sold(listing_id):
        db_toggle_sold(listing_id)
        _persist_listings()
        return redirect("/admin#listings")

    @app.post("/admin/delete/<listing_id>")
    @_login_required
    def admin_delete(listing_id):
        db_delete_listing(listing_id)
        _persist_listings()
        return redirect("/admin#listings")

    @app.post("/admin/edit/<listing_id>")
    @_login_required
    def admin_edit(listing_id):
        title = request.form.get("title", "").strip()
        size  = request.form.get("size", "").strip()
        price = request.form.get("price", "").strip()
        desc  = request.form.get("description", "").strip()
        new_photos = []
        for f in request.files.getlist("photos"):
            if f and f.filename:
                _p = _save_photo(f); new_photos.append(_p) if _p else None
        fields: Dict[str, Any] = {"title": title, "size": size, "description": desc}
        if price:
            try: fields["price"] = float(price)
            except ValueError: pass
        if new_photos:
            fields["photos"] = new_photos
        db_update_listing(listing_id, fields)
        _persist_listings()
        return redirect("/admin#listings")

    @app.post("/admin/remove-photo/<listing_id>/<int:idx>")
    @_login_required
    def admin_remove_photo(listing_id, idx):
        listing = next((l for l in db_list_listings() if l["id"] == listing_id), None)
        if listing:
            photos = listing.get("photos") or []
            if 0 <= idx < len(photos):
                photos.pop(idx)
            db_set_listing_photos(listing_id, photos)
            _persist_listings()
        return redirect("/admin#listings")

    @app.get("/api/history")
    @_login_required
    def api_history():
        from app.filters import normalize_query as _nq
        query = _nq(request.args.get("query") or "")
        if not query:
            return jsonify({"ok": False, "error": "Missing query"}), 400
        return jsonify({"ok": True, "query": query, "history": get_casp_history(query)})

    @app.get("/api/comps")
    @_login_required
    def api_comps():
        limit = int(request.args.get("limit", 100))
        return jsonify({"ok": True, "comps": list_comps(limit), "total": count_comps()})

    @app.post("/api/comps/counts")
    @_login_required
    def api_comps_counts():
        """Given a list of raw watchlist queries, returns {query: comp_count} using normalized keys."""
        queries = (request.get_json(silent=True) or {}).get("queries", [])
        normalized = {q: normalize_query(q) for q in queries if isinstance(q, str) and q.strip()}
        nq_list = list(set(normalized.values()))
        counts_by_nq = count_comps_for_queries(nq_list)
        result = {orig: counts_by_nq.get(nq, 0) for orig, nq in normalized.items()}
        return jsonify({"ok": True, "counts": result})

    @app.get("/admin/refresh-status")
    @_login_required
    def admin_refresh_status():
        from app.scraper import get_refresh_status
        return jsonify({"ok": True, **get_refresh_status()})

    @app.post("/admin/refresh-now")
    @_login_required
    def admin_refresh_now():
        from app.scraper import refresh_all_watchlist
        t = threading.Thread(target=refresh_all_watchlist, daemon=True)
        t.start()
        return jsonify({"ok": True, "message": "Refresh started in background"})

    @app.post("/admin/populate-watchlist")
    @_login_required
    def admin_populate_watchlist():
        profiles_path = os.path.join(os.path.dirname(__file__), "models.json")
        try:
            with open(profiles_path) as f:
                models = json.load(f)
            for key in models.keys():
                add_watch(key)
        except Exception:
            pass
        return redirect("/admin#estimator")

    # -----------------------
    # Archive admin
    # -----------------------
    @app.get("/admin/archive")
    @_login_required
    def admin_archive():
        return render_template("admin.html", listings=db_list_listings(), archive=db_load_archive())

    @app.post("/admin/archive/add-section")
    @_login_required
    def archive_add_section():
        title = request.form.get("title", "").strip()
        if not title:
            return redirect("/admin#archive")
        text = request.form.get("text", "").strip()
        photos = []
        for f in request.files.getlist("photos"):
            if f and f.filename:
                _p = _save_photo(f); photos.append(_p) if _p else None
        db_add_section(uuid.uuid4().hex[:10], title, text=text, photos=photos)
        _persist_archive()
        return redirect("/admin#archive")

    @app.post("/admin/archive/edit-section/<sid>")
    @_login_required
    def archive_edit_section(sid):
        title = request.form.get("title", "").strip()
        text  = request.form.get("text", "").strip()
        photos = []
        for f in request.files.getlist("photos"):
            if f and f.filename:
                _p = _save_photo(f); photos.append(_p) if _p else None
        db_update_section(sid, {"title": title, "text": text, "photos": photos or None})
        _persist_archive()
        return redirect("/admin#archive")

    @app.post("/admin/archive/delete-section/<sid>")
    @_login_required
    def archive_delete_section(sid):
        db_delete_section(sid)
        _persist_archive()
        return redirect("/admin#archive")

    # -----------------------
    # Stripe Checkout
    # -----------------------
    @app.post("/checkout")
    def checkout():
        stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
        data = request.get_json(silent=True) or {}
        listing_id = data.get("id")

        all_listings = db_list_listings()
        listing = next((l for l in all_listings if str(l.get("id")) == str(listing_id)), None)

        if not listing or listing.get("sold"):
            return jsonify({"ok": False, "error": "Listing not available"}), 400

        price_cents = int(round(float(listing["price"]) * 100))
        base_url = request.host_url.rstrip("/")

        session_obj = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": listing["title"],
                        "description": f"Size: {listing.get('size', '')}",
                    },
                    "unit_amount": price_cents,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{base_url}/shop?success=1",
            cancel_url=f"{base_url}/shop?cancelled=1",
        )

        return jsonify({"ok": True, "url": session_obj.url}), 200

    # -----------------------
    # PayPal Checkout
    # -----------------------
    def _paypal_base():
        return "https://api-m.paypal.com" if os.environ.get("PAYPAL_MODE") == "live" \
            else "https://api-m.sandbox.paypal.com"

    def _paypal_token():
        r = _req.post(
            f"{_paypal_base()}/v1/oauth2/token",
            auth=(os.environ.get("PAYPAL_CLIENT_ID", ""), os.environ.get("PAYPAL_CLIENT_SECRET", "")),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["access_token"]

    @app.post("/paypal/create-order")
    def paypal_create_order():
        data = request.get_json(silent=True) or {}
        listing_id = data.get("id")
        all_listings = db_list_listings()
        listing = next((l for l in all_listings if str(l.get("id")) == str(listing_id)), None)
        if not listing or listing.get("sold"):
            return jsonify({"ok": False, "error": "Listing not available"}), 400
        price = f"{float(listing['price']):.2f}"
        token = _paypal_token()
        r = _req.post(
            f"{_paypal_base()}/v2/checkout/orders",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "intent": "CAPTURE",
                "purchase_units": [{"amount": {"currency_code": "USD", "value": price},
                                    "description": listing["title"]}],
            },
            timeout=10,
        )
        r.raise_for_status()
        return jsonify({"ok": True, "orderID": r.json()["id"]}), 200

    @app.post("/paypal/capture-order")
    def paypal_capture_order():
        data = request.get_json(silent=True) or {}
        order_id = data.get("orderID")
        if not order_id:
            return jsonify({"ok": False, "error": "Missing orderID"}), 400
        token = _paypal_token()
        r = _req.post(
            f"{_paypal_base()}/v2/checkout/orders/{order_id}/capture",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=10,
        )
        r.raise_for_status()
        return jsonify({"ok": True}), 200

    # -----------------------
    # Watchlist API
    # -----------------------
    @app.get("/watchlist")
    def watchlist_get():
        return jsonify({"ok": True, "items": list_watches()}), 200

    @app.post("/watchlist")
    def watchlist_add():
        data = request.get_json(silent=True) or {}
        raw_query = data.get("query")
        if raw_query is None:
            raw_query = ""
        if not isinstance(raw_query, str):
            raw_query = str(raw_query)
        if not raw_query.strip():
            return jsonify({"ok": False, "error": "Missing query"}), 400
        add_watch(raw_query)
        return jsonify({"ok": True, "items": list_watches()}), 200

    @app.delete("/watchlist")
    def watchlist_delete():
        raw_query = request.args.get("query")
        if raw_query is None:
            raw_query = ""
        if not isinstance(raw_query, str):
            raw_query = str(raw_query)
        if raw_query.strip():
            delete_watch(raw_query)
        return jsonify({"ok": True, "items": list_watches()}), 200

    # -----------------------
    # Seed demo comps to cache + DB
    # -----------------------
    @app.post("/seed")
    def seed():
        data = request.get_json(silent=True) or {}
        query = normalize_query(data.get("query") or "")
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

        normalized_comps = _normalize_comps(clean_sample, source="manual")

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
            "sample": normalized_comps[:5],
        }

        write_cache(query, payload)

        # DB writes
        insert_comps(query, normalized_comps)
        insert_estimate(query, public_payload=public, summary_payload=summary_dict)

        return jsonify({"ok": True, "query": query, "cached": True, **payload}), 200

    # -----------------------
    # Estimate endpoint
    # -----------------------
    @app.get("/estimate")
    def estimate():
        query = normalize_query(request.args.get("query") or "")
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

            # No cache — try model profile as last resort
            if get_manual_casp_for_query:
                try:
                    profile_casp = get_manual_casp_for_query(query)
                    if profile_casp is not None:
                        public = build_public_payload(casp=profile_casp, confidence=0.0, asking=asking)
                        return jsonify(
                            {
                                "ok": True,
                                "platform": "ebay",
                                "query": query,
                                "from_cache": False,
                                "n": 0,
                                "public": public,
                                "summary": None,
                                "sample": [],
                                "note": "Scrape failed; estimate from model profile only.",
                                "reason": str(e),
                            }
                        ), 200
                except Exception:
                    pass

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
        normalized_comps = _normalize_comps(comps_dicts, source="ebay")
        normalized_comps = filter_comps(normalized_comps, query)
        prices = comps_to_prices(normalized_comps, include_shipping=include_shipping)
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
            "sample": normalized_comps[:5],
        }

        write_cache(query, payload)
        insert_comps(query, normalized_comps)
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

    # ── Background scheduler ──
    # Guard: in Flask debug mode the reloader forks a child process; only start
    # the scheduler in the child (WERKZEUG_RUN_MAIN=true) or in production.
    _in_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    _should_schedule = not app.debug or _in_reloader_child
    if _should_schedule:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from app.scraper import refresh_all_watchlist as _refresh
            _sched = BackgroundScheduler(daemon=True)
            _sched.add_job(_refresh, "interval", hours=6, id="watchlist_refresh",
                           misfire_grace_time=300)
            _sched.start()
            logging.getLogger(__name__).info("[scheduler] Started — refresh every 6 h")
        except Exception as _e:
            logging.getLogger(__name__).warning("[scheduler] Could not start: %s", _e)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
 
# Graphite — What's Been Built

A running log of everything implemented, so new sessions can orient quickly. ROADMAP.md has the original vision; this file has the ground truth.

---

## Infrastructure

- **Hosting**: Render.com free tier — live at graphitevintage.com (Namecheap DNS wired to Render)
- **Uptime monitoring**: UptimeRobot pinging the site
- **Photo storage**: Cloudinary (uploaded via admin → stored as full URLs in DB/JSON)
- **Data persistence across Render redeploys**: listings, archive, and alerts are synced to GitHub via API after every write (`_persist_listings`, `_persist_archive`, `_persist_alerts` in main.py). On startup `init_db` reloads from these JSON files.
- **GitHub**: https://github.com/fergmag/Graphite
- **Background color**: `#283238` — locked in, do not change

---

## Site pages

| Route | Description |
|---|---|
| `/` or `/shop` | Public shop — available listings |
| `/sold` | Sold items |
| `/archive` | Archive/lookbook page (owner-curated sections with photos) |
| `/about` | About page (stub) |
| `/admin` | Owner-only admin panel (login-gated) |
| `/login` | Login page (password = env TOOL_PASSWORD, default "graphite") |
| `/tool` | Redirects to `/admin#estimator` |

---

## Admin panel tabs

### Listings tab
- Add/edit/delete listings with Cloudinary photo upload
- Toggle sold/available
- Size options: M, L, XL, XXL

### Estimator tab
- Search any jacket model (e.g. "J97 CRI", "JB0817")
- Enter optional asking price + size → deal score adjusted for size
- Shows: Estimated Value (CASP), Accuracy %, Deal Score (1–5)
- CASP history chart with y-axis price labels
- Live listings section: scans Depop, Grailed, Etsy for active deals
  - Claude Vision grades condition of all listings with photos (Haiku model)
- Watchlist: saved queries, auto-refreshes every 6h via APScheduler
- Bell icon shows unseen deal alert count
- "Refresh All Now" triggers immediate background refresh

### Archive tab
- Add/edit/delete archive sections with titles, text, and photos

---

## Payments

- **Stripe**: full Checkout integration — card + Apple Pay + Google Pay
  - `POST /checkout` creates a session; success redirects to `/shop?success=1`
  - Line items: item price + $50 shipping + 4% processing fee
- **PayPal**: full server-side order creation + capture
  - `POST /paypal/create-order` and `POST /paypal/capture-order`
  - Sandbox vs live controlled by `PAYPAL_MODE=live` env var

---

## Scraping & pricing

### eBay (sold comps → CASP)
- `scrape_ebay.py` — scrapes eBay sold listings with cookie warming + retry logic
- 403 handling: backs off 45s per attempt
- `scraper.py:scrape_and_save` — wraps eBay scrape, normalizes, filters, computes CASP, writes cache + DB
- `pricing.py` — median + trimmed mean + confidence score
- `filters.py` — drops junk (kids/women's/vest), requires jacket code in title if query has one
- `model_profiles.py` + `models.json` — 27 manual CASP overrides for specific models (M price basis)

### Multi-platform deal scanning (active listings)
- `scrape_depop.py` — Depop internal API
- `scrape_grailed.py` — Grailed via Algolia (public search key — rotates occasionally, update if broken)
- `scrape_etsy.py` — Etsy API v3 (requires `ETSY_API_KEY` env var)
- `scraper.py:scan_platforms_for_query` — fetches all three, filters, scores vs CASP, saves alerts with deal_score ≥ 3

### Size-adjusted deal scoring
- CASP in models.json is the **M (medium) price**
- Size multipliers applied before deal score calculation:
  - M = ×1.0 (base)
  - L = ×0.80
  - XL = ×0.50
  - XXL = ×0.20
- Only applied when CASP comes from a manual profile (not raw eBay data)

### Background scheduler
- APScheduler runs `refresh_all_watchlist` every 6 hours
- 55s delay between queries to avoid eBay rate-limits
- Clears alerts older than 14 days on each run
- Status visible in admin via `/admin/refresh-status`

---

## Vision / AI

- `vision.py` — Claude Haiku (`claude-haiku-4-5-20251001`) grades jacket condition from photo URLs
- Returns `{grade: "7/10", notes: "..."}` or None if API key missing / request fails
- Called for all listings with photos in the `/api/model-detail` endpoint
- Requires `ANTHROPIC_API_KEY` env var

---

## Database (SQLite — graphite.db)

Key tables:
- `comps` — scraped eBay sold listings
- `estimates` — CASP history per query (used for chart)
- `watchlist` — saved search queries
- `listings` — shop inventory
- `archive_sections` — archive page entries
- `alerts` — deal alerts from platform scans

---

## Environment variables needed on Render

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask session secret |
| `TOOL_PASSWORD` | Admin login password |
| `CLOUDINARY_CLOUD_NAME` | Photo storage |
| `CLOUDINARY_API_KEY` | Photo storage |
| `CLOUDINARY_API_SECRET` | Photo storage |
| `STRIPE_SECRET_KEY` | Stripe payments |
| `STRIPE_PUBLISHABLE_KEY` | Stripe frontend |
| `PAYPAL_CLIENT_ID` | PayPal |
| `PAYPAL_CLIENT_SECRET` | PayPal |
| `PAYPAL_MODE` | `live` or `sandbox` |
| `ETSY_API_KEY` | Etsy scraping |
| `ANTHROPIC_API_KEY` | Claude Vision grading |
| `GITHUB_TOKEN` | Data persistence sync |
| `GITHUB_REPO` | `fergmag/Graphite` |

---

## Known issues / deferred

- Render env vars (TOOL_PASSWORD, SECRET_KEY) may not be picked up by gunicorn — "graphite" still works as password fallback. Defer until auth system built.
- Grailed Algolia key rotates — if Grailed returns 0 results, fetch https://www.grailed.com and extract new `window.PUBLIC_CONFIG.algolia.public_search_key`
- eBay occasionally returns 403 (bot detection) — scraper backs off and falls back to cache
- Depop API endpoint may change — monitor for 4xx responses
- Not enough CASP history yet to fully test the price chart

---

## What to build next (from memory)

- Fix any live scraping issues (eBay 403, Depop/Grailed broken keys)
- Auth system: public landing page + owner-approved accounts to access estimator
- Watchlist items: expandable to show current comps
- AI image scraper: take a photo → find similar listings (Google Vision web detection)

# Graphite — What's Been Built

A running log of everything implemented, so new sessions can orient quickly. ROADMAP.md has the original vision; this file has the ground truth.

---

## Infrastructure

- **Hosting**: Render.com free tier — live at graphitevintage.com (Namecheap DNS wired to Render)
- **Uptime monitoring**: UptimeRobot pinging the site
- **Photo storage**: Cloudinary (uploaded via admin → stored as full URLs in DB/JSON)
- **Data persistence across Render redeploys**: listings, archive, alerts, and CASP estimates are synced to GitHub via API after every write (`_persist_listings`, `_persist_archive`, `_persist_alerts`, `_persist_estimates` in main.py). On startup `init_db` reloads from these JSON files.
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
- `scrape_ebay.py` — primary method: eBay Finding API (`findCompletedItems`); falls back to HTML scraping
- **Requires `EBAY_APP_ID` env var** (free — register at developer.ebay.com → create app → copy "App ID")
- Without `EBAY_APP_ID`, HTML scraping is used but is blocked from Render's AWS IPs
- `scraper.py:scrape_and_save` — wraps eBay scrape, normalizes, filters, computes CASP, writes cache + DB
- `pricing.py` — median + trimmed mean + confidence score
- `filters.py` — drops junk (kids/women's/vest), requires jacket code in title if query has one
- `model_profiles.py` + `models.json` — 27 manual CASP overrides for specific models (M price basis)

### Multi-platform deal scanning (active listings)
- `scrape_ebay.py:search_ebay_active` — eBay active BIN listings via Finding API (`findItemsByKeywords`). Also needs `EBAY_APP_ID`
- `scrape_depop.py` — Depop internal API (currently returning [] — requires OAuth, all v1/v2/v3 endpoints are 403)
- `scrape_grailed.py` — Grailed via Algolia (public search key — rotates occasionally, update if broken)
- `scrape_etsy.py` — Etsy API v3 (requires `ETSY_API_KEY` env var — user's key not activated yet)
- `scrape_whatnot.py` — stub, returns [] (Whatnot uses Cloudflare — blocked without Playwright + CF bypass)
- `scraper.py:scan_platforms_for_query` — fetches from all platforms, filters, scores vs CASP, saves alerts with deal_score ≥ 3
- Vision grades ALL listings with photos (no cap — removed the old top-3 limit)

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
- Called for ALL listings with photos in `/api/model-detail` and ALL deal alerts with score ≥ 3
- Prompt uses strict anchors (10=deadstock, 5=well-worn, 4=heavy wear) to combat Haiku defaulting to 6-7
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
| `ETSY_API_KEY` | Etsy scraping (key not activated yet) |
| `ANTHROPIC_API_KEY` | Claude Vision grading |
| `EBAY_APP_ID` | eBay Finding API — **needed for eBay to work from Render** |
| `GITHUB_TOKEN` | Data persistence sync |
| `GITHUB_REPO` | `fergmag/Graphite` |

---

## Known issues / deferred

- **eBay Finding API 503** — Getting HTML 503 error pages from `svcs.ebay.com`. Added retry logic (3 attempts with backoff) and HTML-response detection (means App ID is wrong or blocked). If you see "Got HTML from Finding API" in logs, verify that `EBAY_APP_ID` on Render is the **Production** App ID (not Sandbox) from developer.ebay.com. The Sandbox App ID will not work on the production Finding API endpoint.
- **Etsy 403 "Shared secret required"** — Etsy API v3 requires `{keystring}:{shared_secret}` combined in the `x-api-key` header. Code now supports both `ETSY_API_KEY` (keystring) and `ETSY_SHARED_SECRET`. Both must be set on Render — find the shared secret in your Etsy developer console next to the keystring.
- Grailed Algolia key rotates — if Grailed returns 0 results, fetch https://www.grailed.com and extract new `window.PUBLIC_CONFIG.algolia.public_search_key`
- Depop fully blocked — all API endpoints return 403, requires OAuth. Returning [] for now.
- Whatnot blocked by Cloudflare — needs Playwright + CF bypass. Returning [] for now.
- Vision grades still cluster around 6-7 despite updated prompt — may need further prompt tuning or a different model.
- Render env vars (TOOL_PASSWORD, SECRET_KEY) may not be picked up by gunicorn — "graphite" still works as password fallback.

---

## Environment variables — full list (updated)

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
| `ETSY_API_KEY` | Etsy keystring (from developer console) |
| `ETSY_SHARED_SECRET` | Etsy shared secret — **required or Etsy returns 403** |
| `ANTHROPIC_API_KEY` | Claude Vision grading |
| `EBAY_APP_ID` | eBay Finding API — must be **Production** App ID, not Sandbox |
| `EBAY_CERT_ID` | eBay Browse API OAuth (for active listing search) |
| `GITHUB_TOKEN` | Data persistence sync |
| `GITHUB_REPO` | `fergmag/Graphite` |

---

## What to build next

- **Fix Etsy on Render**: add `ETSY_SHARED_SECRET` env var (copy from Etsy developer console, same page as the keystring/API key)
- **Fix eBay on Render**: verify `EBAY_APP_ID` is the Production App ID (not Sandbox) — logs now show "using App ID prefix XXXXXXXX..." so you can confirm which key is loaded
- Vision accuracy: investigate whether prompt changes or switching to Sonnet helps
- **Vision jacket grading**: next major feature — use Claude Vision to grade condition from listing photos, return structured condition score to help decide buy/skip
- Auth system: public landing page + owner-approved accounts to access estimator
- Watchlist items: expandable to show current comps
- Whatnot: revisit if Playwright becomes feasible (would need upgraded Render plan for RAM)

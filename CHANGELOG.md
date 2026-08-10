# Graphite — Build Log

A chronological record of everything built, fixed, and decided. Written for future sessions, LinkedIn documentation, and résumé context. The honest story of how this went from zero to a real tool.

---

## What Graphite Is

Two projects in one repo:

1. **Price estimator / deal scanner** — scrapes eBay, Grailed, Etsy, Depop, and Whatnot for active Carhartt jacket listings. Computes a CASP (Calculated Average Sold Price), deal scores each listing 1–5 against it, and stores alerts when good deals appear. The owner gets a live feed of the best finds across all platforms.

2. **Personal shop** — a storefront for [@graphitevintage](https://instagram.com/graphitevintage) with listings, Stripe checkout (card + Apple Pay + Google Pay), and PayPal integration. No Shopify. No platform fees beyond payment processor cut.

Built by Fergal Maguire, a student and vintage Carhartt reseller based in Canada.

---

## Infrastructure

| Concern | Solution |
|---|---|
| Hosting | Render.com — runs a persistent Python (gunicorn) process |
| Domain | graphitevintage.com via Namecheap DNS → Render |
| DB | SQLite (`graphite.db`) — ephemeral on Render, seeded from JSON on each deploy |
| Photo storage | Cloudinary — photos uploaded via admin, stored as full URLs |
| Data persistence | After every write, JSON files are pushed to GitHub via API; `init_db()` reloads them on startup. Files: `alerts.json`, `estimates.json`, `watchlist.json`, `listings.json`, `archive.json`, `refresh_log.json` |
| Uptime | UptimeRobot pings `/health` every 5 min, which also triggers refresh if >6h since last run |
| Secrets | All API keys stored in `.env` locally and in Render's environment variable dashboard — never committed to git |
| Background jobs | APScheduler (`BackgroundScheduler`) + health-endpoint trigger as fallback |

---

## API Access — How Keys Were Obtained

### eBay
- Registered as an eBay Developer at developer.ebay.com
- Created an app in the eBay Developer Program to get a `CLIENT_ID` and `CLIENT_SECRET`
- Uses OAuth 2.0 client credentials flow to get a bearer token
- Calls the **eBay Browse API** (`/buy/browse/v1/item_summary/search`) for active listings
- Initially tried the **Finding API** (older REST) and **Marketplace Insights API** (sold comps) but the scope for Marketplace Insights was not granted, so it was removed
- All keys stored in `.env` as `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`

### Etsy
- Applied for Etsy API v3 access at developers.etsy.com
- Received API key after review — emailed back and forth with Etsy's developer team
- Uses `x-api-key` header with the keystring (no OAuth needed for public listing reads)
- Fetches listings via `/v3/application/listings/active` and photos via individual `/v3/application/listings/{id}/images`
- Key stored as `ETSY_API_KEY` in `.env` and Render environment

### Stripe
- Account created at stripe.com
- Live keys stored as `STRIPE_SECRET_KEY` and `STRIPE_PUBLISHABLE_KEY`
- Integrated Stripe Checkout for card payments, Apple Pay, and Google Pay
- Test mode used during development; switched to live for production

### PayPal
- Standard PayPal Checkout button integration (no server-side SDK)
- Buyer pays directly via PayPal's hosted flow
- Items priced to absorb the ~3% PayPal fee
- No sandbox complexity — went straight to production button integration

### Cloudinary
- Account created at cloudinary.com (free tier)
- Photos uploaded via admin panel; stored as full CDN URLs in the DB
- Key stored as `CLOUDINARY_URL` in `.env`

---

## Chronological Build Log

### Dec 2025 — Project Foundation (Steps 1–19)

**Dec 28** — Initial Flask project setup. Basic project structure, `requirements.txt`, `app/__init__.py`.

**Dec 29** — Step 2: eBay sold listings scraper (`scrape_ebay.py`). Step 3: retries and backoff for scraping. Step 4: pricing summary and confidence scoring. Step 5: `/estimate` endpoint (eBay comps → price summary). Step 6: JSON file cache with fallback. Step 7: request timeouts + cache-first logic. Step 8: `/seed` endpoint for manually pasting comps JSON. Step 9: starter web UI. Added `ROADMAP.md`.

**Dec 30** — Step 10: SQLite storage for comps and estimates (`db.py`). Step 11: public estimate endpoint with CASP, confidence level, and deal score. Step 12: quantized accuracy (0–100% in steps of 10), cleaner UI. Step 13: model profiles (`model_profiles.py` + `models.json`) with manual CASP overrides for 27 known jacket models.

**Dec 31** — Step 14: watchlist with DB storage and migrations. Steps 15–16: watchlist UI polish, input validation.

**Jan 2026** — Step 17: redefined CASP accuracy. Step 18: background watchlist refresh. Step 19: normalize comps (deduplication).

---

### May–Jun 2026 — Full Rebuild with Claude Code

**May 27** — Restarted the project from scratch using Claude Code as the development assistant. Switched from OpenAI (used earlier) to Claude.

**Jun 6–8** — Dark mode UI overhaul. New color scheme (`#283238` graphite background). Typography refresh (Inter font). Initial shop page structure. Simplified estimator UI.

**Jun 9** — Added gunicorn for production. Shop page layout work. Account planning (Stripe, PayPal, Cloudinary scoping).

**Jun 11–12** — Stripe and PayPal live integration. Checkout flow working. About page written with shipping/return policies, Instagram link. `models.json` populated with jacket data.

**Jun 13** — Merged estimator tool and admin dashboard into unified admin panel with tab navigation (Estimator, Listings, Archive, Watchlist).

**Jun 15–16** — Bell icon for per-query deal alerts. DB schema updates. Scraper improvements.

**Jun 17** — CASP history chart (SVG line graph showing price trend over time). Archive page with collapsible entries. Archive sections backed by DB + JSON persistence.

**Jun 18** — Cloudinary photo upload working via admin. Splash page (went through many iterations — "I hate this splash page"). CAD/USD currency fix. Footer added.

**Jun 19** — Splash page finalized (fade-in/fade-out). USD-only pricing. Footer polish.

**Jun 20** — Grailed scraper wired up (`scrape_grailed.py`). Estimator UI polish. Per-query alert bells (each watchlist item shows its own bell with count). Given price card. Vision grading module added (`vision.py`) using Claude API to grade jacket condition from photos — experiment.

**Jun 21** — Alerts persist across Render redeploys (JSON → GitHub sync pattern established). Junk listing filter (`filter_comps`). Size info shown on listings. Custom animated dropdowns on admin and shop. Watchlist UI: rectangular pills, inline restore without browser dialog.

**Jun 22** — Vision grading: switched to Claude Sonnet for accuracy. Size-adjusted deal scores (M=1.0×, L=0.80×, XL=0.50×, XXL=0.20× vs CASP). Chart y-axis fixed. CASP estimate persistence. eBay API debugging (503 errors, scope issues). Fixed critical JS crash (temporal dead zone) that broke the entire estimator panel. Fixed estimate timeout by returning manual CASP immediately for known models. Updated CHANGELOG.

**Jun 24** — Chart scale fixed (was showing flat line when only one price point existed). Size filter in UI. Condition field for listings. Vision cap to control Claude API costs.

**Jun 25** — Chart x-axis dates fixed. Persist watchlist across redeploys. Shop size pills + listing URLs. Size-aware deal scores in Etsy integration. Renamed "Refund" to "Return Policy".

**Jun 27** — Fixed model-detail timeout. Configurable Etsy timeout. Dropped vision grading from live detail view (too slow, too expensive).

---

### Jul 2026 — Multi-Platform Expansion + Major Fixes

**Jul 8** — Photos fill listing card with cover crop. Real x-axis dates on chart. Restored Grailed/Depop to model-detail. Fixed alerts expiry logic.

**Jul 9** — Fixed alerts never generating when eBay fails (was silently short-circuiting).

**Jul 10** — eBay Browse API for active listings (not just sold comps). Alert persistence fixed. Global-ID header for eBay. About page copy. User-Agent header added to eBay requests.

**Jul 11** — Etsy API auth debugging (`x-api-key` header format). eBay Finding API retry logic. Saving all deal score ≥1 listings as alerts (previously only ≥3). Bell shows total alert count.

**Jul 12** — Vision grading circuit breaker (stops spending credits if too many failures). Fixed Etsy filter and scheduler persistence.

**Jul 13** — Removed `vision.py` entirely. Vision grading was too expensive and unreliable — scrapped. Etsy photos fixed. Bell display cleaned up.

**Jul 14** — eBay Marketplace Insights attempted for sold comps — requested scope not granted by eBay, removed. eBay token scope fix. Size normalization. CASP size adjustment formula.

**Jul 15** — **Major pivot**: CASP now computed from mean of active listing prices (Grailed + eBay Browse) rather than sold comps. This gives a real-time market value rather than historical average. Etsy batch photo fetch attempted.

**Jul 16** — Scheduler debugging. Etsy photos fixed via batch image fetch. CASP display corrected. Shop sort added.

**Jul 17** — Batch of miscellaneous fixes (deal score logic, scraper stability).

**Jul 20** — Deal scores recalculated correctly. Size filter UI. Sort bar for listings (by deal score, price low/high, newest/oldest). Mean CASP (was median). Archive disclaimer added.

**Jul 20** — Critical JS fix: duplicate `const n` declaration caused SyntaxError that broke all tab button switching in admin panel.

**Jul 22** — Deal scores fixed again. Size parsing from listing titles. Etsy photos. Market CASP shown as "Estimated Value". Condition field removed from listings (too subjective). Archive: photo lightbox (click to zoom) + "Updated July 2026" label. Mobile overflow-x fixed.

**Jul 23** — **Unified Get Estimate with Bell Notifs**: both now read from the same stored DB alerts instead of Get Estimate doing a live scrape. Eliminates the "59 vs 47" type count discrepancies. Fixed CASP inconsistency in bell notifs (was showing stale per-alert CASP, now loads canonical CASP from models.json at render time). Archive text color fixed (was gray-on-gray). CASP label added to listing grid cards.

**Jul 23** — Fixed `confidence` UnboundLocalError in scraper.py — was crashing the background scheduler, causing Estimated Value to always show manual CASP and graph to never update.

**Jul 27** — Added Instagram reels idea to roadmap.

**Jul 30** — Dynamic chart Y-axis (was fixed 0–5000, too flat for $300–800 data). Removed listing size filter that was cutting results. Health endpoint auto-refresh: pinging `/health` now triggers a refresh if >6h since last run — meant to work with UptimeRobot. Etsy results cap added.

**Jul 31** — **Search aliases**: `search_terms_for_query()` now returns both canonical ("j97 timber") and abbreviated ("j97 tmb") forms, searches both on every platform. Added ~200 more listings for timber and similar colorways. Added periodic element logo: `17 / Gr / Graphite` (17 is the hex code for Graphite's brand color). Chart zoom (scroll wheel + trackpad pinch).

**Jul 31** — Size parsing priority rewrite: separate regex passes in order (XXL → XL → L → M) so "Large 2X" correctly parses as XXL instead of L. Etsy rate-limit fix (individual image fetches with 0.15s delay). Abbreviations reversed: added `_ALIAS_TO_CODE` reverse map so "j97 timber" also searches "j97 tmb".

**Aug 1** — Logo element number "17" and name "Graphite" fixed to white (was gray from `opacity: 0.7`). Size priority revert for JB0817 (new parse was re-parsing stored sizes and crashing deal scores). Scroll wheel direction flipped (user preference). Junk filter additions: shorts, pants, bibs, dungarees, hoodie, sweatshirt, etc. Etsy no-photo filter added (most no-photo Etsy listings are spam/scam).

**Aug 1** — Fixed J110 pulling junk: removed ambiguous abbreviations ("dst", "brk", "blu") from `_ALIAS_TO_CODE` reverse map. Were generating searches like "j110 dst" which matched cargo shorts. Reverted brief attempt to require_code on relaxed platforms (would have broken JB0817 Etsy).

**Aug 3** — "quilted" added to JUNK_TERMS (later refined — see below). Size select in Get Estimate now actually filters the listing grid client-side. Watchlist panel: "History" dropdown button added.

**Aug 3** — J110 alias fix deployed. Graph title changed to "Listing Price History". Etsy no-photo filter added to bell notifs JS. Fixed `_ALIAS_TO_CODE` excluding dst/brk/blu.

**Aug 4** — **JUNK_TERMS applied at display time**: previously only filtered at scan time, so old junk alerts in DB kept showing. Now applied in both Get Estimate and bell notifs API endpoints. Alert badge counts now exclude no-photo Etsy at SQL level (fixes persistent count mismatch). Refresh history persisted to `refresh_log` DB table.

**Aug 10** — "quilted" over-filtered J110 Detroit jackets (many have quilted liners). Replaced with "quilted vest", "quilted jacket", "quilted coat". Health endpoint now checks `refresh_log` DB (not estimates table) for last-run time — more reliable after restarts. `threading.Lock` added to prevent concurrent refresh runs from health pings and APScheduler overlapping. APScheduler `misfire_grace_time` raised from 5min to 1h so jobs missed during restarts fire immediately. Trackpad pinch (ctrlKey=true) direction fixed — pinch-open now zooms in correctly. History timestamps show date+time (e.g. "Aug 3, 14:32") not just "Xh ago".

**Aug 10** — Refresh log now persisted to `refresh_log.json` via GitHub sync (same pattern as alerts/estimates). DB seeded from JSON on startup so history survives redeploys. `admin_refresh_now` uses shared lock. `search_terms_for_query` adds bare model code ("j110") alongside full query ("j110 darkstone") to catch listings that omit the colorway. Display-time model code enforcement for eBay/Grailed alerts.

**Aug 10 (this session)** — "carhartt" required in all listing titles at both scan time (`filter_comps`) and display time (Get Estimate + bell notifs). Eliminates junk that has model codes but isn't Carhartt. Code enforcement (require model code in title) now applied to all platforms including Etsy/Depop/Whatnot — was previously exempt. Watchlist history UI fixed: show button with 1+ history entries, stat line (ok/failed/alerts) shown in all display paths.

---

## Database Schema

All tables created/migrated in `app/db.py → init_db()`. Schema is additive — always `ALTER TABLE ADD COLUMN`, never drop/recreate.

| Table | Key columns | Purpose |
|---|---|---|
| `watchlist` | `query TEXT` | Saved search queries (e.g. "j97 moss") |
| `comps` | `query, price, title, url, source, created_at` | Raw scraped listing prices |
| `estimates` | `query, casp, accuracy_pct, created_at` | CASP history data points (feeds the chart) |
| `listing_alerts` | `query, source, title, price, url, photo, casp, deal_score, size, seen` | Active deal alerts from all platforms |
| `archive_sections` | `title, text, photos (JSON)` | Archive page content |
| `listings` | `title, price, size, condition, status, photos (JSON), stripe_price_id` | Shop inventory |
| `refresh_log` | `ran_at, total, ok, failed, alerts_saved` | History of background refresh runs |

---

## Key Design Decisions

**Why SQLite not Postgres?** Simpler setup, no extra Render service needed. DB is ephemeral (wiped on redeploy) but all data is persisted via JSON files committed to GitHub via API. Effectively git is the persistent storage layer.

**Why not Shopify?** No monthly platform fees. Stripe + PayPal together cover card, Apple Pay, Google Pay, and PayPal. Owner has full control.

**Why Render not Vercel?** Flask requires a persistent process (APScheduler for background refresh). Vercel's serverless model kills processes between requests, making background jobs impossible.

**Why all platforms instead of just eBay?** eBay is the best for volume but Grailed has the most knowledgeable buyers/sellers and better photos. Etsy has surprising Carhartt inventory. Depop skews younger, occasional good finds. Whatnot is live auction, still experimental.

**CASP formula**: mean of active listing prices (Grailed + eBay Browse). Previously used sold comps from eBay Finding API but eBay denied Marketplace Insights scope. Active listing mean gives a good proxy for market value and updates in real time.

**Deal score thresholds** (price as % of size-adjusted CASP):
- 5/5: ≤50% — steal
- 4/5: 51–65% — great deal
- 3/5: 66–80% — good deal
- 2/5: 81–95% — fair
- 1/5: >95% — market price

**Size multipliers**: M=1.0×, L=0.80×, XL=0.50×, XXL=0.20× (XL and XXL are significantly less desirable in vintage workwear market).

---

## What's Not Built Yet

- Scheduled email/push alerts when deal score threshold is met
- Multi-user auth (currently single password for the whole admin)
- Depop scraper (disabled — rate limits and login-wall issues)
- Automatic condition grading (vision grading was built then scrapped — too expensive, too unreliable)
- Sold page (different from Archive — shows recent sales with prices)
- Mobile-optimized admin panel

---

*Last updated: Aug 2026*

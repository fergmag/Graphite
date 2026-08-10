# Graphite — Build Log

A running record of what's been built, broken, fixed, and shipped. Written for future sessions, for a LinkedIn writeup eventually, and because I like knowing what actually happened vs what I planned.

This is a personal project. It runs on a 2022 MacBook Air and a Render free tier. No team, no sprints, no standups — just me and Claude figuring it out.

---

## What Graphite Is

Two projects in one repo:

**1. Price estimator / deal scanner** — scrapes eBay, Grailed, Etsy, Depop, and Whatnot for active Carhartt jacket listings. Computes a CASP (Calculated Average Sold Price), deal scores each listing 1–5, and stores alerts when good deals appear. I get a live feed of the best finds across all platforms.

**2. Personal shop** — storefront for [@graphitevintage](https://instagram.com/graphitevintage) with listings, Stripe checkout (card + Apple Pay + Google Pay), and PayPal. No Shopify. No platform fees beyond payment processors. Ships worldwide from Canada.

---

## Infrastructure

| Concern | Solution |
|---|---|
| Hosting | Render.com — persistent Python/gunicorn process |
| Domain | graphitevintage.com via Namecheap DNS |
| Database | SQLite (`graphite.db`) — ephemeral on Render, re-seeded from JSON files on each deploy |
| Photo storage | Cloudinary — uploaded via admin panel, stored as CDN URLs |
| Data persistence | All important data (alerts, estimates, watchlist, listings, archive, refresh log) written to JSON and pushed to GitHub via API after every change. `init_db()` reloads from those files on startup. Effectively git is the storage layer, which is both ridiculous and works perfectly. |
| Uptime | UptimeRobot pings `/health` every 5 min — keeps the Render instance awake and triggers a background refresh if >6h since the last one |
| Secrets | All API keys in `.env` locally and in Render's environment variable dashboard. `.env` is in `.gitignore` — never committed. Repo is public so this actually matters. |
| Background jobs | APScheduler runs a 6h refresh cycle in a background thread. Health endpoint is the fallback if the scheduler dies on a restart (which happens). |

---

## API Access — How Keys Were Obtained

### eBay
Registered as a developer at developer.ebay.com, created an app to get a `CLIENT_ID` and `CLIENT_SECRET`. Uses OAuth 2.0 client credentials flow for a bearer token, then calls the **eBay Browse API** for active listings. Originally tried the older Finding API for sold comps and attempted the **Marketplace Insights API** — that scope was never granted by eBay, so the whole feature got ripped out. Keys: `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`.

### Etsy
Applied for Etsy API v3 access at developers.etsy.com — had to email back and forth with their developer team and wait for approval. Once approved, got an API key that works for public listing reads with just an `x-api-key` header. Fetches listings via `/v3/application/listings/active` and photos via individual `/v3/application/listings/{id}/images`. Tried batching the image fetches but Etsy's v3 API returned 404 for the batch endpoint, so it's sequential with a 0.15s delay to avoid rate limits. Key: `ETSY_API_KEY`.

### Stripe
Standard Stripe Checkout — card, Apple Pay, Google Pay. Created account, used test mode during development, live for production. Keys: `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`.

### PayPal
Standard PayPal Checkout button, no server-side SDK needed. Buyer pays via PayPal's hosted flow. Items priced to absorb the ~3% fee. Went straight to production — no sandbox detour needed.

### Cloudinary
Free tier. Photos uploaded through the admin panel and stored as full CDN URLs in the database. Key: `CLOUDINARY_URL`.

---

## Build Log

Dates are from `git log` — not made up.

The roadmap (`ROADMAP.md`) is the original vision from before any of this existed. The actual build did not follow those steps in order. At all.

---

### Dec 2025 — Getting It Off The Ground

Built the core scraping and pricing engine before any real UI. eBay sold listings scraper, JSON file cache, `/estimate` endpoint, SQLite storage for comps and estimates, model profiles with manual CASP overrides for ~27 known jacket models, and a basic watchlist with background refresh. Also the public estimate endpoint: CASP, quantized accuracy (0–100% in steps of 10), and deal score 1–5.

---

### May–Jun 2026 — Restart + Real Features

**May 27** — Restarted the whole project with Claude Code after switching from OpenAI. Much faster iteration.

**Jun 6–12** — Dark mode UI with the graphite color scheme (`#283238` — locked in permanently). Shop page. Stripe + PayPal live. About page with shipping and return policies. `models.json` populated with all the jackets.

**Jun 13** — Merged the estimator and admin into one dashboard with tab navigation (Estimator, Listings, Archive, Watchlist).

**Jun 17** — CASP history chart as an SVG line graph. Archive page with collapsible sections and photo galleries.

**Jun 18–19** — Cloudinary photo uploads working. The splash page took an embarrassing number of commits — "I hate this splash page" is literally in the git history. CAD/USD currency fixed.

**Jun 20** — Grailed scraper added. Per-query deal alert bells. Vision grading module added — used Claude to grade jacket condition from listing photos. Seemed like a good idea at the time.

**Jun 21** — Alerts persist across Render redeploys (the JSON → GitHub sync pattern). First version of the junk listing filter. Custom animated dropdowns.

**Jun 22** — Vision grading switched to Claude Sonnet for better accuracy. Size-adjusted deal scores: M=1.0×, L=0.80×, XL=0.50×, XXL=0.20×. Fixed a JS crash (temporal dead zone) that broke the entire estimator silently. Fixed estimate timeout by returning manual CASP immediately for known models.

**Jun 24–25** — Chart scale fixed, size filter, condition field for listings, real x-axis dates.

**Jun 27** — Dropped vision grading from the live detail view — too slow, too expensive. It hung around until Jul 14 when `vision.py` was finally deleted entirely. Good riddance.

---

### Jul 2026 — Multi-Platform + A Lot Of Bug Fixing

**Jul 8–11** — eBay Browse API for active listings. Alert persistence fixes. Etsy API auth debugging — the header format took a few iterations. Retry logic for eBay.

**Jul 12–14** — Vision grading fully removed. eBay Marketplace Insights attempted for sold comps — scope not granted, removed. Size normalization and CASP size adjustment finalized.

**Jul 15** — **Big pivot**: CASP changed from historical sold comps to mean of active listing prices (Grailed + eBay Browse). Gives real-time market value instead of a trailing average. Etsy batch photo fetch attempted — 404 from Etsy, fell back to individual fetches with rate-limit delay.

**Jul 16–17** — Scheduler debugging. Various scraper stability fixes.

**Jul 20** — Deal scores recalculated correctly. Sort bar for listings. CASP switched to mean (was median). Fixed a JS SyntaxError (`duplicate const n`) that broke all admin tab switching — took a while to track down.

**Jul 22** — Condition field removed from listings (too subjective). Archive: click-to-zoom photo lightbox. Market CASP labeled "Estimated Value".

**Jul 23** — **Unified Get Estimate with bell notifs**: both now read from stored DB alerts instead of Get Estimate doing a live scrape with a 12-second timeout. Eliminated the persistent count mismatch between the two views. Fixed CASP inconsistency in bell notifs where stale per-alert values were showing instead of canonical values from `models.json`.

Fixed a `confidence` UnboundLocalError in `scraper.py` that was silently crashing the background scheduler — the reason Estimated Value always showed manual CASP and the graph never updated. Looked fine until you knew where to look.

**Jul 30** — Dynamic chart Y-axis (was fixed 0–5000, useless for $300–800 data). Health endpoint auto-refresh via UptimeRobot. Etsy, Depop, Whatnot scrapers added.

**Jul 31** — Search aliases: `search_terms_for_query()` searches both "j97 timber" and "j97 tmb" per platform. Found ~200 more listings immediately. Periodic element logo added: `17 / Gr / Graphite` (17 is in Graphite's color code — it's a design detail, not a chemistry reference). Chart scroll-wheel zoom.

Size parsing priority order (XXL first so "Large 2X" doesn't parse as just L). Etsy individual image fetches with rate-limit delay. Abbreviation reverse map added.

**Aug 1** — Logo "17" and "Graphite" text fixed to white (was gray from `opacity: 0.7` — the classic invisible bug). Scroll wheel zoom direction flipped. JUNK_TERMS additions: shorts, pants, bibs, hoodie, sweatshirt, etc. Etsy no-photo filter added — basically all no-photo Etsy listings are scam spam.

Removed ambiguous colorway abbreviations ("dst", "brk", "blu") from the reverse alias map — was generating searches like "j110 dst" that matched cargo shorts on eBay. Fixed at root.

---

### Aug 2026 — Filters, Reliability, Persistence

**Aug 3** — "quilted" added to JUNK_TERMS. Size select in Get Estimate actually works now (was wired up but not filtering). Watchlist refresh history dropdown.

**Aug 4** — JUNK_TERMS applied at display time — previously only at scan time, so old junk in the DB kept showing. Alert badge counts exclude no-photo Etsy at SQL level.

**Aug 10** — "quilted" alone was over-filtering J110 Detroit jackets with quilted liners — fixed to "quilted vest/jacket/coat". Health endpoint now checks `refresh_log` DB instead of estimates table. Threading lock prevents concurrent refreshes. APScheduler `misfire_grace_time` raised to 1h. Trackpad pinch zoom direction fixed. Refresh history timestamps show date + time.

Refresh log persists to `refresh_log.json` via GitHub sync — survives redeploys now.

**Aug 10** — "carhartt" required in all listing titles at scan time and display time. Model code enforcement applied to all platforms (was only eBay/Grailed — Etsy, Depop, Whatnot now get the same treatment).

**Aug 2026 (current)** — Reverted bare model code search (adding "j110" as a bare search term was pulling j65 blu listings into j65 brk results — colorway cross-contamination). Bell notifs now apply the same model code filter as Get Estimate, fixing the "23 in modal but only 7 real listings" issue. Refresh log capped at 20 entries. CHANGELOG rewritten with personality.

Colorway filtering fully fixed: `filter_comps` now requires the colorway (e.g. "brick"/"brk") in the title, not just the model code ("j65"). This stops j65 BLU listings from getting stored under j65 BRK at scan time — the root cause of cross-colorway contamination. Same check added at display time in Get Estimate and bell notifs. "brk" and "blu" re-added to the search alias map (only "dst" stays excluded) so Grailed searches now use both "j65 brick" AND "j65 brk" — should surface listings the owner posted with abbreviations in the title. Bell badge count now updates to the actual rendered count after opening the modal, fixing the badge-vs-modal mismatch. No-photo Etsy filter moved server-side so badge and rendered count stay aligned.

---

## Database Schema

Tables created/migrated in `app/db.py → init_db()`. Always `ALTER TABLE ADD COLUMN` — never drop/recreate.

| Table | Purpose |
|---|---|
| `watchlist` | Saved search queries ("j97 moss", "j110 darkstone", etc.) |
| `comps` | Raw scraped listing prices per query |
| `estimates` | CASP history per query — feeds the price chart |
| `listing_alerts` | Active deal alerts from all platforms, 7-day retention |
| `archive_sections` | Archive page content |
| `listings` | Shop inventory with Stripe price IDs |
| `refresh_log` | Last 20 background refresh runs |

---

## Key Design Decisions

**Why SQLite not Postgres?** Simpler, zero cost, no extra Render service. DB is ephemeral on Render but all data pushes to GitHub as JSON after every write — git is effectively the storage layer. Sounds insane, works fine. Also this is a personal project run entirely from a 2022 MacBook Air.

**Why not Shopify?** Monthly platform fees, limited control. Stripe + PayPal natively cover card, Apple Pay, Google Pay, and PayPal. Done.

**Why Render not Vercel?** Flask needs a persistent process for background refresh jobs. Vercel's serverless model kills processes between requests — APScheduler would never survive.

**Why all platforms?** eBay has volume. Grailed has knowledgeable sellers and better photos. Etsy has surprising Carhartt inventory. Depop skews younger. Whatnot is live auction, still experimental. More platforms = more data = better deal detection.

**CASP formula**: mean of active listing prices (Grailed + eBay Browse). Originally sold comps from eBay Finding API but eBay denied Marketplace Insights scope. Active listing mean is arguably better anyway — it's what you'd pay today.

**Deal score thresholds** (price vs size-adjusted CASP):
- 5/5: ≤50% — steal
- 4/5: 51–65% — great deal  
- 3/5: 66–80% — good deal
- 2/5: 81–95% — fair
- 1/5: >95% — market price or worse

**Size multipliers**: M=1.0×, L=0.80×, XL=0.50×, XXL=0.20×. XL and XXL go for significantly less in vintage workwear — not many people want oversized Carhartts.

**The 854 vs 616 type discrepancy**: `alerts_saved` in the refresh log counts everything written to the DB during a run. The displayed count applies additional filters at render time (carhartt required, no junk terms, model code in title, no-photo Etsy out). Raw saves will always be higher. Not a bug.

---

## What's Not Built Yet

- Email/push alerts when a high deal score listing appears
- Sold page (distinct from Archive — recent sales with prices)
- Grailed: own listings sometimes don't appear in search results (possible Grailed deduplication of seller's own items)
- Depop scraper (disabled — hits login walls aggressively)
- Mobile admin panel
- Multi-user auth (single password for now)

---

*Updated as things change. Dates are from `git log`.*

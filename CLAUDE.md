# CLAUDE.md — Graphite Project Brief

Read this entire file before touching any code. This is the source of truth.

---

## What Graphite Is

Graphite is a two-part project:

1. **Price estimator tool** — scrapes eBay sold listings to estimate fair market value for vintage Carhartt jackets. Built and partially working already.
2. **Personal shop** — a storefront for @graphite.vintage (Instagram resale business) to display listings and take payments. Not built yet.

The owner is a non-developer. Keep all explanations clear. Always show the full terminal workflow when making changes (activate venv, compile check, run, git commit).

---

## Core Vocabulary — Never Change These Terms

- **CASP** = Calculated Average Sold Price (our market value estimate)
- **Accuracy of CASP** = reliability of the CASP figure, shown as 0–100% in steps of 10
- **Deal score** = 1–5 rating of how good a listing is vs CASP (only shown when asking price is provided)
- **Watchlist** = saved search queries; will eventually auto-refresh

---

## What's Already Built (DO NOT break these)

### Backend (`app/`)
- `main.py` — Flask app, all API routes
- `scrape_ebay.py` — scrapes eBay sold listings, handles retries, parses prices/shipping
- `pricing.py` — computes CASP using median + trimmed mean + confidence score
- `db.py` — SQLite via `graphite.db`, stores comps, estimates, watchlist
- `cache.py` — file-based JSON cache keyed by query
- `public_view.py` — formats the public-facing payload (CASP, accuracy, deal score)
- `model_profiles.py` + `models.json` — manual CASP overrides for specific jacket models

### API Endpoints (keep stable)
- `GET /` — serves index.html
- `GET /health` — status check
- `GET /estimate?query=...` — live scrape or cache, returns CASP + accuracy + optional deal score
- `POST /seed` — manually seed cache with pasted comps JSON
- `GET|POST|DELETE /watchlist` — manage saved queries

### Frontend
- `app/templates/index.html` — single HTML file, vanilla JS, no frameworks
- Shows: CASP card, Accuracy card, Deal score card, Watchlist
- Functional but visually rough — redesign is planned (Phase 1)

### Database
- `graphite.db` — SQLite, already has scraped data in it
- Any schema changes must use `ALTER TABLE ADD COLUMN` or proper migration — never drop/recreate tables

---

## What To Build Next — In Order

### Phase 1: Redesign the estimator UI (START HERE)

The current `index.html` is a dev tool. Turn it into a real webpage that looks like it belongs to a brand called Graphite. Instagram handle is @graphite.vintage.

Design direction: industrial/utilitarian meets refined minimal. Workwear brand meets pricing tool. Dark mode. Strong typography. No generic AI aesthetics.

UX fixes to include:
- "Get CASP" is the primary action. Seed is hidden in an advanced/collapsed section.
- Accuracy label should never imply "buy" — it means reliability of the estimate only
- Watchlist: saving a query must not wipe current CASP results on screen
- Watchlist: fix "undefined" on delete
- Consistent quantized accuracy (0, 10, 20...100%) everywhere

Do NOT add new backend features in Phase 1. Frontend only.

### Phase 2: Add the shop / listings section

A second section or page on the same site showing @graphite.vintage inventory.

Requirements:
- Owner manually adds listings (no CMS, just a JSON file or simple data structure)
- Each listing: photo(s), title, size, condition, price, sold/available status
- Stripe Checkout for card + Apple Pay + Google Pay
- PayPal button integration (standard checkout, owner prices items to absorb ~3% fees)
- No Shopify, no platform fees beyond payment processor cut
- Must work well on mobile (Instagram audience)

### Phase 3: Scraper automation + watchlist alerts (later)

- Scheduled background refresh of watchlist queries
- Email/push alert when deal score threshold is met
- Multi-site support (Depop, Grailed, Poshmark after eBay is solid)
- Condition grading (rule-based first, ML later)

---

## Engineering Rules

- Small changes per session. Don't refactor everything at once.
- No new frameworks unless explicitly discussed. Keep it Flask + vanilla JS.
- Prefer diffs/snippets over full file rewrites unless necessary.
- DB changes: always backwards-compatible. Use ALTER TABLE ADD COLUMN.
- Before every change: explain what files will be touched and why.
- After every change: provide the full terminal workflow to test and commit.

### Standard workflow (always provide this after changes)
```bash
cd ~/Projects/Graphite
source .venv/bin/activate
python -m py_compile app/main.py app/db.py app/pricing.py
python -m app.main
# open http://127.0.0.1:5000 and test manually, then ctrl+c
git add <changed files>
git commit -m "Phase X: description"
git push origin main
```

---

## Deployment Plan

- Hosting: Render.com free tier (supports Flask, persistent process for future background jobs)
- Domain: graphitevintage.com (on Namecheap)
- Payments: Stripe + PayPal checkout button
- No Shopify. No Vercel serverless.

---

## Environment

- Python 3.9, venv at `.venv/`
- Run app with: `python -m app.main`
- Venv already set up, all packages installed
- `graphite.db` has real scraped data — do not delete it
- GitHub: https://github.com/fergmag/Graphite

---

## How To Start Each Session

Paste this brief, then say what phase or task you want to work on. Claude Code will read the full context and work within these constraints.
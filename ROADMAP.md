# Graphite Roadmap

Graphite is a Carhartt/vintage workwear aggregation + valuation platform.
Start small: comps → estimate → confidence. Then expand.

## Now (MVP)
- [ ] Scrape sold comps (eBay first)
- [ ] Basic price estimate (median + trimmed mean)
- [ ] Basic confidence score (sample size + spread)
- [ ] Simple API endpoint: /estimate?query=...

## Next (Core Intelligence)
- [ ] Undervalued listings (estimate vs asking)
- [ ] Overpriced listings
- [ ] Mislabelled listings (title/attrs don't match model patterns)
- [ ] Low-engagement / stale listings

## Next (Search & Aggregation)
- [ ] Multi-site pulling (eBay → others later, Depop, Etsy, Grailed, Poshmark, Mercari)
- [ ] Target keywords, J43, Red Detroit, Blue Detroit, Purple Detroit, JB, JS, 90s, etc
- [ ] Filters: model (J01/J130/etc), size, condition, color
- [ ] Saved searches
- [ ] Notifications / alerts

## ML + Image
- [ ] Identify jacket model from images
- [ ] Predict condition / wear from images
- [ ] Combine image + title for better accuracy
- [ ] Confidence % on predictions

## Platform Features
- [ ] User accounts
- [ ] Saved jackets / collections
- [ ] User-posted listings
- [ ] In-app buying/selling

## Monetization
- [ ] Affiliate links (early)
- [ ] Pro features (alerts, history, bulk searches)
- [ ] Seller tools / pricing insights

## Long-term Trust Layer
- [ ] Authentication / legit check system
- [ ] Anti-scam protection
- [ ] Escrow-style verified trades (Graphite as trusted middleman)

---

## Roadmap steps updated for Codex, Step 15 and beyond (build plan)

### Step 15: Reduce Seed/Get confusion (UX + semantics)
Goal: make the UI feel obvious. “Seed” should be advanced, “Get CASP” should be primary.
- Decide what Seed means (manual paste + persist) vs Estimate (compute CASP/accuracy/deal score)
- Likely outcome: one primary action button for users; seed becomes secondary/hidden

### Step 16: Watchlist polish
Goal: watchlist feels stable and predictable.
- Save exactly what the user typed
- Fix “undefined” deletes
- Don’t wipe CASP/Accuracy results when adding/removing watchlist items (keep UI state)

### Step 17: Consistent CASP/Accuracy meaning everywhere
Goal: avoid “accuracy = buy” confusion.
- Accuracy of CASP = reliability of the computed average, not buy probability
- Quantize accuracy to 0/10/20…100 consistently

### Step 18: Refresh a watchlist item (first automation-shaped feature)
Goal: click “Refresh” on a watch query to update its latest comps/summary.
- Live scrape if possible, fallback to cache
- Write updated result to DB (and update cached payload)

### Step 19: Normalize comps (prep for multi-site)
Goal: make data consistent and future-proof.
- Consistent fields: price, shipping, currency, url, ended_at, source, model_guess (later)
- Dedupe by url / listing id
- Decide and enforce currency rules (later: FX conversion)

### Step 20: Model profiles expansion
Goal: map queries to canonical models and rules.
- Model registry: canonical name, aliases, optional manual CASP override for rare models
- Future: per-size/condition adjustments

### Step 21: Filtering v1 (no ML yet)
Goal: cleaner comps = better CASP.
- Text heuristics to drop mismatches (kids/women/vest/wrong code)
- Basic size extraction/bucketing from titles
- Optional: exclude obvious “new listing / not sold” noise

### Step 22: Scheduled refresh loop (automation v1)
Goal: Graphite checks watchlist queries automatically.
- A background loop/cron that refreshes watchlist queries on a cadence
- Store refresh timestamps + results

### Step 23: Alerts/notifications
Goal: notify users when something is a deal.
- First pass: in-app notifications feed
- Next: email/push
- Trigger conditions: deal score threshold, new listing match, stale listing drops, etc.

### Step 24: Image pipeline
Goal: start saving image data so ML becomes possible.
- Store image URLs and thumbnails (at least metadata)
- Link images to comps/listings

### Step 25: Condition grading (A–D)
Goal: incorporate condition into CASP and deal scoring.
- Start manual/rule-based condition
- Upgrade to ML model later
- Condition-adjusted CASP (by model + size + condition)

### Step 26: Accounts + personalization
Goal: per-user watchlists, alerts, saved items.
- Auth + user tables
- Permissions and ownership of watchlist items

### Step 27: Saved searches + user controls
Goal: user chooses what to track and how.
- Saved searches, alert thresholds, frequency, filters

### Step 28: Marketplace + trust layer (later)
Goal: optional expansion, not needed for core value.
- Listing posting + messaging
- Trust features and (eventually) escrow-style verified trades

### Step 29: Monetization + production hardening
Goal: shipping-grade stability.
- Freemium limits + Pro features
- Deploy production server + observability + rate-limits + safer scraping


## Will figure out how to meet the rest of the goals later
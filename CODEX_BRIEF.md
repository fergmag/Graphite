# Graphite — Codex Brief

## Product
Graphite is a workwear aggregation + valuation platform.

Core terms:
- CASP = Calculated Average Sold Price (our market value estimate)
- Accuracy of CASP = quantized 0–100% in steps of 10 (how reliable CASP is)
- Deal score = 1–5 if asking is provided (how good the deal is vs CASP)
- Watchlist = saved queries; later becomes automated scraping + notifications

## UX rules
- Minimal, uncluttered UI (Apple-esque)
- No raw JSON on the website (debug stays in API / dev only)
- Consistent wording: CASP + Accuracy of CASP

## Current implementation
- Flask + SQLite
- /seed accepts manual comps JSON, writes cache/DB, returns CASP/Accuracy
- /estimate (cache_first) returns cached result; adds deal score if asking provided
- watchlist stored in DB and rendered in UI

## Engineering rules
- Keep changes small per “Step X” commit
- DB changes must be backwards-compatible (migrations/ALTER TABLE ADD COLUMN)
- Avoid introducing frameworks; keep Flask simple

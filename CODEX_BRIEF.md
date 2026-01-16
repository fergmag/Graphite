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

## Two parts to each step
-Part 1: Decide how to tackle the step, explain and plan
-Part 2: Execute, YOU make the changes to the code
-Do this for every step

## Provide me with the full workflow
May look like this:
Last login: Thu Jan  1 21:56:03 on ttys003
fergalmaguire@Fergals-MacBook-Air ~ % cd Projects
fergalmaguire@Fergals-MacBook-Air Projects % cd Graphite
fergalmaguire@Fergals-MacBook-Air Graphite % source .venv/bin/activate
(.venv) fergalmaguire@Fergals-MacBook-Air Graphite % python -m py_compile app/main.py app/public_view.py app/db.py

(.venv) fergalmaguire@Fergals-MacBook-Air Graphite % python -m app.main
 * Serving Flask app 'main'
 * Debug mode: on
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on http://127.0.0.1:5000
Press CTRL+C to quit
 * Restarting with stat
 * Debugger is active!
 * Debugger PIN: 102-880-010
^C%                                                                             (.venv) fergalmaguire@Fergals-MacBook-Air Graphite % git add app/main.py app/db.py
(.venv) fergalmaguire@Fergals-MacBook-Air Graphite % git commit -m "Step 19: normalize comps"
(.venv) fergalmaguire@Fergals-MacBook-Air Graphite % git push origin main


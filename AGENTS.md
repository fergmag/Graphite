# Graphite: Codex guardrails

## Product principles
- Keep UI minimal and uncluttered (Apple-esque).
- Primary terms:
  - CASP = Calculated Average Sold Price
  - Accuracy of CASP = quantized percent (0,10,20...100)
- Do not show raw JSON/debug output in the normal UI flow.

## Engineering constraints
- Prefer small edits over refactors; avoid renaming functions unless required.
- Any SQLite schema changes must include a migration path.
- Keep endpoints stable unless explicitly requested:
  - POST /seed
  - GET /estimate
  - GET/POST/DELETE /watchlist
- When proposing changes, include:
  - files touched
  - why
  - how to test (at minimum: python -m py_compile and a quick manual run)

## Output preference
- Prefer diffs or clearly scoped snippets over full-file rewrites unless asked.

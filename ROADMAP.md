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

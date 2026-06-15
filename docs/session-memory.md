# Session Memory

Last updated: 2026-06-15

## Current State

- Project is a static meteorite inventory dashboard backed by a Python scraper.
- Frontend files are `index.html`, `styles.css`, and `app.js`; no JS build step is required.
- Scraper dependencies are in `scraper/requirements.txt`: `beautifulsoup4`, `requests`, and `lxml`.
- Generated listing data lives in `data/listings.json`; current checked data is a full scrape with 1,314 listings from 7 enabled sources.
- Source registry lives in `data/sites.json`; parser backlog and marketplace rules live in `docs/parser-backlog.md`.
- `.venv/` is local and ignored. Python bytecode caches should be removed rather than committed.

## Active Sources

- SV Meteorites uses `sv_meteorites` and parses public inventory/detail pages with individual specimen fields and category/non-listing rejection.
- Meteorlab uses `meteorlab` and parses old static catalog tables, captures specimen images, skips sold markers, and supports email-for-price rows.
- BAITYLIA uses `baitylia` and parses categorized inventory rows and follows them to detail pages while rejecting header/category rows.
- FossilEra uses `fossilera` and parses active-only meteorite cards and detail pages with pagination and sold-card suppression.
- Aerolite Meteorites uses `aerolite` and parses narrow WooCommerce shop categories while excluding sold and non-specimen products.
- Meteolovers uses `meteolovers` and parses Elementor/Woo product cards under meteorite paths with schema/meta prices and sold/status checks.
- The Meteorite Market uses `meteorite_market` and parses validated static sale pages with duplicate-cell cleanup and sold-price rejection.

## Disabled Sources

- Parser starts remain disabled for Meteorite Exchange, Galactic Stone & Ironworks, Arizona Skies Meteorites, IMPACTIKA, SkyFall Meteorites, justMETEORITES, and Mini Museum Meteorites until their blockers are cleared.
- Fossil Realm Meteorite Collection and TOP Meteorite remain disabled pending reliable full-fetch validation because a previous full scrape returned 0 listings from SSL EOF fetch failures despite smoke tests.
- Collector Secret Meteorites and The Space Shop Meteorites remain policy-blocked disabled sources.
- Disabled sources are visible in the UI source panel but are excluded from scraper runs and listing results.

## Recent Decisions

- README was expanded to be the canonical guide for setup, scraping, validation, workflow behavior, data files, parser policy, and no local media copying.
- A session memory file was added under `docs/` for future agents.
- `.gitignore` now covers common Python, Node/static tooling, local environment, editor, OS, build, temp, and cache artifacts without ignoring source/data docs.
- `scraper/__pycache__/` was removed as a generated artifact.
- `.venv/` was intentionally left in place because it may be useful locally and is ignored.

## Parser Policy

- Do not enable a source with the generic parser first.
- Add or verify a site-specific parser before setting `enabled: true`.
- Emit individual sellable specimens only; reject category pages, books, articles, contact pages, broad collections, souvenir-only items, jewelry-only products, fossils, minerals, and sold-only/archive pages.
- Keep disabled parser starts disabled until row-quality verification passes across pagination and sold/out-of-stock behavior.
- Marketplace candidates need strict storefront vetting; avoid broad eBay/Etsy/category scraping.
- Respect source terms, robots expectations, login walls, CAPTCHAs, and anti-bot systems. Disable a source if scraping is not allowed.

## Workflow And Rotation

- Workflow file is `.github/workflows/scrape-and-publish.yml`.
- Pushes to `main` and manual dispatch run a full scrape of enabled sources.
- Scheduled runs are hourly and use `--rotate --preserve-existing --rotation-key "${{ github.run_number }}"`.
- Rotation refreshes one enabled source per run and preserves existing rows for enabled sources not scraped in that run.
- The workflow validates generated data, commits `data/listings.json` changes, and pushes them.
- `data/listings.json` is ignored by workflow path triggers to prevent immediate scraper commit loops.

## UI Decisions

- UI fetches `data/listings.json` and `data/sites.json` with `cache: "no-store"`.
- Search includes title, source, type, subtype, classification text, and URL.
- Unavailable rows are hidden by default; the checkbox includes them.
- Client-side filtering defensively hides obvious non-individual/category rows and decorative image leftovers.
- Price/g summaries are only shown after narrowing results or when all visible rows share a title.
- Source panel exposes enabled, disabled parser start, and disabled backlog states.
- Images are remote URLs only. Do not add local media copying or seller image mirroring.

## Validation Commands

Run from the repo root:

```sh
node --check app.js
PYTHONDONTWRITEBYTECODE=1 python3 scraper/validate_listings.py
git diff --check
```

Useful local scrape commands:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scraper/scrape.py
PYTHONDONTWRITEBYTECODE=1 python3 scraper/scrape.py --rotate --preserve-existing --rotation-key 1
PYTHONDONTWRITEBYTECODE=1 python3 scraper/scrape.py --site "FossilEra" --preserve-existing
```

## Next Tasks

- Recheck disabled parser starts one by one with narrow local scrapes before enabling any additional source.
- Add lightweight parser tests or saved sample HTML before broadening source coverage.
- Review whether GitHub Pages should be documented or configured more explicitly for the hosting mode in use.
- Continue improving Meteorlab title/classification edge cases only from concrete validation findings.

## Warnings For Future Agents

- Do not delete source files or `data/listings.json` during cleanup.
- Do not commit or push unless the user explicitly asks.
- Use `PYTHONDONTWRITEBYTECODE=1` for Python checks to avoid recreating `__pycache__/`.
- Use `apply_patch` for manual file edits.
- Do not add overbroad ignores such as `data/`, `*.json`, or `docs/`.
- Do not download or commit seller product images, screenshots, or media.

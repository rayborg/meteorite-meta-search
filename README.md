# Meteorite Meta Search

Meteorite Meta Search is a static dashboard for comparing public meteorite seller inventory. A Python scraper normalizes selected seller pages into `data/listings.json`; the browser UI reads that JSON directly and provides search, source/type filters, sort controls, availability filtering, source status, and price-per-gram summaries.

Target repo name: `meteorite-meta-search`

Default public URL after GitHub Pages is enabled: `https://rayborg.github.io/meteorite-meta-search/`

## Project Purpose

The project tracks short, factual listing metadata from meteorite dealer inventory pages so collectors can compare specimens across sources without copying seller pages or media into this repo. It focuses on individual sellable meteorite, tektite, and impactite specimens with useful fields such as clean display title, canonical name metadata, source URL, price, currency, USD-normalized price, weight, estimated price/g, classification, availability, parser, scrape time, and remote image URLs.

## Static Dashboard

The frontend is intentionally static:

- `index.html` provides the page structure and table template.
- `styles.css` provides the dark responsive dashboard styling.
- `app.js` fetches `data/listings.json` and `data/sites.json` with `cache: "no-store"`.
- No bundler, package manager, or local media pipeline is required.

Frontend behavior:

- Search covers title, source, type, subtype, classification text, and URL.
- Type chips and type/source selects are built from currently visible individual listings.
- Unavailable listings are hidden by default and can be included with the checkbox.
- Non-individual leftovers such as generic category/book/catalog rows and decorative images are filtered client-side as a defensive fallback.
- Table headers and the sort select share the same sort state.
- Average and lowest price/g summaries are shown only after narrowing by search, type, source, or a single repeated title.
- Search results can show USD price/g distribution charts by Official MetBull meteorite name when the search is narrow enough; unresolved names are grouped under `Other meteorite`.
- The source panel lists every configured source and labels it as enabled, disabled parser start, disabled backlog, or policy/reference. Source status count cards are clickable and list the sources in that category.
- Listing images remain remote `http` or `https` URLs; `image_url` is primary and optional `image_urls` values are tried as fallbacks before showing `No image`.

## Scraper

The scraper lives in `scraper/scrape.py` and uses site-specific parsers where output quality has been verified. It applies a normal user agent, waits between requests, does not bypass logins/CAPTCHAs/anti-bot systems, and writes normalized listing data to `data/listings.json`.

It extracts or derives:

- Meteorite type, including pallasite, chondrite, carbonaceous chondrite, ordinary chondrite, iron, achondrite, lunar, Martian, mesosiderite, and tektite/impactite.
- Subtypes and classification clues such as H/L/LL, carbonaceous groups, HED terms, iron groups, NWA numbers, and related class text.
- Price, currency, weight, estimated price/g, USD-normalized price fields, remote image URLs, Official MetBull canonical-name fields, availability, parser confidence, and scrape timestamps when present.

## Active Sources

Enabled sources are configured in `data/sites.json` with `enabled: true` and are included in full scrapes, selected scrapes, and rotation runs.

| Source | Parser | Notes |
| --- | --- | --- |
| SV Meteorites | `sv_meteorites` | Parses public inventory/detail pages with individual specimen fields and category/non-listing rejection. |
| Meteorlab | `meteorlab` | Parses old static catalog tables, captures specimen images, skips sold markers, and supports email-for-price rows. |
| BAITYLIA | `baitylia` | Parses categorized inventory rows and follows them to detail pages while rejecting header/category rows. |
| Meteorite Exchange | `meteorite_exchange` | Parses bounded WooCommerce product pages with product-detail proof, category/archive/add-to-cart/filter rejection, and non-specimen filtering. |
| FossilEra | `fossilera` | Parses active-only meteorite cards and detail pages with pagination and sold-card suppression. |
| Prehistoric Fossils Meteorites | `prehistoric_fossils` | Parses only the NWA meteorites WooCommerce category with stock/product proof, exact weights, prices, images, and frame/jar/display rejection. |
| Galactic Stone & Ironworks | `galactic_stone` | Parses BigCommerce product grids with add-to-cart/detail proof, title weights, and non-specimen/out-of-stock rejection. |
| The Meteorite Market | `meteorite_market` | Parses validated static sale pages with duplicate-cell cleanup and sold-price rejection. |
| Arizona Skies Meteorites | `arizona_skies` | Parses only Lunar/Martian final specimen pages and clean inexpensive rows with exact price, individual weight, valid image, and sold/non-specimen rejection. |
| Aerolite Meteorites | `aerolite` | Parses narrow WooCommerce shop categories and excludes sold, jewelry, books, stands, equipment, and other non-specimens. |
| Astro West | `astro_west` | Parses WooCommerce meteorite category pagination and product details with stock/add-to-cart proof while filtering jewelry, pendants, display boxes, gift sets, and other non-specimens. |
| IMPACTIKA | `impactika` | Parses Woo Store API description rows with smaller retried JSON requests and rejects sold, lot/range, from-to, per-gram, and non-specimen rows. |
| SkyFall Meteorites | `skyfall_meteorites` | Parses Woo product sitemap entries under meteorites-for-sale paths with positive title weights and prices. |
| Meteolovers | `meteolovers` | Parses Elementor/Woo product cards under meteorite paths with schema/meta prices and sold/status checks. |
| justMETEORITES | `justmeteorites` | Parses product-sitemap detail pages while excluding sold paths, knife material, gifts, and non-specimen products. |
| Mini Museum Meteorites | `mini_museum` | Parses a narrow Shopify meteorite subset with product-type, gift/jewelry/card/collection, positive-price, and title-weight checks. |
| Fossil Realm Meteorite Collection | `fossil_realm` | Parses Shopify meteorite products with available variants, positive non-placeholder prices, and title weights. |
| TOP Meteorite | `top_meteorite` | Parses Shopify specimen products with available variants, positive prices, title weights, and meteorite keywords. |
| Buy Meteorite | `buy_meteorite` | Parses the Shopify meteorites collection with available variants, meteorite type/tag checks, positive prices, title weights, images, and non-specimen rejection. |
| BuyMeteorites.com | `thompson_meteorites` | Parses the public Thompson Meteorite Collection Woo Store API with in-stock/add-to-cart proof, API currency prices, exact title weights, images, and service/discovery-set rejection. |
| JC Meteorite Collection | `jc_meteorite_collection` | Parses the custom public catalogue API with paginated product rows, batched details, USD prices, exact unit-bearing weights, images, and sold/set/thin-section/fulgurite rejection. |
| PolandMET | `polandmet` | Parses bounded Woo Store API product pages with in-stock/add-to-cart checks, title-derived individual weights, non-specimen rejection, image fallbacks, and local MetBull-assisted clean names. |
| KD Meteorites | `kd_meteorites` | Parses bounded static specimen sale hubs, rejects non-specimen/info pages, requires exact price/weight/image evidence, and cleans old-table titles through page/URL identity. |
| Meteorite Recon | `meteorite_recon` | Parses only the static Stones and Irons sale pages, requires exact price and individual weight, keeps remote image URLs, and rejects offer-price/category/non-specimen rows. |
| WWMeteorites | `wwmeteorites` | Parses bounded same-domain sale/detail pages with exact row price/weight requirements, sold/category/lot/range/non-specimen rejection, and remote image URLs only. |
| Meteor Center | `meteor_center` | Parses WooCommerce product cards across shop pagination, including `/page/2/`, with in-stock/add-to-cart proof, EUR prices, title weights, and non-specimen/range rejection. |
| Collecting Meteorites | `collecting_meteorites` | Parses public WordPress sale cards plus bounded detail pages for exact title weights, EUR prices, category text, remote images, and per-gram/non-specimen/ambiguous multi-specimen rejection. |

## Disabled And Backlog Sources

Disabled sources remain in `data/sites.json` for visibility but are excluded from scraping, rotation, and results until explicitly enabled.

Disabled parser starts:

- `eBay - whitehouse_meteorites`
- `eBay - topherspin`
- `eBay - fobos13ali`
- `eBay - yoda_meteorites`
- `eBay - the.interstellar.collection`
- `eBay - meteoritetreasure`
- `eBay - Top Meteorite Store`

The eBay connector is official Browse API only, seller-allowlist only, fixed-price only, and disabled/config-gated until `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` are configured and rows are manually reviewed. Do not scrape broad eBay search/category pages.

Disabled backlog entries visible in the source panel:

- Etsy - SpaceTreasuresUS
- Etsy - SPACEMANGIFT
- Etsy - saharagems
- Meteorite Hunter

The Etsy storefront candidates were reassessed on 2026-06-17. Narrow public storefront fetches returned HTTP 403, so no safe public-HTML parser is enabled; any future Etsy work should use official Etsy Open API credentials, vetted storefront allowlists, strict souvenir/gift/gem filtering, and manual row review before enablement.

Policy-blocked disabled sources:

- Collector Secret Meteorites: broad eBay affiliate/aggregator feed rather than direct verified inventory.
- eBay Marketplace Search: broad marketplace search/category scraping is blocked; use seller allowlists only.
- Etsy Marketplace Search: broad marketplace search/category scraping is blocked; use official Etsy Open API credentials with vetted storefront allowlists only.
- Facebook Meteorite Groups: login/community source; keep manual/research only.
- IMCA Member List: reference/vetting source, not inventory.

Disqualified storefronts such as The Space Shop Meteorites and the Galactic Stone eCrater mirror are intentionally not counted as configured sources because bounded review found souvenir/display/non-individual inventory rather than useful individual specimens.

Additional marketplace candidates and detailed parser notes are tracked in `docs/parser-backlog.md`.

## Setup

Python dependencies are only needed for scraping and validation.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r scraper/requirements.txt
```

`.venv/` is ignored and should stay local.

Optional marketplace credentials must stay out of tracked files. For local eBay API testing, copy `.env.example` to `.env`, fill the real values there, and export them before running the scraper:

```sh
set -a
source .env
set +a
```

`.env` and `.env.*` are ignored by git. Do not put real credentials in `data/sites.json`, workflow files, docs, or committed examples. For scheduled GitHub Actions runs, add credentials as repository secrets instead of local files.

To view the static site locally, serve the repo root so browser `fetch()` calls work:

```sh
python3 -m http.server 8000
```

Then open `http://localhost:8000/`.

## Local Scraping

Avoid bytecode while running local checks:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scraper/scrape.py
```

Useful scraper modes:

- `PYTHONDONTWRITEBYTECODE=1 python3 scraper/scrape.py` refreshes all enabled sources and rewrites `data/listings.json`.
- `PYTHONDONTWRITEBYTECODE=1 python3 scraper/scrape.py --rotate --preserve-existing --rotation-key 1` refreshes one enabled source and preserves existing rows for the other enabled sources.
- `PYTHONDONTWRITEBYTECODE=1 python3 scraper/scrape.py --site "FossilEra" --preserve-existing` refreshes one enabled source by name or parser id while preserving the rest.
- `PYTHONDONTWRITEBYTECODE=1 python3 scraper/scrape.py --sites "FossilEra,Aerolite Meteorites" --preserve-existing` refreshes multiple enabled sources.

The scraper refuses disabled sources in `--site`/`--sites` selections. Enable a source only after local parser verification shows individual sellable rows with safe filtering.

## Validation

Run these before committing scraper, data, or frontend behavior changes:

```sh
node --check app.js
PYTHONDONTWRITEBYTECODE=1 python3 scraper/validate_listings.py
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile scraper/scrape.py scraper/validate_listings.py scraper/update_metbull_cache.py scraper/discover_sources.py scraper/validate_source_discovery.py
git diff --check
```

`scraper/validate_listings.py` checks required fields, metadata consistency, duplicate keys, price/g math, parser/source validity, sold/unavailable markers, bad decorative image URLs, suspicious category rows, and classification preservation.

## Rotation Workflow

`.github/workflows/scrape-and-publish.yml` runs on pushes to `main`, on hourly schedule, and by manual dispatch.

- Scheduled runs execute `python scraper/scrape.py --rotate --preserve-existing --rotation-key "${{ github.run_number }}"`.
- Rotation selects one enabled source per run and preserves existing rows for enabled sources that were not scraped in that run.
- Push and manual runs currently execute a full scrape of all enabled sources.
- The workflow validates `data/listings.json`, commits inventory changes, and pushes them back to the repository.
- `data/listings.json` and `data/metbull_names.json` are ignored by the workflow trigger path filter so automated data-only commits do not immediately retrigger the workflow.
- The workflow passes optional `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` values from GitHub repository secrets, but eBay sources remain disabled until explicitly reviewed and enabled.
- Workflow concurrency cancels stale scrape runs, and the commit step skips inventory commits if `main` advanced while the scrape was running.

GitHub Pages can serve the static files directly from the repository. No separate frontend build step is required.

`.github/workflows/update-metbull-cache.yml` refreshes the local MetBull cache on Fridays at 07:17 UTC, after the recent Thursday Meteoritical Bulletin RSS batch window. It runs `scraper/update_metbull_cache.py`, normalizes existing listings against the refreshed cache without scraping seller sites, validates the generated JSON, and commits only if `data/metbull_names.json` or `data/listings.json` changed.

`.github/workflows/discover-sources.yml` runs twice daily at 06:37 and 18:37 UTC and by manual dispatch. It is review-only: it runs `scraper/discover_sources.py`, validates the generated JSON with `scraper/validate_source_discovery.py`, and uploads `source-discovery/source-discovery.json` plus `source-discovery/source-discovery.md` as an Actions artifact. It uses optional `BRAVE_SEARCH_API_KEY` or `BING_SEARCH_API_KEY` repository secrets and does not edit, commit, or push `data/sites.json`, `docs/parser-backlog.md`, or inventory data.

## Data Files

- `data/sites.json` is the source registry. `enabled: true` means the source is eligible for scraping and rotation. `enabled: false` means backlog or disabled parser start.
- `data/listings.json` is generated scraper output. It includes metadata such as `generated_at`, `source_count`, `listing_count`, `scrape_mode`, `scraped_sources`, `preserved_sources`, optional rotation metadata, and the normalized `listings` array. Each listing includes `last_verified_at`, the last time that exact row was returned by a source scrape.
- `data/metbull_names.json` is the local Meteoritical Bulletin name cache used for canonical-name lookup. Refresh it manually with `PYTHONDONTWRITEBYTECODE=1 python3 scraper/update_metbull_cache.py`, or let the weekly MetBull cache workflow update it. Normal scrapes should not query MetBull live per listing.
- `source-discovery/` is a workflow artifact path, not committed source data. Treat its JSON and Markdown reports as candidate input for manual review only.
- External shared candidate-list links such as OneDrive documents are candidate input only, not inventory sources; do not add the shared-document URL itself to `data/sites.json`.
- `docs/parser-backlog.md` tracks candidate sources, parser starts, marketplace rules, and parser-build checklists.
- `docs/session-memory.md` summarizes current project context for future editing sessions.

Do not hand-edit `data/listings.json` except for rare emergency repair. Prefer fixing parser logic or source config and regenerating it.

## Source Enable Policy

Do not enable a source with the generic parser first. Before changing a source to `enabled: true`:

1. Inspect a small sample manually and understand index, detail, pagination, sold, and image patterns.
2. Add or update a site-specific parser.
3. Run a narrow local scrape for that source with `--preserve-existing`.
4. Confirm rows are individual sellable meteorite, tektite, or impactite specimens, not categories, books, articles, jewelry-only products, generic gift sets, fossils, minerals, contact pages, or archived/sold-only pages.
5. Confirm prices, weights, availability, source URLs, remote image URLs, and classifications are reasonable.
6. Run validation before enabling and after enabling.

Marketplace sources need stricter vetting. Prefer vetted storefront allowlists over broad marketplace search pages, and include only sellers with varied, credible meteorite inventory.

If a site blocks scraping or disallows it in its terms, remove or disable it in `data/sites.json`.

## No Local Media Copying

Do not download, copy, optimize, commit, or mirror seller images or product media into this repository. Keep only remote `image_url` and optional remote `image_urls` fallback values in generated listing data, and let the static UI load those remote images directly. This keeps the repo small and avoids republishing seller media.

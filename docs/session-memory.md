# Session Memory

Last updated: 2026-06-27

## Current State

- Project is a static meteorite inventory dashboard backed by a Python scraper.
- Frontend files are `index.html`, `styles.css`, and `app.js`; no JS build step is required.
- Scraper dependencies are in `scraper/requirements.txt`: `beautifulsoup4`, `requests`, and `lxml`.
- Generated listing data lives in `data/listings.json`; current generated data has 3,955 listings from 27 enabled sources after normalizing Meteor Center, Collecting Meteorites, BuyMeteorites.com, and JC Meteorite Collection rows.
- Source registry has 42 configured sources: 27 enabled and 15 disabled.
- User preference: after completing and validating changes in this repo, commit and push them unless there is a blocker, failed validation, secret exposure risk, or an explicit instruction not to publish.
- `data/listings.json` preserves source `price`, `currency`, and `price_per_g`, and now also carries USD-normalized `price_usd`, `price_per_g_usd`, `fx_rate_to_usd`, `fx_rate_date`, plus top-level `exchange_rates` metadata.
- Source registry lives in `data/sites.json`; parser backlog and marketplace rules live in `docs/parser-backlog.md`.
- `.venv/` is local and ignored. Python bytecode caches should be removed rather than committed.
- Source discovery automation is review-only and artifact-only. It must not auto-enable sources, scrape new inventory, or commit registry/backlog changes.

## Active Sources

- SV Meteorites uses `sv_meteorites` and parses public inventory/detail pages with individual specimen fields and category/non-listing rejection.
- Meteorlab uses `meteorlab` and parses old static catalog tables, captures specimen images, skips sold markers, and supports email-for-price rows.
- BAITYLIA uses `baitylia` and parses categorized inventory rows and follows them to detail pages while rejecting header/category rows.
- Meteorite Exchange uses `meteorite_exchange` and parses bounded WooCommerce product pages with product-detail proof, category/archive/add-to-cart/filter rejection, and non-specimen filtering.
- FossilEra uses `fossilera` and parses active-only meteorite cards and detail pages with pagination and sold-card suppression.
- Prehistoric Fossils Meteorites uses `prehistoric_fossils` and parses only the NWA meteorites WooCommerce category with product/cart or stock proof, exact weights/prices/images, and frame/gem-jar/display rejection.
- Galactic Stone & Ironworks uses `galactic_stone` and parses BigCommerce product grids with add-to-cart/detail proof, title weights, and non-specimen/out-of-stock rejection.
- The Meteorite Market uses `meteorite_market` and parses validated static sale pages with duplicate-cell cleanup and sold-price rejection.
- Arizona Skies Meteorites uses `arizona_skies` and parses only Lunar/Martian final specimen pages plus clean inexpensive rows with exact price, individual weight, valid image, and sold/non-specimen rejection.
- Aerolite Meteorites uses `aerolite` and parses narrow WooCommerce shop categories while excluding sold and non-specimen products; branded schema suffixes such as `| Aerolite Meteorites Incorporated` are stripped during normalization.
- Astro West uses `astro_west` and parses WooCommerce meteorite category pagination to `/products/` details with product/add-to-cart proof, meteorite title markers, and jewelry/display/gift-set rejection without rejecting the broad gifts category alone.
- IMPACTIKA uses `impactika` and parses Woo Store API description rows with smaller retried JSON requests, exact price/weight row validation, stock checks, lot/range/per-gram rejection, and product/URL-derived display names instead of AB inventory row codes.
- SkyFall Meteorites uses `skyfall_meteorites` and parses product sitemap entries under meteorites-for-sale paths with positive title weights/prices and path/title rejection rules.
- Meteolovers uses `meteolovers` and parses Elementor/Woo product cards under meteorite paths with schema/meta prices and sold/status checks.
- justMETEORITES uses `justmeteorites` and parses product-sitemap detail pages while excluding sold paths, non-specimen paths, and unavailable detail pages.
- Mini Museum Meteorites uses `mini_museum` and parses a narrow Shopify meteorite subset with product-type, gift/jewelry/card/collection, positive-price, and title-weight checks.
- Fossil Realm Meteorite Collection uses `fossil_realm` and parses Shopify meteorite products with available variants, positive non-placeholder prices, and title weights.
- TOP Meteorite uses `top_meteorite` and parses Shopify specimen products with available variants, positive prices, title weights, and meteorite keywords.
- Buy Meteorite uses `buy_meteorite` and parses only the Shopify meteorites collection with meteorite product type/tag checks, available variants, positive prices, title weights, images, and non-specimen rejection.
- BuyMeteorites.com uses `thompson_meteorites` and parses the public Thompson Meteorite Collection Woo Store API with in-stock/add-to-cart proof, API-currency positive prices, exact title weights, remote images, and service/discovery-set/non-specimen rejection.
- JC Meteorite Collection uses `jc_meteorite_collection` and parses paginated custom public catalogue API pages plus batched detail records with exact unit-bearing weights, positive USD prices, meteorite/classification evidence, remote images, and sold/fulgurite/thin-section/set/lot/range rejection.
- PolandMET uses `polandmet` and parses five bounded Woo Store API pages with in-stock/add-to-cart checks, title-derived individual weights, non-specimen rejection, image fallback candidates, and local MetBull-assisted display names.
- KD Meteorites uses `kd_meteorites` and parses bounded static sale hubs/detail pages with non-specimen/info-page rejection, exact price/weight/image requirements, and page/URL-derived clean titles.
- Meteorite Recon uses `meteorite_recon` and parses only the static Stones and Irons sale pages with row-scoped images, exact price/individual-weight requirements, and offer-price/category/non-specimen rejection.
- WWMeteorites uses `wwmeteorites` and parses bounded same-domain sale/detail pages with exact row price/weight requirements, sold/category/lot/range/non-specimen rejection, duplicate row suppression, and remote image URLs only.
- Meteor Center uses `meteor_center` and parses WooCommerce shop product cards across pagination, including `/page/2/`, with in-stock/add-to-cart proof, EUR prices, title weights, and non-specimen/range rejection without fetching every product detail page.
- Collecting Meteorites uses `collecting_meteorites` and parses the public meteorites-for-sale WordPress cards plus bounded detail pages for exact title weights, EUR prices, category text, remote images, and rejection for per-gram, non-specimen, unavailable, ambiguous multi-specimen, and non-positive-price rows.

## Disabled Sources

- Collector Secret Meteorites, broad eBay/Etsy marketplace search, Facebook Meteorite Groups, and IMCA Member List remain policy-blocked or reference-only disabled sources.
- Seven disabled eBay Browse API parser-start entries are present: `whitehouse_meteorites`, `topherspin`, `fobos13ali`, `yoda_meteorites`, `the.interstellar.collection`, `meteoritetreasure`, and `topmeteorite`.
- eBay entries are official Browse API only, seller-allowlist only, fixed-price only, and must remain disabled until API secrets are configured and rows are manually reviewed.
- Disabled backlog entries are present for Etsy SpaceTreasuresUS, Etsy SPACEMANGIFT, and Etsy saharagems. They use the no-op `disabled_backlog` parser until a real parser is built.
- Etsy SpaceTreasuresUS, SPACEMANGIFT, and saharagems were reassessed on 2026-06-17. Narrow public storefront fetches returned HTTP 403, so no safe/reliable public-HTML parser was added; future Etsy work should use official Etsy Open API credentials plus manual row-quality review before enablement.
- Disabled sources are visible in the UI source panel but are excluded from scraper runs and listing results. Source status counts are clickable and render grouped site cards for connected, parser-start, backlog, and policy/reference categories.
- Source card headings wrap long source names and status pills so disabled parser-start/backlog cards stay readable on narrow layouts.

## Current In-Progress Work

- Image resilience is implemented with optional remote `image_urls` fallback candidates while preserving `image_url` as the primary/backward-compatible field.
- Frontend image rendering tries fallback image URLs before showing `No image`.
- Validator structurally validates optional `image_urls` arrays.
- Scraper politeness is centralized through a per-host throttled request wrapper with jitter, transient-status retries, and `Retry-After` support.
- Normal inventory scrapes do not query the Meteoritical Bulletin live per row. MetBull support is cache-backed/local through `data/metbull_names.json` and `scraper/update_metbull_cache.py`.
- A conservative MetBull-assisted canonical-name layer adds `canonical_name`, `canonical_name_display`, `canonical_name_status`, and `canonical_name_source` fields only for Official MetBull matches; unresolved names remain `unknown` and group as `Other meteorite` in price charts.
- PolandMET and KD Meteorites parser work has passed targeted local scrape review and validation.
- eBay Browse API connector work is present but disabled/config-gated until API secrets and manual row review exist.
- Disqualified storefronts such as The Space Shop Meteorites and Galactic Stone eCrater Mirror are intentionally not configured because bounded review found souvenir/display/non-individual inventory rather than useful individual specimens.
- The user's long dealer list should be treated as candidate backlog/input, not as permission to scrape every site or broad marketplace results.
- Twice-daily source discovery work is implemented as a separate review-only workflow that uploads JSON/Markdown artifacts and leaves the hourly inventory scrape workflow unchanged.

## Active Todo List

- For future completed changes, run validation, commit, and push by default unless blocked or explicitly told not to.

## Recent Decisions

- README was expanded to be the canonical guide for setup, scraping, validation, workflow behavior, data files, parser policy, and no local media copying.
- A session memory file was added under `docs/` for future agents.
- Current active source registry now has 27 enabled sources after adding Meteor Center, Collecting Meteorites, BuyMeteorites.com, and JC Meteorite Collection.
- Saffordite is treated as an impactite marker so Meteorite Exchange impactite rows classify without suspicious-row noise.
- Scraper output now normalizes priced rows to USD using daily no-key FX rates when available, including EUR and CAD when the current source data needs them, falling back to saved exchange-rate metadata or USD-only metadata if offline.
- `.gitignore` now covers common Python, Node/static tooling, local environment, editor, OS, build, temp, and cache artifacts without ignoring source/data docs.
- `scraper/__pycache__/` was removed as a generated artifact.
- `.venv/` was intentionally left in place because it may be useful locally and is ignored.
- Parser normalization now preserves high-confidence subtype variants such as `C2-UNG`, `EH3/EH4`, `L/LL6`, Eucrite qualifiers, `Achondrite-ung`, and `IIIE-AN`; targeted source fixes cover FossilEra lunar Type labels, Arizona Skies Campocito/Campo del Cielo rows, justMETEORITES Vaca Muerta and Monturaqui, and Meteorite Exchange NWA 4799 EH-melt rock.
- GitHub Actions scrape failures from push runs were diagnosed as stale long-running scrape commits being rejected after `main` advanced; workflow was fixed to cancel stale runs and skip stale inventory commits.
- The next `Scrape meteorite inventory` workflow run after that fix succeeded and produced bot inventory commit `7b7e630`.
- For new source discovery, prioritize direct dealer sites with individual priced/weighted listings; add candidates one at a time with source-specific parsers and targeted validation.
- For eBay, use official Browse API only, seller allowlists only, fixed-price only for v1, and no broad marketplace search/category scraping.
- Be conservative with site traffic: per-host throttling, jitter, `Retry-After` handling, bounded source caps, and no high-volume live MetBull lookups during normal scraping.

## Parser Policy

- Do not enable a source with the generic parser first.
- Add or verify a site-specific parser before setting `enabled: true`.
- Emit individual sellable specimens only; reject category pages, books, articles, contact pages, broad collections, souvenir-only items, jewelry-only products, fossils, minerals, and sold-only/archive pages.
- Keep disabled parser starts disabled until row-quality verification passes across pagination and sold/out-of-stock behavior.
- Marketplace candidates need strict storefront vetting; avoid broad eBay/Etsy/category scraping. Etsy storefronts should be official Open API only if public storefront HTML is gated or anti-bot-protected.
- Respect source terms, robots expectations, login walls, CAPTCHAs, and anti-bot systems. Disable a source if scraping is not allowed.
- Do not hit sites hard during parser development. Use narrow `--site` runs, conservative page/product caps, and source-specific parsers that avoid unbounded crawling.
- If a site returns `429`, `403`, CAPTCHAs, login walls, or anti-bot responses, back off and disable or keep the source disabled rather than escalating scraping.

## Workflow And Rotation

- Workflow file is `.github/workflows/scrape-and-publish.yml`.
- Pushes to `main` and manual dispatch run a full scrape of enabled sources.
- Scheduled runs are hourly and use `--rotate --preserve-existing --rotation-key "${{ github.run_number }}"`.
- Rotation refreshes one enabled source per run and preserves existing rows for enabled sources not scraped in that run.
- The workflow validates generated data, commits `data/listings.json` changes, and pushes them.
- `data/listings.json` and `data/metbull_names.json` are ignored by scrape workflow path triggers to prevent immediate data-only commit loops.
- Workflow concurrency now cancels stale in-progress scrape runs, and commit steps verify that `HEAD` still matches fetched remote `main` before attempting to push generated data commits.
- Optional eBay Browse API workflow env vars are `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET`; the connector must remain disabled unless those are configured and row quality is reviewed.
- Local optional API credentials should live only in ignored `.env`/`.env.*` files or exported shell variables. `.env.example` is a placeholder-only template; never commit real credentials.
- Weekly MetBull cache workflow is `.github/workflows/update-metbull-cache.yml`; it runs Fridays at 07:17 UTC, refreshes `data/metbull_names.json`, normalizes existing listings against the refreshed cache, validates JSON/listings, and commits only changed generated data.
- Source discovery workflow is `.github/workflows/discover-sources.yml`; it runs twice daily at 06:37 and 18:37 UTC, uses optional Brave/Bing search API secrets, validates its report, uploads artifacts, and does not commit or push changes.

## UI Decisions

- UI fetches `data/listings.json` and `data/sites.json` with `cache: "no-store"`.
- Search includes title, source, category, subtype, classification text, and URL.
- Unavailable rows are hidden by default; the checkbox includes them.
- Client-side filtering defensively hides obvious non-individual/category rows and decorative image leftovers.
- Category chips now render in a MetBull-inspired order with friendly plural labels, and each category chip can expand an in-flow subtype control group.
- Expanded subtype groups are generated only from current `subtype` values in `data/listings.json`; `All <friendly category>` clears the subtype while keeping the top-level category, and blank subtypes are labeled `No subtype recorded`.
- `Tektites & impactites` includes concise helper copy because it contains related impact material and is not a formal meteorite category.
- Category/subtype control counts honor search, source, and unavailable filters, but intentionally ignore the currently selected category/subtype so sibling counts remain comparable.
- Price/g summaries are only shown after narrowing results or when all visible rows share a title.
- Price and price/g UI display, sorting, and summaries use USD-normalized fields only; non-USD source prices are preserved in listing data and exposed as concise price-cell title/aria metadata.
- Listings weighing at least 1000 g show USD price/kg alongside USD price/g in the price/g cell.
- Search-scoped price distribution charts group available priced rows by Official MetBull meteorite name only; rows that cannot be confidently reconciled to Official MetBull names group as `Other meteorite`.
- Source panel exposes enabled, disabled parser start, and disabled backlog states.
- Source status count cards render grouped source cards for connected, parser-start, backlog, and policy/reference categories; long names/status pills must wrap cleanly.
- Images are remote URLs only. Do not add local media copying or seller image mirroring.
- Image fallback keeps `image_url` primary and lets optional `image_urls` provide retry candidates before `No image` is shown.

## Validation Commands

Run from the repo root:

```sh
node --check app.js
PYTHONDONTWRITEBYTECODE=1 python3 scraper/validate_listings.py
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile scraper/scrape.py scraper/validate_listings.py scraper/update_metbull_cache.py
git diff --check
```

Useful local scrape commands:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scraper/scrape.py
PYTHONDONTWRITEBYTECODE=1 python3 scraper/scrape.py --rotate --preserve-existing --rotation-key 1
PYTHONDONTWRITEBYTECODE=1 python3 scraper/scrape.py --site "FossilEra" --preserve-existing
PYTHONDONTWRITEBYTECODE=1 python3 scraper/scrape.py --normalize-existing
PYTHONDONTWRITEBYTECODE=1 python3 scraper/update_metbull_cache.py
```

## Next Tasks

- Vet new candidate sources one by one with narrow local scrapes before enabling any additional source.
- Add lightweight parser tests or saved sample HTML before broadening source coverage.
- Review whether GitHub Pages should be documented or configured more explicitly for the hosting mode in use.
- Continue improving Meteorlab title/classification edge cases only from concrete validation findings.

## Warnings For Future Agents

- Do not delete source files or `data/listings.json` during cleanup.
- The user has asked to always commit and push completed validated changes in this repo. Still inspect status/diff/log first, stage only intended files, and stop on failed validation, secrets, destructive changes, or explicit instructions not to publish.
- Use `PYTHONDONTWRITEBYTECODE=1` for Python checks to avoid recreating `__pycache__/`.
- Use `apply_patch` for manual file edits.
- Do not add overbroad ignores such as `data/`, `*.json`, or `docs/`.
- Do not download or commit seller product images, screenshots, or media.

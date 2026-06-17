# Parser Backlog

Generated: 2026-06-16

This is the working queue of meteorite dealer sites to inspect and add with custom parsers. Do not enable a site with the generic parser first. For each site, crawl a small sample manually, identify index/detail/page patterns, then add a parser and only then enable it in `data/sites.json`.

## Already In System

| Site | Status | Parser notes |
| --- | --- | --- |
| SV Meteorites | Active | Category discovery; individual listings are `Meteorite.aspx?id=...`. Do not emit category pages. |
| Meteorlab / New England Meteoritical Services | Active | Old static catalog pages with multiple specimens per page. Parser now reads paired/grid tables by logical item columns, captures remote product images, skips sold markers, and supports email-for-price rows. |
| BAITYLIA / Meteorite and More | Active | Index pages contain item rows; detail pages are `Meteorite.aspx?id=...`. Header/category pages are not listings. |
| Meteorite Exchange | Active | WooCommerce category/detail parser follows only root `.html` product pages with product metadata and rejects category/archive/add-to-cart/filter links, jewelry, gifts, books, and non-specimen products. |
| FossilEra | Active | Active-only `meteorites-for-sale` category parser follows `/meteorites/...` detail pages, suppresses sold cards, and extracts schema/detail metadata. |
| Galactic Stone & Ironworks | Active | BigCommerce product-grid parser requires product IDs, add-to-cart/detail proof, title weights, and meteorite/class markers; rejects collections, jewelry, displays, memorabilia, micromounts without weights, and out-of-stock cards. |
| The Meteorite Market | Active | Static allowlist parser reads validated sale tables, dedupes repeated cells/images, and rejects sold prices. |
| Arizona Skies Meteorites | Active | Narrow static parser follows only Lunar/Martian final specimen pages and clean inexpensive rows; requires exact price, individual weight, valid image, and sold/non-specimen filtering. |
| Aerolite Meteorites | Active | Narrow WooCommerce shop-category parser excludes sold, jewelry, books, stands, equipment, and other non-specimen products. |
| IMPACTIKA | Active | Woo Store API parser uses smaller retried JSON pages and emits only available exact price/weight rows while rejecting sold, lot/range, from-to, per-gram, and non-specimen rows. |
| SkyFall Meteorites | Active | Product sitemap parser accepts only `/meteorites-for-sale/` product paths with positive title weights/prices and rejects NFS, zero-gram, read-more, jewelry, books, and category failures. |
| Meteolovers | Active | Elementor/Woo product-card parser follows meteorite paths, uses schema/meta prices, and checks sold/status/category coverage. |
| justMETEORITES | Active | Product sitemap parser rejects sold paths, knife-material/gift/non-specimen paths, and out-of-stock/sold detail pages. |
| Mini Museum Meteorites | Active | Shopify products parser emits only a narrow meteorite subset after product-type, gift/jewelry/card/collection, positive-price, and title-weight checks. |
| Fossil Realm Meteorite Collection | Active | Shopify products parser requires product_type Meteorites, available variants, positive non-placeholder prices, and title weights. |
| TOP Meteorite | Active | Shopify products parser requires product_type Specimen, available variants, positive prices, title weights, and meteorite keywords. |
| PolandMET | Active | Woo Store API parser uses five bounded product pages, in-stock/add-to-cart checks, title-derived individual weights, non-specimen rejection, image fallbacks, and local MetBull-assisted display names. |
| KD Meteorites | Active | Static sale-hub parser follows bounded same-domain specimen pages, rejects non-specimen/info pages, requires exact row price/weight/image evidence, and cleans old table titles from page/URL identity. |
| Meteorite Recon | Active | Static WordPress sale-page parser fetches only Stones and Irons pages, scopes rows to specimen sale sections, requires exact price and individual weight, keeps remote image URLs, and rejects offer-price/category/non-specimen rows. |
| WWMeteorites | Active | Static/Wix sale-page parser discovers bounded same-domain detail pages, requires exact row price and weight, rejects sold/category/lot/range/non-specimen rows, and keeps remote image URLs only. |

Scheduled GitHub Actions runs rotate across active enabled sources one source at a time and preserve existing rows for enabled sources not scraped in that run. Disabled parser starts and policy-blocked disabled sources below are excluded from rotation.

## Inspected / Parser Started But Disabled

These sources are present in `data/sites.json` with `enabled: false` and `stage: disabled_parser_start`. They are not scraped unless explicitly enabled after credential setup and manual row review.

| Site | Parser | Blocker / next step |
| --- | --- | --- |
| eBay - whitehouse_meteorites | `ebay_browse` | Official Browse API only. Needs `EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET` and manual row review before enabling. |
| eBay - topherspin | `ebay_browse` | Official Browse API only. Needs API credentials and manual filtering review for combo/gift-style rows. |
| eBay - fobos13ali | `ebay_browse` | Candidate from user-provided list. Needs storefront quality review before any enablement. |
| eBay - yoda_meteorites | `ebay_browse` | Candidate from user-provided list. Needs storefront quality review before any enablement. |
| eBay - the.interstellar.collection | `ebay_browse` | Candidate with possible dust/vial noise. Needs manual review confirming enough individual specimens. |
| Galactic Stone eCrater Mirror | `galactic_stone_ecrater` | Parser is implemented for the narrow eCrater Meteorites category, but keep disabled. Bounded review on 2026-06-17 found current rows are display kits, pendants/vials, collections, and other non-individual or weightless products, adding no safe useful inventory beyond active Galactic Stone direct. |
| eBay - meteoritetreasure | `ebay_browse` | Provisional seller allowlist from `/str/meteoritetreasure`. Needs API credential setup, seller verification, and manual row review before enabling. |
| eBay - Top Meteorite Store | `ebay_browse` | Provisional seller allowlist from `/str/topmeteorite`. Needs API credential setup, seller verification, and manual row review before enabling. |

## Disabled Backlog Entries In Registry

These are present in `data/sites.json` with `enabled: false`, `stage: disabled_backlog`, and parser `disabled_backlog`. They are visible in the source panel but are explicit no-ops until a real source-specific parser is built.

| Site | URL | Next step |
| --- | --- | --- |
| Etsy - SpaceTreasuresUS | https://www.etsy.com/shop/SpaceTreasuresUS | Assessed 2026-06-17: narrow public storefront fetch returned HTTP 403. Keep disabled; use official Etsy Open API credentials and manual row-quality review before any parser work. |
| Etsy - SPACEMANGIFT | https://www.etsy.com/shop/SPACEMANGIFT | Assessed 2026-06-17: narrow public storefront fetch returned HTTP 403. Keep disabled; use official Etsy Open API credentials and manual row-quality review before any parser work. |
| Etsy - saharagems | https://www.etsy.com/shop/saharagems | Assessed 2026-06-17: narrow public storefront fetch returned HTTP 403. Keep disabled; use official Etsy Open API credentials and manual row-quality review before any parser work. |

## High-Priority Candidates

| Priority | Site | URL | Why add | Likely parser style | First inspection notes |
| --- | --- | --- | --- | --- | --- |
| 10 | Galactic Stone eCrater mirror | https://galacticstone.ecrater.com/ | Older/mirror storefront for Galactic Stone. | eCrater product-grid parser exists but is disabled. | Current inventory does not pass quality gate; revisit only if the mirror later has individual exact price/weight specimens not covered by the direct source. |

## Medium-Priority Candidates

| Priority | Site | URL | Why add | Likely parser style | First inspection notes |
| --- | --- | --- | --- | --- | --- |
| - | None currently | - | Previously listed direct-storefront candidates are now active after parser validation. | - | Continue with marketplace storefront vetting below. |

## Policy-Blocked Disabled Sources

These are present in `data/sites.json` with `enabled: false` and `stage: disabled_policy_blocked`. They should not be treated as ordinary parser candidates unless the source model changes.

| Site | URL | Blocker |
| --- | --- | --- |
| Collector Secret Meteorites | https://www.collector-secret.com/minerals/meteorites | Broad eBay affiliate/aggregator feed rather than direct verified inventory. |
| The Space Shop Meteorites | https://thespaceshop.com/genuine-meteorite-3-grams/ | Generic souvenir/gift products rather than named individual specimen inventory. |
| eBay Marketplace Search | https://www.ebay.com/ | Broad marketplace search/category scraping is blocked; use official Browse API seller allowlists only. |
| Etsy Marketplace Search | https://www.etsy.com/ | Broad marketplace search/category scraping is blocked; use official Etsy Open API credentials with vetted storefront allowlists only. |
| Facebook Meteorite Groups | https://www.facebook.com/ | Login/community source; keep manual/research only. |
| IMCA Member List | https://imcax.com/ | Reference/vetting source, not inventory. |

## Marketplace Storefront Rules

Marketplace sellers on eBay, Etsy, eCrater, or similar platforms must pass a stricter inventory-quality screen before we add them. The goal is varied meteorite dealer inventory, not souvenir-only shops.

Include a marketplace storefront only if it appears to have most of these:

1. At least 20 active meteorite-related listings.
2. At least 5 distinct meteorite classes or families, such as ordinary chondrite, carbonaceous chondrite, achondrite/HED, iron, pallasite, lunar, Martian, tektite/impactite.
3. Multiple named/classified specimens, not just generic labels like `meteorite stone`, `space rock`, or `Campo del Cielo`.
4. Individual specimen weights and prices on most listings.
5. Some higher-information listings with NWA numbers, official names, classification, provenance, IMCA/GMA identity, or Meteoritical Bulletin references.
6. A meaningful share of actual specimens, slices, end cuts, individuals, or fragments rather than mostly pendants, dust vials, beads, framed gift sets, or souvenir displays.

Exclude or deprioritize storefronts when most inventory is:

1. Souvenir sets only.
2. Mostly Campo del Cielo, Aletai, Sikhote-Alin, Muonionalusta jewelry, or other basic/common material with little variety.
3. Mostly dust vials, tiny display cards, beads, charms, pendants, or generic gift products.
4. Unnamed or unclassified rocks with no credible classification details.
5. Mixed fossil/crystal/gift shops where meteorites are only a small novelty section.

## Marketplace Candidates To Vet Later

These are not enabled. They are candidates to inspect manually and score against the rules above.

| Priority | Storefront | Platform | URL | Why consider | Caution |
| --- | --- | --- | --- | --- | --- |
| M1 | whitehouse_meteorites | eBay | https://www.ebay.com/usr/whitehouse_meteorites | Search results show varied listings: aubrite, eucrite, lunar, Martian shergottite, CV3, irons, ordinary chondrites, Sikhote-Alin, impactite. | Now present as disabled official Browse API connector. Enable only after credentials and row review. |
| M2 | topherspin | eBay | https://www.ebay.com/usr/topherspin | Search results show pallasite, iron, eucrite, achondrite, Chelyabinsk, unclassified NWA, and IMCA references. | Now present as disabled official Browse API connector. Some combo/gift-style listings need filtering review. |
| M3 | meteoritetreasure | eBay Store | https://www.ebay.com/str/meteoritetreasure | Store categories include iron, stone, stony-iron, lunar, Martian; snippets show CV3, lunar, pallasite, Martian, Aletai. | Now present as disabled official Browse API connector with provisional seller `meteoritetreasure`; verify seller and row quality before enabling. |
| M4 | Top Meteorite eBay store | eBay | https://www.ebay.com/str/topmeteorite | Search snippets show lunar/Martian/Vestan sets, winonaite, pallasite, impact glass. | Now present as disabled official Browse API connector with provisional seller `topmeteorite`; watch for sets and verify rows before enabling. |
| M5 | SpaceTreasuresUS | Etsy | https://www.etsy.com/shop/SpaceTreasuresUS | Shop description claims iron, stony-iron, stone meteorites, impactites, and tektites by an official dealer. | Public storefront fetch returned HTTP 403 on 2026-06-17. Do not scrape HTML; use official Etsy Open API credentials and strong anti-souvenir filters only if promoted. |
| M6 | SPACEMANGIFT | Etsy | https://www.etsy.com/shop/SPACEMANGIFT | Categories show stone, iron, stony-iron, HED, lunar, Martian, tektites, impact craters. | Public storefront fetch returned HTTP 403 on 2026-06-17. Do not scrape HTML; use official Etsy Open API credentials and strict category/title filters only if promoted. |
| M7 | The Interstellar Collection | eBay | https://www.ebay.com/usr/the.interstellar.collection | Search shows IMCA/GMA identity, lunar/Martian material, and pallasite/museum-grade specimen mentions. | Now present as disabled official Browse API connector. Appears dust-vial heavy; enable only if review finds enough individual specimens. |
| M8 | saharagems | Etsy | https://www.etsy.com/shop/saharagems | Search shows pallasite and Martian meteorite listings with substantial weights/prices. | Public storefront fetch returned HTTP 403 on 2026-06-17. Do not scrape HTML; use official Etsy Open API credentials and gem/mineral noise filters only if promoted. |
| M9 | fobos13ali | eBay | https://www.ebay.com/usr/fobos13ali | Candidate seller from provided list. | Present as disabled official Browse API connector; needs manual storefront quality review. |
| M10 | yoda_meteorites | eBay | https://www.ebay.com/usr/yoda_meteorites | Candidate seller from provided list. | Present as disabled official Browse API connector; needs manual storefront quality review. |

## Later / Special Handling

| Site | URL | Notes |
| --- | --- | --- |
| eBay marketplace search/category pages | https://www.ebay.com/ | Do not scrape broad eBay search/category pages. Use official Browse API only, seller allowlists only, fixed-price only, credentials via secrets, active/sold separation, duplicate handling, and manual row review before enabling. |
| Etsy marketplace search/category pages | https://www.etsy.com/ | Do not scrape broad Etsy search/category pages. Public storefront HTML fetches returned HTTP 403 for current candidates, so Etsy access should be official Open API only with vetted storefront allowlists, credentials, and gift/souvenir filtering. |
| Facebook meteorite groups | https://www.facebook.com/ | Useful community sales source, but not practical for public scheduled scraping. Keep manual/research only. |
| IMCA member list | https://imcax.com/ | Useful for vetting sellers and finding dealer names, but IMCA itself does not sell meteorites. Treat as reference data, not inventory. |

## Parser Build Checklist

1. Identify inventory index URLs and pagination.
2. Identify detail/product URL pattern.
3. Separate categories, books, articles, contact pages, educational pages, souvenir-only pages, and generic gift-set pages from sellable specimen listings.
4. Extract title, classification/type, specimen weight, price, currency, image, availability, and source URL.
5. Add parser-specific tests or saved sample HTML before enabling broad crawling.
6. Enable in `data/sites.json` only after the parser returns individual specimens, not collections or category pages.
7. For marketplaces, enable only vetted storefronts that pass the varied-inventory rules above.

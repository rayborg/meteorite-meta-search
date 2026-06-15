# Parser Backlog

Generated: 2026-06-15

This is the working queue of meteorite dealer sites to inspect and add with custom parsers. Do not enable a site with the generic parser first. For each site, crawl a small sample manually, identify index/detail/page patterns, then add a parser and only then enable it in `data/sites.json`.

## Already In System

| Site | Status | Parser notes |
| --- | --- | --- |
| SV Meteorites | Active | Category discovery; individual listings are `Meteorite.aspx?id=...`. Do not emit category pages. |
| Meteorlab / New England Meteoritical Services | Active | Old static catalog pages with multiple specimens per page. Parser now reads paired/grid tables by logical item columns, captures remote product images, skips sold markers, and supports email-for-price rows. |
| BAITYLIA / Meteorite and More | Active | Index pages contain item rows; detail pages are `Meteorite.aspx?id=...`. Header/category pages are not listings. |
| FossilEra | Active | Active-only `meteorites-for-sale` category parser follows `/meteorites/...` detail pages, suppresses sold cards, and extracts schema/detail metadata. |
| Aerolite Meteorites | Active | Narrow WooCommerce shop-category parser excludes sold, jewelry, books, stands, equipment, and other non-specimen products. |
| Meteolovers | Active | Elementor/Woo product-card parser follows meteorite paths, uses schema/meta prices, and checks sold/status/category coverage. |
| The Meteorite Market | Active | Static allowlist parser reads validated sale tables, dedupes repeated cells/images, and rejects sold prices. |

Scheduled GitHub Actions runs rotate across active enabled sources one source at a time and preserve existing rows for enabled sources not scraped in that run. Disabled parser starts below are excluded from rotation until `enabled` is changed to `true` after local verification.

## Inspected / Parser Started But Disabled

These entries are present in `data/sites.json` with `enabled: false`. They are not part of scheduled output until local verification shows good individual rows and filtering policies are safe.

| Site | Parser status | Inspection findings | Why disabled |
| --- | --- | --- | --- |
| Meteorite Exchange | `meteorite_exchange` parser start added | WooCommerce/WordPress pages. Category examples include `new-arrivals.html` and `moon-meteorites.html`; product links are `.html`; page has WooCommerce feeds and product/card markup mixed with add-to-cart affordances. | Needs local category-card verification across multiple categories and strict exclusion of add-to-cart/filter/category links before enabling. |
| Galactic Stone & Ironworks | `galactic_stone` parser start added | BigCommerce category at `/meteorites/` has `article.card` product grid, product data attributes, remote CDN images, prices, and `rel=next` pagination. Cards include Add to Cart and Out of stock controls. | Disabled because the category mixes micromounts, collections, jewelry, memorabilia, and out-of-stock items; needs product-type policy before active output. |
| Arizona Skies Meteorites | `arizona_skies` parser start added | Home page is highly mixed: meteorites, fossils, jewelry, watches, military collectibles, art, and price-bucket links. Meteorite pages include lunar/Martian/category examples. | Disabled; requires narrow allowlist and crawl-delay policy. Do not broad-crawl this site. |

## High-Priority Candidates

| Priority | Site | URL | Why add | Likely parser style | First inspection notes |
| --- | --- | --- | --- | --- | --- |
| 1 | Meteorite Exchange | https://www.meteorites-for-sale.com/ | Specialist meteorite store active since 1996; broad categories including lunar, Martian, tektites, impactites, jewelry. | Category pages plus product/detail pages. | Search shows category pages such as lunar price ranges. Crawl category links, then product cards/details. |
| 2 | Galactic Stone & Ironworks | https://galactic-stone.com/ | Specialist shop with meteorite categories including lunar, Martian, NWA, USA finds/falls, tektites. | Modern ecommerce category pages with product cards. | Search snippet shows add-to-cart/quick-view cards; parse category collections first. |
| 3 | IMPACTIKA | https://impactika.com/ | Long-running specialist source for rare, historical meteorites; sells online and at shows. | Old/static site parser. | Likely hand-built pages; inspect navigation and any inventory pages before enabling. |
| 4 | SkyFall Meteorites | https://skyfallmeteorites.com/ | Specialist meteorite seller and buyer; authenticity guarantee; likely inventory pages. | WordPress/WooCommerce or custom shop parser. | Separate buy/sell resource pages from product listings. |
| 5 | Arizona Skies Meteorites | https://www.arizonaskiesmeteorites.com/ | Meteorites plus fossils; has price-bucket category links under $100 and under $250. | Category pages plus product/listing pages. | Must filter fossils/minerals and only parse meteorite sections. |

## Medium-Priority Candidates

| Priority | Site | URL | Why add | Likely parser style | First inspection notes |
| --- | --- | --- | --- | --- | --- |
| 6 | justMETEORITES | https://justmeteorites.com/ | Authentic meteorites and impactites; visible sections for Vaca Muerta, Imilac, Monturaqui, chondrites. | Category/collection parser. | Need distinguish repeated SEO/category text from actual product cards. |
| 7 | Mini Museum Meteorites | https://shop.minimuseum.com/collections/meteorites | Retail meteorite collection with priced products. | Shopify collection/product parser. | Lower scientific depth, but easy parser and useful price baseline. |
| 8 | Fossil Realm Meteorite Collection | https://www.fossilrealm.com/collections/meteorite-collection | High-end meteorite/mineral collection with specimen details and provenance. | Shopify collection/product parser. | Likely few high-value listings; parse full detail pages. |
| 9 | TOP Meteorite | https://topmeteorite.com/ | Featured dealer on meteorite.com; rare/significant meteorites and jewelry. | Needs verification, then shop/detail parser. | Confirm active URL and inventory structure before adding. |
| 10 | Galactic Stone eCrater mirror | https://galacticstone.ecrater.com/ | Older/mirror storefront for Galactic Stone; may expose cleaner product pages. | eCrater product-grid parser. | Use only if main site is hard to parse or incomplete. |

## Policy-Blocked Disabled Sources

These are present in `data/sites.json` with `enabled: false` and `stage: disabled_policy_blocked`. They should not be treated as ordinary parser candidates unless the source model changes.

| Site | URL | Blocker |
| --- | --- | --- |
| Collector Secret Meteorites | https://www.collector-secret.com/minerals/meteorites | Broad eBay affiliate/aggregator feed rather than direct verified inventory. |
| The Space Shop Meteorites | https://thespaceshop.com/genuine-meteorite-3-grams/ | Generic souvenir/gift products rather than named individual specimen inventory. |

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
| M1 | whitehouse_meteorites | eBay | https://www.ebay.com/usr/whitehouse_meteorites | Search results show varied listings: aubrite, eucrite, lunar, Martian shergottite, CV3, irons, ordinary chondrites, Sikhote-Alin, impactite. | Needs seller-page parser and active/sold filtering. |
| M2 | topherspin | eBay | https://www.ebay.com/usr/topherspin | Search results show pallasite, iron, eucrite, achondrite, Chelyabinsk, unclassified NWA, and IMCA references. | Some combo/gift-style listings; filter to individual specimens. |
| M3 | meteoritetreasure | eBay Store | https://www.ebay.com/str/meteoritetreasure | Store categories include iron, stone, stony-iron, lunar, Martian; snippets show CV3, lunar, pallasite, Martian, Aletai. | Verify authenticity detail depth and avoid jewelry-heavy rows. |
| M4 | Top Meteorite eBay store | eBay | https://www.ebay.com/str/topmeteorite | Search snippets show lunar/Martian/Vestan sets, winonaite, pallasite, impact glass. | Watch for sets; include only individual named specimens where possible. |
| M5 | SpaceTreasuresUS | Etsy | https://www.etsy.com/shop/SpaceTreasuresUS | Shop description claims iron, stony-iron, stone meteorites, impactites, and tektites by an official dealer. | Etsy pages need strong anti-souvenir filters. |
| M6 | SPACEMANGIFT | Etsy | https://www.etsy.com/shop/SPACEMANGIFT | Categories show stone, iron, stony-iron, HED, lunar, Martian, tektites, impact craters. | Also has souvenirs and jewelry; parser must filter categories/listing titles. |
| M7 | The Interstellar Collection | eBay | https://www.ebay.com/usr/the.interstellar.collection | Search shows IMCA/GMA identity, lunar/Martian material, and pallasite/museum-grade specimen mentions. | Appears dust-vial heavy in snippets; add only if full inventory has enough individual specimens. |
| M8 | saharagems | Etsy | https://www.etsy.com/shop/saharagems | Search shows pallasite and Martian meteorite listings with substantial weights/prices. | May be narrow or gem/mineral-heavy; include only if meteorite variety is broad enough. |

## Later / Special Handling

| Site | URL | Notes |
| --- | --- | --- |
| eBay marketplace search/category pages | https://www.ebay.com/ | Do not scrape broad eBay search/category pages first. Prefer vetted storefront allowlists. Needs seller filters, active/sold separation, duplicate handling, and stronger authenticity checks. |
| Etsy marketplace search/category pages | https://www.etsy.com/ | Do not scrape broad Etsy search/category pages first. Prefer vetted storefront allowlists and exclude gift/souvenir-heavy shops. |
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

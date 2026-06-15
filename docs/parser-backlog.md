# Parser Backlog

Generated: 2026-06-15

This is the working queue of meteorite dealer sites to inspect and add with custom parsers. Do not enable a site with the generic parser first. For each site, crawl a small sample manually, identify index/detail/page patterns, then add a parser and only then enable it in `data/sites.json`.

## Already In System

| Site | Status | Parser notes |
| --- | --- | --- |
| SV Meteorites | Active | Category discovery; individual listings are `Meteorite.aspx?id=...`. Do not emit category pages. |
| BAITYLIA / Meteorite and More | Active | Index pages contain item rows; detail pages are `Meteorite.aspx?id=...`. Header/category pages are not listings. |
| Meteorlab / New England Meteoritical Services | Active | Old static catalog pages with multiple specimens per page. Parser extracts item clusters from known offering pages. |

## High-Priority Candidates

| Priority | Site | URL | Why add | Likely parser style | First inspection notes |
| --- | --- | --- | --- | --- | --- |
| 1 | Meteorite Exchange | https://www.meteorites-for-sale.com/ | Specialist meteorite store active since 1996; broad categories including lunar, Martian, tektites, impactites, jewelry. | Category pages plus product/detail pages. | Search shows category pages such as lunar price ranges. Crawl category links, then product cards/details. |
| 2 | Aerolite Meteorites | https://aerolite.org/ | Large specialist dealer with authentic meteorites, lunar, Martian, high-end specimens, bulk meteorites, jewelry. | WordPress/WooCommerce-style product-category pages and product pages. | Product categories appear under `/product-category/...`; likely standard product cards. |
| 3 | Galactic Stone & Ironworks | https://galactic-stone.com/ | Specialist shop with meteorite categories including lunar, Martian, NWA, USA finds/falls, tektites. | Modern ecommerce category pages with product cards. | Search snippet shows add-to-cart/quick-view cards; parse category collections first. |
| 4 | IMPACTIKA | https://impactika.com/ | Long-running specialist source for rare, historical meteorites; sells online and at shows. | Old/static site parser. | Likely hand-built pages; inspect navigation and any inventory pages before enabling. |
| 5 | FossilEra Meteorites | https://www.fossilera.com/meteorites-for-sale | Large inventory and clear meteorite category page; likely many priced items. | Modern ecommerce category pagination plus product pages. | Good candidate for robust product card extraction. |
| 6 | SkyFall Meteorites | https://skyfallmeteorites.com/ | Specialist meteorite seller and buyer; authenticity guarantee; likely inventory pages. | WordPress/WooCommerce or custom shop parser. | Separate buy/sell resource pages from product listings. |
| 7 | The Meteorite Market | https://www.meteoritemarket.com/ | Very old meteorite sales site, online since 1995; historically useful catalog. | Old/static table/page parser. | Expect static HTML and mixed educational/sales pages; needs careful page allowlist. |
| 8 | Arizona Skies Meteorites | https://www.arizonaskiesmeteorites.com/ | Meteorites plus fossils; has price-bucket category links under $100 and under $250. | Category pages plus product/listing pages. | Must filter fossils/minerals and only parse meteorite sections. |

## Medium-Priority Candidates

| Priority | Site | URL | Why add | Likely parser style | First inspection notes |
| --- | --- | --- | --- | --- | --- |
| 9 | Meteolovers | https://meteolovers.com/ | IMCA-certified shop for meteorites, tektites, and related collectibles. | Shop category/product parser. | Likely clean ecommerce. Confirm product markup and pagination. |
| 10 | justMETEORITES | https://justmeteorites.com/ | Authentic meteorites and impactites; visible sections for Vaca Muerta, Imilac, Monturaqui, chondrites. | Category/collection parser. | Need distinguish repeated SEO/category text from actual product cards. |
| 11 | Collector Secret Meteorites | https://www.collector-secret.com/minerals/meteorites | Meteorites for collectors; says new meteorites listed often. | Ecommerce product-grid parser. | Multi-mineral marketplace; filter to meteorite collection only. |
| 12 | Mini Museum Meteorites | https://shop.minimuseum.com/collections/meteorites | Retail meteorite collection with priced products. | Shopify collection/product parser. | Lower scientific depth, but easy parser and useful price baseline. |
| 13 | Fossil Realm Meteorite Collection | https://www.fossilrealm.com/collections/meteorite-collection | High-end meteorite/mineral collection with specimen details and provenance. | Shopify collection/product parser. | Likely few high-value listings; parse full detail pages. |
| 14 | TOP Meteorite | https://topmeteorite.com/ | Featured dealer on meteorite.com; rare/significant meteorites and jewelry. | Needs verification, then shop/detail parser. | Confirm active URL and inventory structure before adding. |
| 15 | Galactic Stone eCrater mirror | https://galacticstone.ecrater.com/ | Older/mirror storefront for Galactic Stone; may expose cleaner product pages. | eCrater product-grid parser. | Use only if main site is hard to parse or incomplete. |
| 16 | The Space Shop meteorites | https://thespaceshop.com/genuine-meteorite-3-grams/ | Retail meteorite products. | Product page parser only. | Low priority because many items may be generic lots, not individual named specimens. |

## Later / Special Handling

| Site | URL | Notes |
| --- | --- | --- |
| eBay meteorite sellers | https://www.ebay.com/ | Needs marketplace-specific logic, seller filters, sold/active separation, duplicate handling, and stronger authenticity checks. Do not mix with private dealer parsers yet. |
| Facebook meteorite groups | https://www.facebook.com/ | Useful community sales source, but not practical for public scheduled scraping. Keep manual/research only. |
| IMCA member list | https://imcax.com/ | Useful for vetting sellers and finding dealer names, but IMCA itself does not sell meteorites. Treat as reference data, not inventory. |

## Parser Build Checklist

1. Identify inventory index URLs and pagination.
2. Identify detail/product URL pattern.
3. Separate categories, books, articles, contact pages, and educational pages from sellable listings.
4. Extract title, classification/type, specimen weight, price, currency, image, availability, and source URL.
5. Add parser-specific tests or saved sample HTML before enabling broad crawling.
6. Enable in `data/sites.json` only after the parser returns individual specimens, not collections or category pages.

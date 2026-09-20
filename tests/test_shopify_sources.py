import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scraper"))

import scrape  # noqa: E402
import validate_listings  # noqa: E402


def product(
    title="NWA 12345 Lunar Meteorite Individual, 4.25g",
    *,
    product_id=1,
    product_type="Meteorite > Lunar",
    price="85.00",
    available=True,
    images=True,
    tags=None,
    grams=999999,
    handle=None,
    body_html="<p>Authenticated specimen.</p>",
    variants=None,
):
    return {
        "id": product_id,
        "handle": handle or f"specimen-{product_id}",
        "title": title,
        "product_type": product_type,
        "body_html": body_html,
        "tags": tags or [],
        "images": [{"src": f"https://cdn.example.com/{product_id}.jpg"}] if images else [],
        "variants": variants
        if variants is not None
        else [{"id": product_id * 10, "title": "Default Title", "price": price, "available": available, "grams": grams}],
    }


def site(parser, *, currency="USD", inventory_urls=None):
    return {
        "name": parser,
        "parser": parser,
        "base_url": "https://example.com/",
        "currency": currency,
        "inventory_urls": inventory_urls or ["/collections/specimens/products.json?limit=250&country=US"],
    }


class ShopifySourceTests(unittest.TestCase):
    SOURCE_FILTERS = [
        ("treasure_coast_meteorites", scrape.treasure_coast_meteorites_filter),
        ("outerspacer", scrape.outerspacer_filter),
    ]

    def test_pagination_preserves_arbitrary_query_parameters(self):
        url = scrape.shopify_products_api_url(
            site("fossil_realm"),
            "/collections/all/products.json?limit=17&country=US&view=public&flag=a&flag=b",
            3,
            50,
        )
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["country"], ["US"])
        self.assertEqual(query["view"], ["public"])
        self.assertEqual(query["flag"], ["a", "b"])
        self.assertEqual(query["limit"], ["50"])
        self.assertEqual(query["page"], ["3"])

    def test_configured_currency_is_used_and_existing_sources_default_to_usd(self):
        fixture = product()
        eur_item = scrape.shopify_listing(site("fossil_realm", currency="EUR"), "fossil_realm", fixture, scrape.SourceLog(site("fossil_realm")), lambda *args: None)
        usd_item = scrape.shopify_listing(site("fossil_realm", currency=None), "fossil_realm", fixture, scrape.SourceLog(site("fossil_realm")), lambda *args: None)
        self.assertEqual(eur_item["currency"], "EUR")
        self.assertEqual(usd_item["currency"], "USD")

    def test_new_sources_require_explicit_usd_configuration(self):
        with self.assertRaises(ValueError):
            scrape.scrape_treasure_coast_meteorites(site("treasure_coast_meteorites", currency=None), scrape.SourceLog(site("treasure_coast_meteorites")))
        with self.assertRaises(ValueError):
            scrape.scrape_outerspacer(site("outerspacer", currency="EUR"), scrape.SourceLog(site("outerspacer")))

    def test_strict_sources_accept_exact_title_weight_and_ignore_shipping_grams(self):
        fixture = product(grams=999999)
        for parser, source_filter in self.SOURCE_FILTERS:
            with self.subTest(parser=parser):
                item = scrape.shopify_listing(site(parser), parser, fixture, scrape.SourceLog(site(parser)), source_filter)
                self.assertEqual(item["weight_g"], 4.25)
                self.assertEqual(item["currency"], "USD")
                self.assertNotIn("4.25g", item["title"])

    def test_compact_weight_ranges_are_rejected_and_validator_stays_aligned(self):
        ranges = ["2-5g", "2 - 5g", "2–5g", "2—5g", "2 to 5g", "2g-5g", "2g to 5g", "2.25-5.75g"]
        for value in ranges:
            title = f"NWA 12345 Lunar Meteorite {value}"
            self.assertIsNotNone(scrape.WEIGHT_RANGE_RE.search(title), value)
            self.assertIsNotNone(validate_listings.TITLE_WEIGHT_RANGE_RE.search(title), value)
            errors = validate_listings.validation_errors(
                {"title": title, "available": True, "parser": "outerspacer", "url": ""},
                1,
                {None},
                {"outerspacer"},
            )
            self.assertTrue(any("active title has variable weight range" in error for error in errors), value)
            for parser, source_filter in self.SOURCE_FILTERS:
                with self.subTest(value=value, parser=parser):
                    item = scrape.shopify_listing(
                        site(parser),
                        parser,
                        product(title=title),
                        scrape.SourceLog(site(parser)),
                        source_filter,
                    )
                    self.assertIsNone(item)

    def test_catalog_identity_separator_is_not_a_weight_range(self):
        titles = [
            "NWA 12345 - 4.25g",
            "Northwest Africa 12345 - 4.25g",
            "Dhofar 1234 - 4.25g",
            "Jiddat al Harasis 123 - 4.25g",
            "JAH 123 - 4.25g",
            "DaG 123 - 4.25g",
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertFalse(scrape.has_weight_range(title))
                self.assertEqual(scrape.first_weight_g(title), 4.25)
                self.assertFalse(validate_listings.has_title_weight_range(title))
                self.assertEqual(validate_listings.title_weight_g(title), 4.25)

                errors = validate_listings.validation_errors(
                    {"title": title, "available": True, "parser": "outerspacer", "url": ""},
                    1,
                    {None},
                    {"outerspacer"},
                )
                self.assertFalse(any("active title has variable weight range" in error for error in errors))
                for parser, source_filter in self.SOURCE_FILTERS:
                    item = scrape.shopify_listing(
                        site(parser),
                        parser,
                        product(title=title),
                        scrape.SourceLog(site(parser)),
                        source_filter,
                    )
                    self.assertEqual(item["weight_g"], 4.25)

    def test_generic_numeric_separator_remains_a_weight_range(self):
        title = "Meteorite specimen 123 - 4.25g"
        self.assertTrue(scrape.has_weight_range(title))
        self.assertIsNone(scrape.first_weight_g(title))
        self.assertTrue(validate_listings.has_title_weight_range(title))
        self.assertIsNone(validate_listings.title_weight_g(title))
        for parser, source_filter in self.SOURCE_FILTERS:
            with self.subTest(parser=parser):
                item = scrape.shopify_listing(
                    site(parser),
                    parser,
                    product(title=title),
                    scrape.SourceLog(site(parser)),
                    source_filter,
                )
                self.assertIsNone(item)

    def test_official_identity_overlap_ranges_are_rejected_by_all_shopify_filters(self):
        titles = [
            "Dhofar 123 - 4.25g-5g",
            "Dhofar 123 - 4.25g to 5g",
            "JAH 123 - 4.25g–5g",
            "Jiddat al Harasis 123 - 4.25g—5g",
        ]
        established = [
            ("fossil_realm", scrape.fossil_realm_filter, {"product_type": "Meteorites"}),
            ("top_meteorite", scrape.top_meteorite_filter, {"product_type": "Specimen", "body_html": "<p>Meteorite specimen.</p>"}),
            ("buy_meteorite", scrape.buy_meteorite_filter, {"product_type": "Meteorite", "tags": ["Meteorite"]}),
            ("mini_museum", scrape.mini_museum_filter, {"product_type": "Meteorite"}),
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertTrue(scrape.has_weight_range(title))
                self.assertIsNone(scrape.first_weight_g(title))
                self.assertTrue(validate_listings.has_title_weight_range(title))
                self.assertIsNone(validate_listings.title_weight_g(title))

                for parser, source_filter in self.SOURCE_FILTERS:
                    item = scrape.shopify_listing(
                        site(parser),
                        parser,
                        product(title=title),
                        scrape.SourceLog(site(parser)),
                        source_filter,
                    )
                    self.assertIsNone(item)

                for parser, source_filter, fixture_options in established:
                    item = scrape.shopify_listing(
                        site(parser),
                        parser,
                        product(title=title, **fixture_options),
                        scrape.SourceLog(site(parser)),
                        source_filter,
                    )
                    self.assertIsNone(item)

    def test_body_and_product_type_offer_evidence_is_rejected(self):
        cases = [
            product(body_html="<p>This listing is for a lot of three meteorite pieces.</p>"),
            product(body_html="<p>The purchase includes three meteorite fragments.</p>"),
            product(body_html="<p>You will receive 3 assorted stones from this meteorite.</p>"),
            product(body_html="<p>One of several sizes; select an option before purchase.</p>"),
            product(body_html="<p>Bundle of three meteorite fragments.</p>"),
            product(body_html="<p>Choose your weight from multiple sizes.</p>"),
            product(body_html="<p>This material is priced per gram.</p>"),
            product(body_html="<p>Available specimen weight range: 2-5g.</p>"),
            product(product_type="Meteorite Bundle"),
            product(product_type="Meteorite > Selectable Weights"),
            product(product_type="Meteorite Offer 2-5g"),
        ]
        for parser, source_filter in self.SOURCE_FILTERS:
            for position, fixture in enumerate(cases):
                with self.subTest(parser=parser, position=position):
                    item = scrape.shopify_listing(site(parser), parser, fixture, scrape.SourceLog(site(parser)), source_filter)
                    self.assertIsNone(item)

    def test_benign_singular_specimen_prose_remains_eligible(self):
        fixture = product(
            body_html=(
                "<p>This individual specimen is from a recovery with multiple specimens "
                "and has a lot of fusion crust.</p>"
            )
        )
        for parser, source_filter in self.SOURCE_FILTERS:
            with self.subTest(parser=parser):
                item = scrape.shopify_listing(site(parser), parser, fixture, scrape.SourceLog(site(parser)), source_filter)
                self.assertIsNotNone(item)

    def test_invalid_shopify_handles_are_rejected_before_url_construction(self):
        invalid_handles = [
            None,
            "",
            "None",
            "null",
            "undefined",
            "../escape",
            "nested/path",
            "//evil.example/item",
            "https://evil.example/item",
            "slug?x=1",
            "slug#part",
            "bad slug",
        ]
        for parser, source_filter in self.SOURCE_FILTERS:
            for handle in invalid_handles:
                fixture = product()
                if handle is None:
                    fixture.pop("handle")
                else:
                    fixture["handle"] = handle
                log = scrape.SourceLog(site(parser))
                with self.subTest(parser=parser, handle=handle):
                    item = scrape.shopify_listing(site(parser), parser, fixture, log, source_filter)
                    self.assertIsNone(item)
                    self.assertEqual(log.rejected["shopify_invalid_handle"], 1)

        valid = product(handle="nwa-12345-lunar-specimen-4-25g")
        item = scrape.shopify_listing(
            site("outerspacer"),
            "outerspacer",
            valid,
            scrape.SourceLog(site("outerspacer")),
            scrape.outerspacer_filter,
        )
        self.assertEqual(item["url"], "https://example.com/products/nwa-12345-lunar-specimen-4-25g")

    def test_only_new_source_requests_use_agent_user_agent(self):
        for parser, _source_filter in self.SOURCE_FILTERS:
            with self.subTest(parser=parser):
                self.assertIn("Agent/MeteoriteMetaSearchBot/0.3", scrape.shopify_json_headers(site(parser))["User-Agent"])
        for parser in ["fossil_realm", "top_meteorite", "buy_meteorite", "mini_museum"]:
            with self.subTest(parser=parser):
                self.assertEqual(scrape.shopify_json_headers(site(parser))["User-Agent"], scrape.BROWSER_UA)

    def test_strict_sources_reject_unsafe_products(self):
        cases = [
            product(available=False),
            product(price="0.00"),
            product(price="1000000.00"),
            product(title="NWA 12345 Lunar Meteorite Select Size"),
            product(title="NWA 12345 Lunar Meteorite 2g to 5g"),
            product(title="NWA 12345 Lunar Meteorite Dust, 4.25g"),
            product(title="NWA 12345 Lunar Meteorite Display, 4.25g"),
            product(title="NWA 12345 Lunar Meteorite Set, 4.25g"),
            product(title="NWA 12345 Lunar Meteorite Lot, 4.25g"),
            product(title="NWA 12345 Lunar Meteorite Fragments, 4.25g"),
            product(title="NWA 12345 Lunar Meteorite, 4.25g, $20 per gram"),
            product(handle="nwa-12345-gembox-display-case-4-25g"),
            product(images=False),
            product(product_type="Gift Card"),
            product(title="Obsidian Individual, 4.25g", product_type="Obsidian"),
            product(
                variants=[
                    {"id": 1, "title": "4.25g", "price": "10.00", "available": True, "grams": 4},
                    {"id": 2, "title": "5.25g", "price": "12.00", "available": True, "grams": 5},
                ]
            ),
        ]
        for parser, source_filter in self.SOURCE_FILTERS:
            for position, fixture in enumerate(cases):
                with self.subTest(parser=parser, position=position):
                    item = scrape.shopify_listing(site(parser), parser, fixture, scrape.SourceLog(site(parser)), source_filter)
                    self.assertIsNone(item)

    def test_outerspacer_seo_tags_do_not_affect_classification(self):
        fixture = product(
            title="Aletai Iron Meteorite Individual, 4.25g",
            product_type="Iron, IIIE-an",
            tags=["Lunar Meteorite", "Martian Shergottite", "Meteorite Type-Lunar", "SEO Bestseller"],
        )
        item = scrape.shopify_listing(site("outerspacer"), "outerspacer", fixture, scrape.SourceLog(site("outerspacer")), scrape.outerspacer_filter)
        self.assertEqual(item["title"], "Aletai")
        self.assertEqual(item["meteorite_type"], "iron")
        self.assertNotIn("Lunar", item.get("classification_text") or "")
        self.assertNotIn("Martian", item.get("classification_text") or "")

    @patch.object(scrape.time, "sleep", return_value=None)
    @patch.object(scrape, "fetch_shopify_json_page")
    def test_collection_products_are_deduplicated(self, fetch_page, _sleep):
        fixture = product()
        fetch_page.side_effect = [
            {"products": [fixture]},
            {"products": [fixture]},
        ]
        source = site(
            "outerspacer",
            inventory_urls=[
                "/collections/stony-meteorites/products.json?limit=250&country=US",
                "/collections/iron-meteorites/products.json?limit=250&country=US",
            ],
        )
        rows = scrape.scrape_outerspacer(source, scrape.SourceLog(source))
        self.assertEqual(len(rows), 1)
        for call in fetch_page.call_args_list:
            self.assertIn("Agent/MeteoriteMetaSearchBot/0.3", call.args[3]["User-Agent"])

    def test_outerspacer_rejects_non_approved_collection(self):
        source = site("outerspacer", inventory_urls=["/products.json?limit=250&country=US"])
        with self.assertRaises(ValueError):
            scrape.scrape_outerspacer(source, scrape.SourceLog(source))

    @patch.object(scrape, "scrape_treasure_coast_meteorites", return_value=[{"parser": "treasure_coast_meteorites"}])
    def test_treasure_coast_dispatch(self, scraper):
        source = site("treasure_coast_meteorites")
        self.assertEqual(scrape.scrape_site(source, scrape.SourceLog(source))[0]["parser"], "treasure_coast_meteorites")
        scraper.assert_called_once()

    @patch.object(scrape, "scrape_outerspacer", return_value=[{"parser": "outerspacer"}])
    def test_outerspacer_dispatch(self, scraper):
        source = site("outerspacer")
        self.assertEqual(scrape.scrape_site(source, scrape.SourceLog(source))[0]["parser"], "outerspacer")
        scraper.assert_called_once()

    def test_validator_enforces_source_specific_shopify_invariants(self):
        fixture = {
            "parser": "outerspacer",
            "source_url": "https://outerspacer.com/",
            "currency": "EUR",
            "available": True,
            "price": None,
            "weight_g": None,
            "image_url": None,
            "url": "https://outerspacer.com/collections/stony-meteorites",
        }
        errors = validate_listings.validation_errors(fixture, 1, {None}, {"outerspacer"})
        self.assertTrue(any("not USD" in error for error in errors))
        self.assertTrue(any("lacks exact price/weight" in error for error in errors))
        self.assertTrue(any("lacks a specimen image" in error for error in errors))
        self.assertTrue(any("not a product URL" in error for error in errors))

        for bad_url in [
            "https://outerspacer.com/products/None",
            "https://outerspacer.com/products/nested/path",
            "https://outerspacer.com/products/specimen?variant=1",
            "https://outerspacer.com/products/specimen#details",
            "https://outerspacer.com/products/bad slug",
            "https://evil.example/products/specimen",
        ]:
            row = dict(fixture, currency="USD", price=10.0, weight_g=1.0, image_url="https://cdn.example.com/1.jpg", url=bad_url)
            url_errors = validate_listings.validation_errors(row, 1, {None}, {"outerspacer"})
            self.assertTrue(any("not a product URL" in error for error in url_errors), bad_url)


if __name__ == "__main__":
    unittest.main()

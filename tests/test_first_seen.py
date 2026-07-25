import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scraper"))

import scrape  # noqa: E402


class FirstSeenTests(unittest.TestCase):
    def test_invalid_history_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            history_path = Path(directory) / "listing_history.json"
            history_path.write_text("not json", encoding="utf-8")
            with patch.object(scrape, "LISTING_HISTORY", history_path):
                with self.assertRaises(SystemExit):
                    scrape.load_listing_history()

    def test_semantically_invalid_history_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            history_path = Path(directory) / "listing_history.json"
            history_path.write_text('{"version": 1, "records": {"id:old": {"first_seen_at": "bad", "is_baseline": false}}}', encoding="utf-8")
            with patch.object(scrape, "LISTING_HISTORY", history_path):
                with self.assertRaises(SystemExit):
                    scrape.load_listing_history()

    def test_existing_scrape_time_is_the_legacy_first_seen_fallback(self):
        by_id, _ = scrape.first_seen_indexes([
            {"id": "old", "source": "Dealer", "url": "https://example.com/a", "title": "Alpha", "scraped_at": "2026-06-01T00:00:00+00:00"}
        ])
        self.assertEqual(by_id["old"]["first_seen_at"], "2026-06-01T00:00:00+00:00")
        self.assertTrue(by_id["old"]["is_baseline"])

    @patch.object(scrape, "normalize_listing_item", side_effect=lambda item, _fx: dict(item))
    def test_price_change_keeps_first_seen_through_stable_history_key(self, _normalize):
        existing = {
            "listings": [{
                "id": "old-price-id",
                "source": "Dealer",
                "url": "https://example.com/alpha",
                "title": "Alpha",
                "weight_g": 10.0,
                "price": 100.0,
                "first_seen_at": "2026-06-01T00:00:00+00:00",
                "scraped_at": "2026-06-01T00:00:00+00:00",
            }]
        }
        refreshed = {
            "new-price-id": {
                "id": "new-price-id",
                "source": "Dealer",
                "url": "https://example.com/alpha",
                "title": "Alpha",
                "weight_g": 10.0,
                "price": 80.0,
                "first_seen_at": "2026-07-24T00:00:00+00:00",
                "scraped_at": "2026-07-24T00:00:00+00:00",
            }
        }

        listings, _, _ = scrape.merge_listings(
            existing,
            refreshed,
            {"Dealer": 1},
            {"Dealer"},
            {"Dealer"},
            {},
            {},
            preserve_unselected_sources=False,
        )

        self.assertEqual(listings[0]["id"], "new-price-id")
        self.assertEqual(listings[0]["first_seen_at"], "2026-06-01T00:00:00+00:00")
        self.assertFalse(listings[0]["first_seen_is_baseline"])

    @patch.object(scrape, "normalize_listing_item", side_effect=lambda item, _fx: dict(item))
    def test_ambiguous_refreshed_rows_do_not_share_old_first_seen(self, _normalize):
        existing = {
            "listings": [{
                "id": "old-id",
                "source": "Dealer",
                "url": "https://example.com/alpha",
                "title": "Alpha",
                "weight_g": 10.0,
                "first_seen_at": "2026-06-01T00:00:00+00:00",
                "first_seen_is_baseline": False,
                "scraped_at": "2026-06-01T00:00:00+00:00",
            }]
        }
        refreshed = {
            item_id: {
                "id": item_id,
                "source": "Dealer",
                "url": "https://example.com/alpha",
                "title": "Alpha",
                "weight_g": 10.0,
                "price": price,
                "first_seen_at": "2026-07-24T00:00:00+00:00",
                "first_seen_is_baseline": False,
                "scraped_at": "2026-07-24T00:00:00+00:00",
            }
            for item_id, price in [("new-a", 80.0), ("new-b", 90.0)]
        }

        listings, _, _ = scrape.merge_listings(
            existing,
            refreshed,
            {"Dealer": 2},
            {"Dealer"},
            {"Dealer"},
            {},
            {},
            preserve_unselected_sources=False,
        )

        self.assertEqual({item["first_seen_at"] for item in listings}, {"2026-07-24T00:00:00+00:00"})

    @patch.object(scrape, "normalize_listing_item", side_effect=lambda item, _fx: dict(item))
    def test_returning_listing_uses_persisted_history_after_disappearing(self, _normalize):
        old = {
            "id": "old-price-id",
            "source": "Dealer",
            "url": "https://example.com/alpha",
            "title": "Alpha",
            "weight_g": 10.0,
            "price": 100.0,
            "first_seen_at": "2026-06-01T00:00:00+00:00",
            "first_seen_is_baseline": False,
            "scraped_at": "2026-06-01T00:00:00+00:00",
        }
        history = scrape.updated_first_seen_history({}, {"listings": [old]}, [])
        refreshed = {
            "old-price-id": {
                "id": "old-price-id",
                "source": "Dealer",
                "url": "https://example.com/alpha",
                "title": "Alpha",
                "weight_g": 10.0,
                "price": 100.0,
                "first_seen_at": "2026-07-24T00:00:00+00:00",
                "first_seen_is_baseline": False,
                "scraped_at": "2026-07-24T00:00:00+00:00",
            }
        }

        listings, _, _ = scrape.merge_listings(
            {"listings": []},
            refreshed,
            {"Dealer": 1},
            {"Dealer"},
            {"Dealer"},
            {},
            history["records"],
            preserve_unselected_sources=False,
        )

        self.assertEqual(listings[0]["first_seen_at"], "2026-06-01T00:00:00+00:00")
        self.assertFalse(listings[0]["first_seen_is_baseline"])


if __name__ == "__main__":
    unittest.main()

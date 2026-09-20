import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITES = ROOT / "data" / "sites.json"

EXPECTED_CANDIDATES = {
    "Treasure Coast Meteorite Co.",
    "OuterSpacer Meteorites",
    "MSG-Meteorites",
    "Allmeteorite",
    "Labenne Meteorites / Meteorites.tv",
    "VIP Meteorites",
    "Decker Meteorite-Shop",
    "Isameteorites",
    "Mile High Meteorites",
    "Nakhla Dog Meteorites",
    "Meteorites.dk",
    "Sun.org Meteoriteshop",
    "Southwest Meteorite Laboratory",
    "Rocks on Fire",
}


class SourceRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sites = json.loads(SITES.read_text(encoding="utf-8"))
        cls.by_name = {site["name"]: site for site in cls.sites}

    def test_vetted_candidates_are_registered(self):
        self.assertTrue(EXPECTED_CANDIDATES <= self.by_name.keys())

    def test_unimplemented_candidates_remain_disabled_backlog(self):
        implemented = {"Treasure Coast Meteorite Co.", "OuterSpacer Meteorites"}
        for name in EXPECTED_CANDIDATES - implemented:
            with self.subTest(name=name):
                self.assertFalse(self.by_name[name]["enabled"])
                self.assertEqual(self.by_name[name]["stage"], "disabled_backlog")
                self.assertEqual(self.by_name[name]["parser"], "disabled_backlog")

    def test_shopify_parser_starts_pin_us_currency(self):
        expected_parsers = {
            "Treasure Coast Meteorite Co.": "treasure_coast_meteorites",
            "OuterSpacer Meteorites": "outerspacer",
        }
        for name, parser in expected_parsers.items():
            with self.subTest(name=name):
                site = self.by_name[name]
                self.assertEqual(site["parser"], parser)
                self.assertEqual(site["currency"], "USD")
                self.assertTrue(all("country=US" in url for url in site["inventory_urls"]))

    def test_reviewed_shopify_source_states_follow_validation_and_policy(self):
        treasure_coast = self.by_name["Treasure Coast Meteorite Co."]
        self.assertFalse(treasure_coast["enabled"])
        self.assertEqual(treasure_coast["stage"], "disabled_policy_blocked")

        outerspacer = self.by_name["OuterSpacer Meteorites"]
        self.assertTrue(outerspacer["enabled"])
        self.assertEqual(outerspacer["stage"], "active_verified")

    def test_source_names_and_candidate_domains_are_unique(self):
        names = [site["name"] for site in self.sites]
        domains = [
            self.by_name[name]["base_url"].split("//", 1)[-1].strip("/").removeprefix("www.")
            for name in EXPECTED_CANDIDATES
        ]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(domains), len(set(domains)))


if __name__ == "__main__":
    unittest.main()

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  listingUsesFirstSeenBaseline,
  priceComparisonSignal,
  raritySignal,
  selectRecentFindEntries,
  selectRecentListings
} = require("../app.js");

function listing(overrides = {}) {
  return {
    id: "listing",
    source: "Test Dealer",
    url: "https://example.com/listing",
    title: "Test Meteorite",
    meteorite_type: "ordinary chondrite",
    subtype: "H5",
    canonical_name_status: "unknown",
    available: true,
    ...overrides
  };
}

test("recent listings use first-seen time, exclude unavailable stock, and deduplicate names", () => {
  const items = [
    listing({ id: "older-a", title: "Alpha", canonical_name: "Alpha", canonical_name_status: "metbull_verified", first_seen_at: "2026-07-20T10:00:00Z" }),
    listing({ id: "newer-a", title: "Alpha", canonical_name: "Alpha", canonical_name_status: "metbull_verified", first_seen_at: "2026-07-22T10:00:00Z" }),
    listing({ id: "beta", title: "Beta", scraped_at: "2026-07-21T10:00:00Z" }),
    listing({ id: "sold", title: "Sold", first_seen_at: "2026-07-23T10:00:00Z", available: false })
  ];

  assert.deepEqual(selectRecentListings(items).map((item) => item.id), ["newer-a", "beta"]);
});

test("unverified names deduplicate even when sellers disagree on classification", () => {
  const items = [
    listing({ id: "iron", title: "Gamma", meteorite_type: "iron", first_seen_at: "2026-07-20T10:00:00Z" }),
    listing({ id: "stone", title: "Gamma", meteorite_type: "ordinary chondrite", first_seen_at: "2026-07-21T10:00:00Z" })
  ];

  assert.deepEqual(selectRecentListings(items).map((item) => item.id), ["stone"]);
});

test("legacy rows are identified as tracking baselines", () => {
  assert.equal(listingUsesFirstSeenBaseline(listing({ scraped_at: "2026-06-01T00:00:00Z" })), true);
  assert.equal(listingUsesFirstSeenBaseline(listing({ first_seen_at: "2026-07-24T00:00:00Z" })), false);
  assert.equal(listingUsesFirstSeenBaseline(listing({ first_seen_at: "2026-06-01T00:00:00Z", first_seen_is_baseline: true })), true);
});

test("low price signal requires a like-for-like cohort, lower quartile, and 15 percent discount", () => {
  const prices = [10, 20, 20, 20];
  const items = prices.map((price, index) => listing({
    id: `alpha-${index}`,
    title: "Alpha",
    canonical_name: "Alpha",
    canonical_name_display: "Alpha",
    canonical_name_status: "metbull_verified",
    price_per_g_usd: price
  }));

  const signal = priceComparisonSignal(items[0], items);
  assert.equal(signal.count, 4);
  assert.equal(signal.median, 20);
  assert.equal(signal.percentBelow, 50);
  assert.equal(priceComparisonSignal(items[1], items), null);
});

test("rarity is based on a classification occupying at most 0.5 percent", () => {
  const common = Array.from({ length: 995 }, (_, index) => listing({ id: `common-${index}`, title: `Common ${index}` }));
  const rare = Array.from({ length: 5 }, (_, index) => listing({
    id: `rare-${index}`,
    title: `Rare ${index}`,
    meteorite_type: "achondrite",
    subtype: "ANGRITE"
  }));
  const items = [...common, ...rare];
  const subtypeMissing = listing({ id: "missing-subtype", title: "Missing Subtype", subtype: null });

  assert.equal(raritySignal(rare[0], items).count, 5);
  assert.equal(raritySignal(common[0], items), null);
  assert.equal(raritySignal(subtypeMissing, [...items, subtypeMissing]), null);
});

test("recent card selection keeps the eight newest and adds a newer rarity highlight", () => {
  const newest = Date.UTC(2026, 6, 24, 10);
  const items = Array.from({ length: 200 }, (_, index) => listing({
    id: `item-${index + 1}`,
    title: `Meteorite ${index + 1}`,
    first_seen_at: new Date(newest - index * 60 * 60 * 1000).toISOString()
  }));
  items[9] = listing({
    id: "rare-item",
    title: "Rare Meteorite",
    meteorite_type: "achondrite",
    subtype: "ANGRITE",
    first_seen_at: new Date(newest - 9 * 60 * 60 * 1000).toISOString()
  });

  const selected = selectRecentFindEntries(items, 9);
  assert.deepEqual(selected.filter((entry) => entry.selection === "newest").map((entry) => entry.item.id), items.slice(0, 8).map((item) => item.id));
  assert.equal(selected.find((entry) => entry.item.id === "rare-item").selection, "highlight");
});

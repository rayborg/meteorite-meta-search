#!/usr/bin/env python3
"""Lightweight checks for generated meteorite listing data."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "listings.json"

METEORITE_RE = re.compile(
    r"meteorite|chondrite|achondrite|pallasite|lunar|martian|nwa\s*\d+|"
    r"northwest africa|"
    r"sikhote|gibeon|campo|diablo|tektite|moldavite|eucrite|diogenite|howardite|"
    r"shergottite|nakhlite|aubrite|ureilite|angrite|mesosiderite|octahedrite|ataxite|"
    r"\b(?:OC|C\s?2|IIA|IAB|IIAB|IIIAB|IVA|IVB|IIE|IRUNGR|EUC)\b",
    re.I,
)
BAD_IMAGE_RE = re.compile(r"favicon|ajax-loader|logo|spinner|counter", re.I)
CATEGORY_TITLE_RE = re.compile(
    r"^(meteorites?|unclassified meteorites?|tektites?|impactites?|minerals?|books?|catalog(?:ue)?|collection|home|contact)$",
    re.I,
)
CATEGORY_PATH_RE = re.compile(r"/(?:Meteorites|Unclassified|Tektites|Impactites|Minerals|Books)(?:\.aspx)?/?$", re.I)
DETAIL_PATH_RE = re.compile(r"/(?:Meteorite|unclassified_meteorite|Tektite)\.aspx$|/[^/]*(?:product|item|specimen)[^/]*", re.I)


def suspicious_reasons(item: dict) -> list[str]:
    reasons = []
    title = str(item.get("title") or "").strip()
    url = str(item.get("url") or "")
    image_url = str(item.get("image_url") or "")
    parsed = urlparse(url)

    if CATEGORY_TITLE_RE.search(title):
        reasons.append("category title")
    if BAD_IMAGE_RE.search(image_url):
        reasons.append("favicon/logo image")
    if item.get("weight_g") and item.get("price_per_g") is not None:
        if item["weight_g"] >= 100_000 and item["price_per_g"] < 0.05:
            reasons.append("possible total-known-weight price_per_g")
    if not (METEORITE_RE.search(title) or item.get("meteorite_type") not in {None, "unknown"} or item.get("classification_text") or item.get("subtype")):
        reasons.append("no meteorite keyword/classification")
    if CATEGORY_PATH_RE.search(parsed.path) and not parsed.query:
        reasons.append("category URL without id/product pattern")
    if parsed.query and "id=" not in parsed.query.lower() and not DETAIL_PATH_RE.search(parsed.path):
        reasons.append("URL lacks id/product pattern")
    if re.search(r"meteorlab specimen|small stones were recovered|total mass of|area\.the|^0$", title, re.I):
        reasons.append("parser-contaminated title")
    if len(title) > 120:
        reasons.append("very long title")
    return reasons


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    listings = data.get("listings", [])
    by_source = Counter(item.get("source") or "unknown" for item in listings)
    suspicious = []
    for item in listings:
        reasons = suspicious_reasons(item)
        if reasons:
            suspicious.append((item, reasons))

    print(f"total listings: {len(listings)}")
    print("counts by source:")
    for source, count in sorted(by_source.items()):
        print(f"  {source}: {count}")
    print(f"with price: {sum(item.get('price') is not None for item in listings)}")
    print(f"with weight: {sum(item.get('weight_g') is not None for item in listings)}")
    print(f"with price_per_g: {sum(item.get('price_per_g') is not None for item in listings)}")
    print(f"suspicious rows: {len(suspicious)}")
    print("top 20 suspicious titles:")
    for item, reasons in suspicious[:20]:
        print(f"  [{item.get('source')}] {item.get('title')} ({'; '.join(reasons)}) - {item.get('url')}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Lightweight checks for generated meteorite listing data."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "listings.json"
SITES = ROOT / "data" / "sites.json"

METEORITE_RE = re.compile(
    r"meteorite|chondrite|achondrite|pallasite|lunar|martian|nwa\s*\d+|"
    r"northwest africa|"
    r"sikhote|gibeon|campo|diablo|tektite|moldavite|eucrite|diogenite|howardite|"
    r"shergottite|nakhlite|aubrite|ureilite|angrite|mesosiderite|octahedrite|ataxite|"
    r"\b(?:OC|C\s?2|IIA|IAB|IIAB|IIIAB|IVA|IVB|IIE|IRUNGR|EUC)\b",
    re.I,
)
BAD_IMAGE_RE = re.compile(r"favicon|ajax-loader|logo|spinner|counter|sold\.jpg|red(?:%20|\s)*dot|meteor50|frontis|wid%2012|micro%20enhanced", re.I)
SOLD_TEXT_RE = re.compile(r"\b(on\s+hold|reserved|unavailable)\b|\bsold\b(?![\s-]+by\b)(?:\s+out\b)?", re.I)
SLASH_CLASS_RE = re.compile(r"\b(?:H|L|LL)\s*[3-7](?:\.\d)?\s*/\s*[3-7](?:\.\d)?\b", re.I)
TITLE_WEIGHT_NUMBER_RE = r"(?:[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+(?:[,.][0-9]+)?|[,.][0-9]+)"
TITLE_WEIGHT_RE = re.compile(
    rf"(?<![0-9A-Za-z])({TITLE_WEIGHT_NUMBER_RE})\s*(kg|kilograms?|g|gm|gms|gr|grs|grams?|mg|milligrams?|oz|ounces?)\b",
    re.I,
)
METEOLOVERS_NON_INDIVIDUAL_RE = re.compile(
    r"(?:^|[-_/])lots?(?:[-_/]|$)|\b(?:lots?|collections?|sets?|groups?|mixed|assort(?:ed|ment)|"
    r"multiple\s+(?:pieces?|specimens?|individuals?)|small\s+individuals|"
    r"\d+\s+(?:pieces?|individuals?|fragments?|slices?|endcuts?)\b.*\b\d+\s+(?:pieces?|individuals?|fragments?|slices?|endcuts?)|"
    r"(?:slices?|endcuts?|individuals?)\s*,\s*(?:\d+\s+)?(?:slices?|endcuts?|individuals?)|"
    r"(?:slices?|endcuts?)\s*(?:and|,)\s*(?:slices?|endcuts?))\b",
    re.I,
)
ACTIVE_NON_INDIVIDUAL_RE = re.compile(
    r"\b(?:matched[-_\s]+pairs?|choose[-_\s]*(?:your|a)[-_\s]*(?:pieces?|specimens?|slices?|fragments?)|"
    r"variable[-_\s]*(?:pieces?|specimens?|weights?|sizes?)|many\s+(?:pieces?|specimens?|slices?|fragments?)|"
    rf"(?:pieces?|specimens?|slices?|fragments?)\s+from\s+{TITLE_WEIGHT_NUMBER_RE}\s*(?:to|-|\u2013)\s*{TITLE_WEIGHT_NUMBER_RE}\s*(?:kg|kilograms?|g|gm|gms|gr|grs|grams?|mg|milligrams?|oz|ounces?))\b",
    re.I,
)
ACTIVE_MIXED_ARTIFACT_RE = re.compile(r"\b(?:roof[-_\s]+panels?|broken[-_\s]+roof)\b", re.I)
VALID_CONFIDENCE = {"low", "medium", "high"}
VALID_CURRENCIES = {"USD", "EUR"}
REQUIRED_KEYS = {
    "id",
    "source",
    "source_url",
    "url",
    "title",
    "price",
    "currency",
    "weight_g",
    "price_per_g",
    "meteorite_type",
    "subtype",
    "classification_text",
    "image_url",
    "confidence",
    "available",
    "parser",
    "scraped_at",
}
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
    active_haystack = " ".join(str(item.get(key) or "") for key in ["title", "url", "classification_text", "subtype"])
    if item.get("available") is True and ACTIVE_NON_INDIVIDUAL_RE.search(active_haystack):
        reasons.append("active non-individual matched-pair/variable-piece row")
    if item.get("available") is True and ACTIVE_MIXED_ARTIFACT_RE.search(active_haystack):
        reasons.append("active mixed non-meteorite artifact row")
    return reasons


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def number_value(text: str) -> float | None:
    value = text.replace("\xa0", "").strip()
    if value.startswith((".", ",")):
        value = f"0{value}"
    if re.fullmatch(r"[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?", value):
        value = value.replace(",", "")
    elif "," in value and "." not in value:
        value = value.replace(",", ".")
    else:
        value = value.replace(",", "")
    try:
        return float(value)
    except ValueError:
        return None


def title_weight_g(title: str) -> float | None:
    match = TITLE_WEIGHT_RE.search(title)
    if not match:
        return None
    value = number_value(match.group(1))
    if value is None:
        return None
    unit = match.group(2).lower()
    if unit.startswith("kg"):
        return value * 1000
    if unit.startswith("mg"):
        return value / 1000
    if unit.startswith("oz"):
        return value * 28.349523125
    return value


def validation_errors(item: dict, index: int, valid_sources: set[str], valid_parsers: set[str]) -> list[str]:
    errors = []
    missing = sorted(REQUIRED_KEYS - set(item))
    if missing:
        errors.append(f"row {index}: missing keys {', '.join(missing)}")

    source = item.get("source")
    parser = item.get("parser")
    title = str(item.get("title") or "").strip()
    currency = item.get("currency")
    confidence = item.get("confidence")
    price = item.get("price")
    weight = item.get("weight_g")
    ppg = item.get("price_per_g")
    available = item.get("available")

    if source not in valid_sources:
        errors.append(f"row {index}: invalid source {source!r}")
    if parser not in valid_parsers:
        errors.append(f"row {index}: invalid parser {parser!r}")
    if confidence not in VALID_CONFIDENCE:
        errors.append(f"row {index}: invalid confidence {confidence!r}")
    if not isinstance(available, bool):
        errors.append(f"row {index}: available is not boolean")
    if currency is not None and currency not in VALID_CURRENCIES:
        errors.append(f"row {index}: invalid currency {currency!r}")
    if price is not None and currency not in VALID_CURRENCIES:
        errors.append(f"row {index}: priced item missing valid currency")

    if price is not None and (not is_number(price) or price <= 0):
        errors.append(f"row {index}: price is not positive numeric")
    if weight is not None and (not is_number(weight) or weight <= 0):
        errors.append(f"row {index}: weight_g is not positive numeric")
    if ppg is not None and (not is_number(ppg) or ppg <= 0):
        errors.append(f"row {index}: price_per_g is not positive numeric")

    parsed_title_weight = title_weight_g(title)
    if parsed_title_weight is not None:
        if not is_number(weight):
            errors.append(f"row {index}: title has weight but weight_g is missing")
        elif abs(weight - parsed_title_weight) > 0.001:
            errors.append(f"row {index}: title weight {parsed_title_weight}g does not match weight_g {weight!r}")

    if is_number(price) and is_number(weight) and weight > 0:
        expected = round(price / weight, 4)
        if not is_number(ppg) or abs(ppg - expected) > 0.001:
            errors.append(f"row {index}: price_per_g {ppg!r} does not match recomputed {expected}")
    elif price is None and ppg is not None:
        errors.append(f"row {index}: price_per_g present without price")

    if parser == "meteorlab" and available is True and price is not None and (weight is None or ppg is None):
        errors.append(f"row {index}: active Meteorlab priced row lacks weight/price_per_g")

    image_url = str(item.get("image_url") or "")
    if image_url and BAD_IMAGE_RE.search(image_url):
        errors.append(f"row {index}: bad decorative image URL")

    sold_haystack = " ".join(str(item.get(key) or "") for key in ["title", "url", "image_url", "classification_text", "subtype"])
    if available is True and SOLD_TEXT_RE.search(sold_haystack):
        errors.append(f"row {index}: sold/on-hold/unavailable text marked available")

    non_individual_haystack = " ".join(str(item.get(key) or "") for key in ["title", "url", "classification_text", "subtype"])
    if parser == "meteolovers" and available is True and METEOLOVERS_NON_INDIVIDUAL_RE.search(non_individual_haystack):
        errors.append(f"row {index}: active Meteolovers lot/combined-piece row")
    if available is True and ACTIVE_NON_INDIVIDUAL_RE.search(non_individual_haystack):
        errors.append(f"row {index}: active matched-pair/choose-your-piece/variable-piece row")
    if available is True and ACTIVE_MIXED_ARTIFACT_RE.search(non_individual_haystack):
        errors.append(f"row {index}: active mixed non-meteorite artifact row")

    class_haystack = " ".join(str(item.get(key) or "") for key in ["title", "classification_text"])
    preserved_haystack = " ".join(str(item.get(key) or "") for key in ["subtype", "classification_text"])
    if SLASH_CLASS_RE.search(class_haystack) and not SLASH_CLASS_RE.search(preserved_haystack):
        errors.append(f"row {index}: slash classification not preserved in subtype/classification_text")

    return errors


def metadata_errors(data: dict, listings: list[dict], sites: list[dict]) -> list[str]:
    errors = []
    enabled_sources = {site["name"] for site in sites if site.get("enabled", True)}
    valid_sources = {site["name"] for site in sites}

    if data.get("listing_count") != len(listings):
        errors.append(f"metadata listing_count {data.get('listing_count')!r} does not match {len(listings)} rows")
    if data.get("source_count") != len(enabled_sources):
        errors.append(f"metadata source_count {data.get('source_count')!r} does not match {len(enabled_sources)} enabled sources")

    for key in ["scraped_sources", "preserved_sources", "empty_refresh_preserved_sources"]:
        values = data.get(key, [])
        if values is None:
            continue
        if not isinstance(values, list):
            errors.append(f"metadata {key} is not a list")
            continue
        invalid = sorted(source for source in values if source not in valid_sources)
        if invalid:
            errors.append(f"metadata {key} contains invalid source(s): {', '.join(invalid)}")

    scraped_sources = set(data.get("scraped_sources") or [])
    preserved_sources = set(data.get("preserved_sources") or [])
    if scraped_sources & preserved_sources and not set(data.get("empty_refresh_preserved_sources") or []):
        errors.append("metadata source appears both scraped and preserved without empty_refresh_preserved_sources")

    return errors


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    sites = json.loads(SITES.read_text(encoding="utf-8"))
    valid_sources = {site["name"] for site in sites}
    valid_parsers = {site.get("parser") or "generic" for site in sites} | {"generic"}
    listings = data.get("listings", [])
    by_source = Counter(item.get("source") or "unknown" for item in listings)
    by_scraped_at = Counter(item.get("scraped_at") or "missing" for item in listings)
    suspicious = []
    errors = metadata_errors(data, listings, sites)
    duplicate_keys = Counter(
        (
            item.get("source"),
            item.get("url"),
            item.get("title"),
            item.get("price"),
            item.get("weight_g"),
        )
        for item in listings
    )
    for idx, item in enumerate(listings, 1):
        errors.extend(validation_errors(item, idx, valid_sources, valid_parsers))
        reasons = suspicious_reasons(item)
        if reasons:
            suspicious.append((item, reasons))
    for key, count in duplicate_keys.items():
        if count > 1:
            errors.append(f"duplicate listing key {key!r} appears {count} times")

    print(f"total listings: {len(listings)}")
    print(f"scrape mode: {data.get('scrape_mode') or 'unknown'}")
    print(f"scraped sources: {', '.join(data.get('scraped_sources') or []) or 'unknown'}")
    print(f"preserved sources: {', '.join(data.get('preserved_sources') or []) or 'none'}")
    if data.get("rotation_index") is not None:
        print(f"rotation index: {data.get('rotation_index')} of {data.get('rotation_total')}")
    print("counts by source:")
    for source, count in sorted(by_source.items()):
        print(f"  {source}: {count}")
    print(f"distinct row scraped_at values: {len(by_scraped_at)}")
    print(f"with price: {sum(item.get('price') is not None for item in listings)}")
    print(f"with weight: {sum(item.get('weight_g') is not None for item in listings)}")
    print(f"with price_per_g: {sum(item.get('price_per_g') is not None for item in listings)}")
    print(f"validation errors: {len(errors)}")
    for error in errors[:50]:
        print(f"  ERROR {error}")
    print(f"suspicious rows: {len(suspicious)}")
    print("top 20 suspicious titles:")
    for item, reasons in suspicious[:20]:
        print(f"  [{item.get('source')}] {item.get('title')} ({'; '.join(reasons)}) - {item.get('url')}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()

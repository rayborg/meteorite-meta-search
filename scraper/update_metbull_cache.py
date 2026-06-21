#!/usr/bin/env python3
"""Build a local Meteoritical Bulletin name cache from the public CSV export."""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "metbull_names.json"
UA = "MeteoriteMetaSearchBot/0.3 (+https://github.com/rayborg/meteorite-meta-search)"
REQUIRED_HEADERS = {"Name", "Code", "Status", "Type"}
MIN_NAMES = 80_000
MIN_ALIASES = 250_000
CACHE_COMPARE_KEYS = ("schema_version", "source", "source_url", "names", "aliases")
METBULL_CSV_URL = (
    "https://www.lpi.usra.edu/meteor/metbull.cfm?"
    "sea=%25&sfor=names&stype=contains&map=ll&country=All&srt=name&"
    "categ=All&mblist=All&snew=0&pnt=Normal%20table&csv=1"
)


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_name_key(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", clean(value))
    text = "".join(char for char in text if not unicodedata.combining(char)).lower()
    text = re.sub(r"[\u2018\u2019'`]", "", text)
    text = re.sub(r"[-_]+", " ", text)
    text = re.sub(r"\bmeteorites?\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def number_value(value: str | None):
    value = clean(value)
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def int_value(value: str | None):
    value = clean(value)
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def display_name(name: str, abbrev: str | None) -> str:
    abbrev = clean(abbrev)
    if abbrev:
        return abbrev
    match = re.fullmatch(r"Northwest Africa\s+(\d{2,6})(?:\s+([A-Z]))?", clean(name), re.I)
    if match:
        suffix = f" {match.group(2).upper()}" if match.group(2) else ""
        return f"NWA {match.group(1)}{suffix}"
    return clean(name)


def alias_values(name: str, abbrev: str | None) -> set[str]:
    aliases = {name, f"{name} meteorite"}
    if abbrev:
        aliases.update({abbrev, abbrev.replace(" ", ""), abbrev.replace(" ", "-"), f"{abbrev} meteorite"})
    nwa = re.fullmatch(r"Northwest Africa\s+(\d{2,6})(?:\s+([A-Z]))?", clean(name), re.I)
    if nwa:
        suffix = f" {nwa.group(2).upper()}" if nwa.group(2) else ""
        compact_suffix = nwa.group(2).upper() if nwa.group(2) else ""
        aliases.update(
            {
                f"NWA {nwa.group(1)}{suffix}",
                f"NWA{nwa.group(1)}{compact_suffix}",
                f"NWA-{nwa.group(1)}{compact_suffix}",
                f"Northwest Africa {nwa.group(1)}{suffix}",
                f"Northwest Africa {nwa.group(1)}{suffix} meteorite",
            }
        )
    numbered = re.fullmatch(r"(.+?)\s+(\d{2,6})([A-Za-z])?", clean(name))
    if numbered:
        prefix, number, suffix = numbered.groups()
        suffix = suffix or ""
        aliases.update({f"{prefix} {number}{suffix}", f"{prefix}{number}{suffix}", f"{prefix}-{number}{suffix}"})
    return {normalize_name_key(alias) for alias in aliases if normalize_name_key(alias)}


def fetch_csv() -> str:
    request = Request(METBULL_CSV_URL, headers={"User-Agent": UA, "Accept": "text/csv,text/plain,*/*"})
    with urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8-sig", "replace")


def build_cache(csv_text: str) -> dict:
    names = {}
    aliases = {}
    reader = csv.DictReader(csv_text.splitlines())
    missing_headers = REQUIRED_HEADERS - set(reader.fieldnames or [])
    if missing_headers:
        raise ValueError(f"MetBull CSV is missing required header(s): {', '.join(sorted(missing_headers))}")
    for row in reader:
        name = clean(row.get("Name"))
        if not name:
            continue
        key = normalize_name_key(name)
        abbrev = clean(row.get("Abbrev")) or None
        entry = {
            "code": int_value(row.get("Code")),
            "name": name,
            "display_name": display_name(name, abbrev),
            "abbrev": abbrev,
            "status": clean(row.get("Status")) or None,
            "fall": clean(row.get("Fall")) or None,
            "year": int_value(row.get("Year")),
            "place": clean(row.get("Place")) or None,
            "type": clean(row.get("Type")) or None,
            "mass_g": number_value(row.get("Mass")),
            "metbull": int_value(row.get("MetBull")),
            "antarctic": clean(row.get("Antarctic")) or None,
            "lat": number_value(row.get("Lat")),
            "long": number_value(row.get("Long")),
            "comment": clean(row.get("Comment")) or None,
        }
        names[key] = {k: v for k, v in entry.items() if v is not None}
        for alias in alias_values(name, abbrev):
            aliases.setdefault(alias, key)
    if len(names) < MIN_NAMES or len(aliases) < MIN_ALIASES:
        raise ValueError(f"MetBull CSV cache too small: {len(names)} names, {len(aliases)} aliases")
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Meteoritical Bulletin Database CSV export",
        "source_url": METBULL_CSV_URL,
        "names": names,
        "aliases": aliases,
    }


def unchanged_cache(existing: dict, new_cache: dict) -> bool:
    return all(existing.get(key) == new_cache.get(key) for key in CACHE_COMPARE_KEYS)


def main() -> None:
    cache = build_cache(fetch_csv())
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = None
        if isinstance(existing, dict) and unchanged_cache(existing, cache):
            print(f"No MetBull cache content changes: {len(cache['names'])} names and {len(cache['aliases'])} aliases")
            return

    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(OUT)
    print(f"Wrote {OUT} with {len(cache['names'])} names and {len(cache['aliases'])} aliases")


if __name__ == "__main__":
    main()

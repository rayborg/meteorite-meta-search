#!/usr/bin/env python3
"""Conservative public-page meteorite inventory scraper."""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SITES = ROOT / "data" / "sites.json"
OUT = ROOT / "data" / "listings.json"
UA = "MeteoriteMetaSearchBot/0.1 (+https://github.com/rayborg/meteorite-meta-search)"
DELAY = 2.0
MAX_PAGES_PER_SITE = 120

METEORITE_RE = re.compile(r"meteorite|chondrite|achondrite|pallasite|iron|lunar|martian|nwa\s*\d+|sikhote|gibeon|campo|diablo|tektite|moldavite|eucrite|diogenite|howardite", re.I)
PRICE_RE = re.compile(r"\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)|\b([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(?:USD|US\$)\b", re.I)
WEIGHT_RE = re.compile(r"\b([0-9]+(?:[,.][0-9]+)?)\s*(kg|kilograms?|g|grams?|mg|milligrams?|oz|ounces?)\b", re.I)

TYPE_RULES = [
    ("lunar", r"\b(lunar|moon|feldspathic breccia|lunar breccia)\b"),
    ("martian", r"\b(martian|mars|shergottite|nakhlite|chassignite)\b"),
    ("pallasite", r"\b(pallasite|olivine pallasite|esquel|im-?ilac|sericho|brahin|admire)\b"),
    ("mesosiderite", r"\bmesosiderite\b"),
    ("iron", r"\b(iron meteorite|octahedrite|ataxite|hexahedrite|sikhote|campo del cielo|canyon diablo|gibeon|muonionalusta|seymchan)\b"),
    ("carbonaceous chondrite", r"\b(carbonaceous|cv3|cm2|ci1|co3|cr2|ck|c2-?ung|c1-?ung)\b"),
    ("ordinary chondrite", r"\b(ordinary chondrite|h\s?[3-6]|l\s?[3-6]|ll\s?[3-6]|h/l|l/ll)\b"),
    ("chondrite", r"\b(chondrite|chondritic)\b"),
    ("achondrite", r"\b(achondrite|eucrite|diogenite|howardite|hed\b|ureilite|aubrite|angrite|acapulcoite|lodranite|winonaite)\b"),
    ("tektite/impactite", r"\b(tektite|moldavite|libyan desert glass|impactite|impact melt)\b"),
]

SUBTYPE_RE = re.compile(r"\b(H|L|LL)\s*-?\s*([3-6](?:\.\d)?)\b|\b(CI|CM|CO|CV|CR|CK|CH|CB)\s*-?\s*(\d(?:\.\d)?)\b|\b(EH|EL)\s*-?\s*([3-7])\b|\b(HED|eucrite|diogenite|howardite|ureilite|aubrite|angrite|shergottite|nakhlite|chassignite|octahedrite|ataxite|hexahedrite)\b", re.I)


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def num(text: str | None) -> float | None:
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html"}, timeout=25)
        if r.status_code >= 400:
            print(f"WARN {r.status_code}: {url}")
            return None
        return r.text
    except requests.RequestException as exc:
        print(f"WARN fetch failed {url}: {exc}")
        return None


def same_domain(base: str, url: str) -> bool:
    b = urlparse(base)
    u = urlparse(url)
    return (not u.netloc) or u.netloc == b.netloc


def likely_link(href: str, text: str) -> bool:
    blob = f"{href} {text}"
    if re.search(r"cart|checkout|account|login|privacy|terms|contact|about|facebook|instagram|mailto:", blob, re.I):
        return False
    return bool(METEORITE_RE.search(blob) or re.search(r"product|shop|store|specimen|meteorites?", blob, re.I))


def discover(site: dict) -> list[str]:
    base = site["base_url"]
    seen = set()
    pages = []
    for start in site.get("inventory_urls", []):
        html = fetch(start)
        time.sleep(DELAY)
        if not html:
            continue
        start_abs = urljoin(base, start).split("#", 1)[0]
        seen.add(start_abs)
        pages.append(start_abs)
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            url = urljoin(start_abs, a.get("href")).split("#", 1)[0]
            if url in seen or not same_domain(base, url):
                continue
            if likely_link(url, clean(a.get_text(" ", strip=True))):
                seen.add(url)
                pages.append(url)
            if len(pages) >= MAX_PAGES_PER_SITE:
                return pages
    return pages


def title_for(soup: BeautifulSoup) -> str:
    for sel in ["h1", "h2", ".product-title", ".product_name", ".ProductName", "title"]:
        node = soup.select_one(sel)
        if node:
            title = clean(node.get_text(" ", strip=True))
            if title:
                return title
    return "Untitled listing"


def price_for(text: str) -> tuple[float | None, str | None]:
    m = PRICE_RE.search(text)
    if not m:
        return None, None
    value = num(m.group(1) or m.group(2))
    return value, "USD" if value is not None else None


def weight_for(text: str) -> float | None:
    m = WEIGHT_RE.search(text)
    if not m:
        return None
    value = num(m.group(1).replace(",", "."))
    if value is None:
        return None
    unit = m.group(2).lower()
    if unit.startswith("kg"):
        return value * 1000
    if unit.startswith("mg"):
        return value / 1000
    if unit.startswith("oz"):
        return value * 28.349523125
    return value


def classify(text: str) -> tuple[str, str | None, str | None]:
    mtype = "unknown"
    for name, pattern in TYPE_RULES:
        if re.search(pattern, text, re.I):
            mtype = name
            break
    sm = SUBTYPE_RE.search(text)
    subtype = clean(sm.group(0)).upper() if sm else None
    bits = []
    for m in re.finditer(r"\b(?:NWA\s*\d+|H\s?[3-6](?:\.\d)?|L\s?[3-6](?:\.\d)?|LL\s?[3-6](?:\.\d)?|CM2|CV3|CO3|CR2|CI1|eucrite|diogenite|howardite|ureilite|aubrite|angrite|shergottite|nakhlite|pallasite|iron)\b", text, re.I):
        bit = clean(m.group(0))
        if bit and bit.lower() not in {x.lower() for x in bits}:
            bits.append(bit)
    return mtype, subtype, ", ".join(bits[:6]) or None


def image_for(soup: BeautifulSoup, page_url: str) -> str | None:
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return urljoin(page_url, og["content"])
    img = soup.find("img")
    if img and img.get("src"):
        return urljoin(page_url, img["src"])
    return None


def confidence(text: str, price: float | None, weight: float | None) -> str:
    score = 0
    if METEORITE_RE.search(text): score += 2
    if price is not None: score += 1
    if weight is not None: score += 1
    if re.search(r"\b(NWA\s*\d+|H\s?[3-6]|L\s?[3-6]|LL\s?[3-6]|CM2|CV3|CO3|CR2|CI1)\b", text, re.I): score += 1
    return "high" if score >= 4 else "medium" if score >= 2 else "low"


def listing_from(site: dict, url: str, html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    for bad in soup(["script", "style", "noscript", "svg"]):
        bad.decompose()
    title = title_for(soup)
    text = clean(title + " " + soup.get_text(" ", strip=True)[:2500])
    if not METEORITE_RE.search(text):
        return None
    price, currency = price_for(text)
    weight = weight_for(text)
    ppg = round(price / weight, 4) if price and weight and weight > 0 else None
    mtype, subtype, ctext = classify(text)
    raw_id = f"{site['name']}|{url}|{title}".encode("utf-8", "ignore")
    return {
        "id": hashlib.sha1(raw_id).hexdigest()[:16],
        "source": site["name"],
        "source_url": site["base_url"],
        "url": url,
        "title": title,
        "price": price,
        "currency": currency,
        "weight_g": round(weight, 4) if weight is not None else None,
        "price_per_g": ppg,
        "meteorite_type": mtype,
        "subtype": subtype,
        "classification_text": ctext,
        "image_url": image_for(soup, url),
        "confidence": confidence(text, price, weight),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    sites = json.loads(SITES.read_text(encoding="utf-8"))
    by_id = {}
    for site in sites:
        if not site.get("enabled", True):
            continue
        print("Scraping", site["name"])
        for url in discover(site):
            html = fetch(url)
            time.sleep(DELAY)
            if not html:
                continue
            item = listing_from(site, url, html)
            if item:
                by_id[item["id"]] = item
    listings = sorted(by_id.values(), key=lambda x: (x.get("meteorite_type") or "unknown", x.get("subtype") or "", x.get("price_per_g") if x.get("price_per_g") is not None else 10**9, x.get("title") or ""))
    OUT.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "source_count": len([s for s in sites if s.get("enabled", True)]), "listing_count": len(listings), "listings": listings}, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} with {len(listings)} listings")


if __name__ == "__main__":
    main()

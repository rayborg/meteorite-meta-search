#!/usr/bin/env python3
"""Site-specific public-page meteorite inventory scraper."""

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
UA = "MeteoriteMetaSearchBot/0.3 (+https://github.com/rayborg/meteorite-meta-search)"
DELAY = 2.0
MAX_INDEX_PAGES_PER_SITE = 80
MAX_DETAIL_PAGES_PER_SITE = 300

METEORITE_RE = re.compile(
    r"meteorite|chondrite|achondrite|pallasite|lunar|martian|nwa\s*\d+|"
    r"sikhote|gibeon|campo|diablo|tektite|moldavite|eucrite|diogenite|howardite|"
    r"shergottite|nakhlite|aubrite|ureilite|angrite|mesosiderite|octahedrite|ataxite",
    re.I,
)
WEIGHT_RE = re.compile(
    r"\b([0-9]+(?:[,.][0-9]+)?)\s*(kg|kilograms?|g|gr|grs|grams?|mg|milligrams?|oz|ounces?)\b",
    re.I,
)
PRICE_RE = re.compile(
    r"(?:(US\$|\$)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)|"
    r"\b(USD|US\$)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)|"
    r"\b(EUR)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)|"
    r"(€)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?))",
    re.I,
)

TYPE_RULES = [
    ("lunar", r"\b(lunar|moon|feldspathic breccia|lunar breccia)\b"),
    ("martian", r"\b(martian|mars|shergottite|nakhlite|chassignite)\b"),
    ("pallasite", r"\b(pallasite|olivine pallasite|esquel|im-?ilac|sericho|brahin|admire)\b"),
    ("mesosiderite", r"\bmesosiderite\b"),
    ("iron", r"\b(iron meteorite|octahedrite|ataxite|hexahedrite|sikhote|campo del cielo|canyon diablo|gibeon|muonionalusta|seymchan)\b"),
    ("carbonaceous chondrite", r"\b(carbonaceous|cv\s?3|cm\s?2|ci\s?1|co\s?3|cr\s?2|ck|c2-?ung|c1-?ung)\b"),
    ("ordinary chondrite", r"\b(ordinary chondrite|h\s?[3-6](?:\.\d)?|l\s?[3-6](?:\.\d)?|ll\s?[3-6](?:\.\d)?|h/l|l/ll)\b"),
    ("achondrite", r"\b(achondrite|eucrite|diogenite|howardite|hed\b|ureilite|aubrite|angrite|acapulcoite|lodranite|winonaite)\b"),
    ("chondrite", r"\b(chondrite|chondritic)\b"),
    ("tektite/impactite", r"\b(tektite|moldavite|libyan desert glass|impactite|impact melt)\b"),
]
SUBTYPE_RE = re.compile(
    r"\b(H|L|LL)\s*-?\s*([3-6](?:\.\d)?)\b|"
    r"\b(CI|CM|CO|CV|CR|CK|CH|CB)\s*-?\s*(\d(?:\.\d)?)\b|"
    r"\b(EH|EL)\s*-?\s*([3-7])\b|"
    r"\b(HED|eucrite|diogenite|howardite|ureilite|aubrite|angrite|shergottite|nakhlite|chassignite|octahedrite|ataxite|hexahedrite|acapulcoite|mesosiderite)\b",
    re.I,
)
BAD_IMAGE_RE = re.compile(r"favicon|ajax-loader|logo|spinner|counter", re.I)


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def lines_from(soup: BeautifulSoup) -> list[str]:
    return [clean(x) for x in soup.get_text("\n", strip=True).splitlines() if clean(x)]


def num(text: str | None) -> float | None:
    if not text:
        return None
    value = text.replace("\xa0", "").strip()
    if "," in value and "." not in value:
        value = value.replace(",", ".")
    else:
        value = value.replace(",", "")
    try:
        return float(value)
    except ValueError:
        return None


def fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html"}, timeout=30)
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


def url_path_query(url: str) -> str:
    u = urlparse(url)
    return f"{u.path}?{u.query}" if u.query else u.path


def title_for(soup: BeautifulSoup) -> str:
    for sel in ["h1", "h2", ".product-title", ".product_name", ".ProductName", "title"]:
        node = soup.select_one(sel)
        if node:
            title = clean(node.get_text(" ", strip=True))
            title = re.sub(r"\s+-\s+(BAITYLIA|SV Meteorites|Meteorlab).*$", "", title, flags=re.I)
            if title:
                return title
    return "Untitled listing"


def prices_in(text: str) -> list[tuple[int, float, str]]:
    found = []
    for m in PRICE_RE.finditer(text):
        groups = m.groups()
        symbol = next((x for x in groups[0::2] if x), "$")
        amount = next((x for x in groups[1::2] if x), None)
        value = num(amount)
        if value is None:
            continue
        currency = "EUR" if symbol and symbol.upper() in {"EUR", "€"} else "USD"
        found.append((m.start(), value, currency))
    return found


def first_price(text: str) -> tuple[float | None, str | None]:
    prices = prices_in(text)
    if not prices:
        return None, None
    _, value, currency = prices[0]
    return value, currency


def weight_to_g(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit.startswith("kg"):
        return value * 1000
    if unit.startswith("mg"):
        return value / 1000
    if unit.startswith("oz"):
        return value * 28.349523125
    return value


def first_weight_g(text: str) -> float | None:
    m = WEIGHT_RE.search(text)
    if not m:
        return None
    value = num(m.group(1))
    return weight_to_g(value, m.group(2)) if value is not None else None


def labeled_value(lines: list[str], label: str) -> str | None:
    pat = re.compile(rf"^{re.escape(label)}\s*:\s*(.*)$", re.I)
    for line in lines:
        m = pat.match(line)
        if m:
            return clean(m.group(1))
    return None


def labeled_weight(lines: list[str]) -> float | None:
    value = labeled_value(lines, "Weight")
    return first_weight_g(value or "")


def classify_from_text(text: str) -> tuple[str, str | None, str | None]:
    mtype = "unknown"
    for name, pattern in TYPE_RULES:
        if re.search(pattern, text, re.I):
            mtype = name
            break
    sm = SUBTYPE_RE.search(text)
    subtype = clean(sm.group(0)).upper() if sm else None
    bits = []
    for m in re.finditer(
        r"\b(?:NWA\s*\d+|H\s?[3-6](?:\.\d)?|L\s?[3-6](?:\.\d)?|LL\s?[3-6](?:\.\d)?|CM\s?2|CV\s?3|CO\s?3|CR\s?2|CI\s?1|eucrite|diogenite|howardite|ureilite|aubrite|angrite|shergottite|nakhlite|pallasite|mesosiderite|iron)\b",
        text,
        re.I,
    ):
        bit = clean(m.group(0))
        if bit and bit.lower() not in {x.lower() for x in bits}:
            bits.append(bit)
    return mtype, subtype, ", ".join(bits[:6]) or None


def classify(title: str, detail_text: str = "", explicit_type: str | None = None) -> tuple[str, str | None, str | None]:
    priority_text = clean(" ".join(x for x in [title, explicit_type] if x))
    result = classify_from_text(priority_text)
    if result[0] != "unknown" or result[1] or result[2]:
        return result
    return classify_from_text(clean(f"{title} {detail_text[:900]}"))


def image_for(soup: BeautifulSoup, page_url: str) -> str | None:
    for og in soup.find_all("meta", property="og:image"):
        content = og.get("content")
        if content and not BAD_IMAGE_RE.search(content):
            return urljoin(page_url, content)
    for img in soup.find_all("img"):
        src = img.get("src")
        if src and not BAD_IMAGE_RE.search(src):
            return urljoin(page_url, src)
    return None


def confidence(price: float | None, weight: float | None, detail_url: bool, explicit_type: str | None) -> str:
    score = 1 if detail_url else 0
    if explicit_type:
        score += 1
    if price is not None:
        score += 1
    if weight is not None:
        score += 1
    return "high" if score >= 4 else "medium" if score >= 2 else "low"


def make_listing(
    site: dict,
    url: str,
    title: str,
    *,
    price: float | None = None,
    currency: str | None = None,
    weight_g: float | None = None,
    detail_text: str = "",
    explicit_type: str | None = None,
    image_url: str | None = None,
    item_key: str | None = None,
    available: bool = True,
    parser: str | None = None,
) -> dict | None:
    title = clean(title)
    if not title or title.lower() in {"meteorites", "books", "contact", "home", "welcome to baitylia"}:
        return None
    if not (METEORITE_RE.search(title) or METEORITE_RE.search(detail_text) or explicit_type):
        return None
    mtype, subtype, ctext = classify(title, detail_text, explicit_type)
    ppg = round(price / weight_g, 4) if price and weight_g and weight_g > 0 else None
    raw_id = f"{site['name']}|{url}|{item_key or title}|{weight_g}|{price}".encode("utf-8", "ignore")
    return {
        "id": hashlib.sha1(raw_id).hexdigest()[:16],
        "source": site["name"],
        "source_url": site["base_url"],
        "url": url,
        "title": title,
        "price": price,
        "currency": currency,
        "weight_g": round(weight_g, 4) if weight_g is not None else None,
        "price_per_g": ppg,
        "meteorite_type": mtype,
        "subtype": subtype,
        "classification_text": ctext,
        "image_url": image_url,
        "confidence": confidence(price, weight_g, bool(re.search(r"[?&]id=\d+", url)), explicit_type),
        "available": available,
        "parser": parser or site.get("parser") or "generic",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def discover_details(site: dict, detail_re: re.Pattern, index_re: re.Pattern | None = None) -> list[str]:
    base = site["base_url"]
    queue = [urljoin(base, u) for u in site.get("inventory_urls", [])]
    seen_indexes = set()
    details: dict[str, None] = {}

    while queue and len(seen_indexes) < MAX_INDEX_PAGES_PER_SITE and len(details) < MAX_DETAIL_PAGES_PER_SITE:
        index_url = queue.pop(0).split("#", 1)[0]
        if index_url in seen_indexes:
            continue
        seen_indexes.add(index_url)
        html = fetch(index_url)
        time.sleep(DELAY)
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            href = urljoin(index_url, a.get("href")).split("#", 1)[0]
            if not same_domain(base, href):
                continue
            path_query = url_path_query(href)
            if detail_re.search(path_query):
                details[href] = None
            elif index_re and index_re.search(path_query) and href not in seen_indexes and href not in queue:
                queue.append(href)
    return list(details.keys())


def parse_baitylia_detail(site: dict, url: str, html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    title = title_for(soup)
    lines = lines_from(soup)
    cutoff = "\n".join(lines)
    cutoff = re.split(r"\b\d+\s+more specimen|\bmore specimen", cutoff, flags=re.I)[0]
    explicit_type = labeled_value(lines, "Type")
    weight = labeled_weight(lines) or first_weight_g(cutoff)
    price, currency = first_price(cutoff)
    item_id = labeled_value(lines, "ID#") or re.search(r"[?&]id=(\d+)", url).group(1)
    return make_listing(
        site,
        url,
        title,
        price=price,
        currency=currency,
        weight_g=weight,
        detail_text=cutoff,
        explicit_type=explicit_type,
        image_url=image_for(soup, url),
        item_key=item_id,
        parser="baitylia",
    )


def scrape_baitylia(site: dict) -> list[dict]:
    detail_re = re.compile(r"/(?:Meteorite|Unclassified|Tektite)s?\.aspx\?[^#]*\bid=\d+", re.I)
    index_re = re.compile(r"/(?:Meteorites|Unclassified|Tektites)\.aspx(?:\?|$)", re.I)
    listings = []
    for url in discover_details(site, detail_re, index_re):
        html = fetch(url)
        time.sleep(DELAY)
        if not html:
            continue
        item = parse_baitylia_detail(site, url, html)
        if item:
            listings.append(item)
    return listings


def parse_sv_detail(site: dict, url: str, html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    for bad in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        bad.decompose()
    title = title_for(soup)
    lines = lines_from(soup)
    detail_text = "\n".join(lines[:80])
    explicit_type = labeled_value(lines, "Type") or labeled_value(lines, "Class")
    weight = labeled_weight(lines) or first_weight_g(detail_text)
    price, currency = first_price(detail_text)
    item_id_match = re.search(r"[?&]id=(\d+)", url)
    return make_listing(
        site,
        url,
        title,
        price=price,
        currency=currency,
        weight_g=weight,
        detail_text=detail_text,
        explicit_type=explicit_type,
        image_url=image_for(soup, url),
        item_key=item_id_match.group(1) if item_id_match else None,
        parser="sv_meteorites",
    )


def scrape_sv_meteorites(site: dict) -> list[dict]:
    detail_re = re.compile(r"/Meteorite\.aspx\?[^#]*\bid=\d+", re.I)
    index_re = re.compile(r"/(?:Meteorites)(?:\?|$)", re.I)
    listings = []
    for url in discover_details(site, detail_re, index_re):
        html = fetch(url)
        time.sleep(DELAY)
        if not html:
            continue
        item = parse_sv_detail(site, url, html)
        if item:
            listings.append(item)
    return listings


def infer_meteorlab_title(context: str) -> str:
    context = clean(context)
    context = re.sub(r"Image: \{short description of image\}|Image", "", context, flags=re.I)
    before_weight = WEIGHT_RE.split(context, maxsplit=1)[0]
    before_weight = re.split(r"\$[0-9][0-9,.]*|\bSOLD\b", before_weight, flags=re.I)[-1]
    before_weight = re.sub(r"\b(?:mm|cm)\b.*$", "", before_weight, flags=re.I)
    before_weight = clean(before_weight.strip(" .,-;:"))
    if len(before_weight) > 120:
        before_weight = clean(before_weight[-120:])
    # Prefer a meteorite-name-looking phrase before the first class/country comma pile-up.
    m = re.search(r"([A-Z][A-Za-z0-9 ./'()\-]+?)(?:,\s*(?:[A-Z]{1,3}\d|H\d|L\d|LL\d|iron|chondrite|achondrite|pallasite|mesosiderite)|$)", before_weight, re.I)
    return clean((m.group(1) if m else before_weight) or "Meteorlab specimen")


def meteorlab_listings_from_text(site: dict, page_url: str, text: str) -> list[dict]:
    listings = []
    price_matches = prices_in(text)
    for idx, (pos, price, currency) in enumerate(price_matches):
        prefix = text[max(0, pos - 700):pos]
        wm = list(WEIGHT_RE.finditer(prefix))
        if not wm:
            continue
        last_weight = wm[-1]
        weight_value = num(last_weight.group(1))
        if weight_value is None:
            continue
        weight = weight_to_g(weight_value, last_weight.group(2))
        context = text[max(0, pos - 900):min(len(text), pos + 180)]
        if "email for price" in context.lower():
            continue
        title = infer_meteorlab_title(context)
        item = make_listing(
            site,
            page_url,
            title,
            price=price,
            currency=currency,
            weight_g=weight,
            detail_text=context,
            explicit_type=None,
            image_url=None,
            item_key=f"{idx}:{title}:{weight}:{price}",
            available="sold" not in context[max(0, pos - 80):pos + 80].lower(),
            parser="meteorlab",
        )
        if item:
            listings.append(item)
    return listings


def scrape_meteorlab(site: dict) -> list[dict]:
    listings = []
    for url in site.get("inventory_urls", []):
        html = fetch(url)
        time.sleep(DELAY)
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        cells = [clean(td.get_text(" ", strip=True)) for td in soup.find_all("td")]
        cells = [c for c in cells if len(c) > 25 and PRICE_RE.search(c) and WEIGHT_RE.search(c)]
        if cells:
            for cell in cells:
                listings.extend(meteorlab_listings_from_text(site, url, cell))
        else:
            listings.extend(meteorlab_listings_from_text(site, url, clean(soup.get_text(" ", strip=True))))
    return listings


def scrape_generic(site: dict) -> list[dict]:
    detail_re = re.compile(r"/(?:meteorite|specimen|product|item)\.(?:aspx|php|html?)\?[^#]*\bid=\d+|/(?:product|products|shop|store|specimen|item)s?/[^/#?]+", re.I)
    listings = []
    for url in discover_details(site, detail_re):
        html = fetch(url)
        time.sleep(DELAY)
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        for bad in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
            bad.decompose()
        text = clean(soup.get_text(" ", strip=True))
        title = title_for(soup)
        price, currency = first_price(text)
        item = make_listing(site, url, title, price=price, currency=currency, weight_g=first_weight_g(text), detail_text=text, image_url=image_for(soup, url))
        if item:
            listings.append(item)
    return listings


def scrape_site(site: dict) -> list[dict]:
    parser = site.get("parser") or "generic"
    if parser == "baitylia":
        return scrape_baitylia(site)
    if parser == "sv_meteorites":
        return scrape_sv_meteorites(site)
    if parser == "meteorlab":
        return scrape_meteorlab(site)
    return scrape_generic(site)


def main() -> None:
    sites = json.loads(SITES.read_text(encoding="utf-8"))
    by_id = {}
    enabled_sites = [s for s in sites if s.get("enabled", True)]
    for site in enabled_sites:
        print(f"Scraping {site['name']} with {site.get('parser', 'generic')} parser")
        for item in scrape_site(site):
            by_id[item["id"]] = item
    listings = sorted(
        by_id.values(),
        key=lambda x: (
            x.get("meteorite_type") or "unknown",
            x.get("subtype") or "",
            x.get("price_per_g") if x.get("price_per_g") is not None else 10**9,
            x.get("title") or "",
        ),
    )
    OUT.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source_count": len(enabled_sites),
                "listing_count": len(listings),
                "listings": listings,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUT} with {len(listings)} listings")


if __name__ == "__main__":
    main()

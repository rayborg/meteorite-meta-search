#!/usr/bin/env python3
"""Site-specific public-page meteorite inventory scraper."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

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
    r"northwest africa|"
    r"sikhote|gibeon|campo|diablo|tektite|moldavite|eucrite|diogenite|howardite|"
    r"shergottite|nakhlite|aubrite|ureilite|angrite|mesosiderite|octahedrite|ataxite|"
    r"\b(?:IIA|IAB|IIAB|IIIAB|IVA|IVB|IIE|IRUNGR|EUC)\b",
    re.I,
)
WEIGHT_RE = re.compile(
    r"\b([0-9]+(?:[,.][0-9]+)?)\s*(kg|kilograms?|g|gm|gms|gr|grs|grams?|mg|milligrams?|oz|ounces?)\b",
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
    ("iron", r"\b(iron meteorite|octahedrite|ataxite|hexahedrite|sikhote|campo del cielo|canyon diablo|gibeon|muonionalusta|seymchan|IIA|IAB|IIAB|IIIAB|IVA|IVB|IIE|IRUNGR|I\s*C)\b"),
    ("carbonaceous chondrite", r"\b(carbonaceous|c\s?2|cv\s?3|cvred\s?3|cvox[a-z]?\s?3|cm\s?2|ci\s?1|co\s?3|cr\s?2|ck|c3-?ung|c2-?ung|c1-?ung)\b"),
    ("ordinary chondrite", r"\b(ordinary chondrite|oc|h\s?[3-6](?:\.\d)?(?:\s*[/\-]\s*[3-6](?:\.\d)?)?|h/l\s?3?|l\s?[3-6](?:\.\d)?(?:\s*[/\-]\s*[3-6](?:\.\d)?)?|ll\s?[3-7](?:\.\d)?(?:\s*[/\-]\s*[3-7](?:\.\d)?)?|l\s?\(\s?ll\s?\)\s?3|h/l|l/ll|H|L|LL)\b"),
    ("achondrite", r"\b(achondrite|eucrite|EUC|diogenite|howardite|hed\b|ureilite|aubrite|angrite|acapulcoite|lodranite|winonaite)\b"),
    ("chondrite", r"\b(chondrite|chondritic)\b"),
    ("tektite/impactite", r"\b(tektite|moldavite|libyan desert glass|impactite|impact melt)\b"),
]
SUBTYPE_RE = re.compile(
    r"\b(H|L|LL)\s*-?\s*([3-7](?:\.\d)?(?:\s*[/\-]\s*[3-7](?:\.\d)?)?)\b|"
    r"\b(L\s?\(\s?LL\s?\)\s?3|L\s*-\s*melt breccia|LL\s?7)\b|"
    r"\b(CI|CM|CO|CV|CR|CK|CH|CB)\s*-?\s*(\d(?:\.\d)?)\b|"
    r"\b(C)\s*-?\s*(2)\b|"
    r"\b(CVred|CVoxA)\s*-?\s*3\b|"
    r"\b(OC|H/L\s?3?)\b|"
    r"\b(R)\s*-?\s*([3-6])\b|"
    r"\b(EH|EL)\s*-?\s*([3-7])\b|"
    r"\b(IIA|IAB|IIAB|IIIAB|IVA|IVB|IIE|IRUNGR|I\s*C)\b|"
    r"\b(HED|EUC|eucrite|diogenite|howardite|ureilite|aubrite|angrite|shergottite|nakhlite|chassignite|octahedrite|ataxite|hexahedrite|acapulcoite|mesosiderite)\b",
    re.I,
)
BAD_IMAGE_RE = re.compile(r"favicon|ajax-loader|logo|spinner|counter|sold\.jpg|red(?:%20|\s)*dot", re.I)
POSTBACK_RE = re.compile(r"__doPostBack\('([^']*)','([^']*)'\)")
METEORLAB_LOOSE_PRICE_RE = re.compile(r"\b(?:g|gm|gms|gr|grs|grams?)\b\s*,?\s+([0-9][0-9,]*(?:\.[0-9]{2}))\b", re.I)
SOLD_STATUS_RE = re.compile(r"\b(on\s+hold|reserved|unavailable)\b|\bsold\b(?![\s-]+by\b)(?:\s+out\b)?", re.I)
EMAIL_PRICE_RE = re.compile(r"\bemail\s+for(?:\s+new)?\s+price\b", re.I)
METEORLAB_BAD_IMAGE_RE = re.compile(
    r"favicon|ajax-loader|logo|spinner|counter|meteor50|red(?:%20|\s)*dot|sold\.jpg|frontis|wid%2012|micro%20enhanced",
    re.I,
)


class SourceLog:
    def __init__(self, site: dict):
        self.name = site["name"]
        self.parser = site.get("parser") or "generic"
        self.index_urls: list[str] = []
        self.http_statuses: Counter[str] = Counter()
        self.fetch_failures: list[str] = []
        self.detail_urls: set[str] = set()
        self.parsed = 0
        self.rejected: Counter[str] = Counter()
        self.rejected_pages: Counter[str] = Counter()

    def index(self, url: str) -> None:
        self.index_urls.append(url)

    def fetched(self, status: int) -> None:
        self.http_statuses[str(status)] += 1

    def failed(self, url: str, reason: str) -> None:
        self.fetch_failures.append(f"{url}: {reason}")

    def detail(self, url: str) -> None:
        self.detail_urls.add(url)

    def parsed_listing(self) -> None:
        self.parsed += 1

    def reject(self, reason: str) -> None:
        self.rejected[reason] += 1

    def reject_page(self, reason: str) -> None:
        self.rejected_pages[reason] += 1

    def summary(self) -> None:
        attempted = ", ".join(self.index_urls[:12])
        if len(self.index_urls) > 12:
            attempted = f"{attempted}, ... +{len(self.index_urls) - 12} more"
        statuses = ", ".join(f"{status}={count}" for status, count in sorted(self.http_statuses.items())) or "none"
        rejects = self.rejected + self.rejected_pages
        top_rejects = ", ".join(f"{reason}={count}" for reason, count in rejects.most_common(8)) or "none"
        print(f"Finished {self.name}: parser={self.parser}")
        print(f"  index URLs attempted ({len(self.index_urls)}): {attempted or 'none'}")
        print(f"  HTTP statuses: {statuses}; fetch failures={len(self.fetch_failures)}")
        if self.fetch_failures:
            for failure in self.fetch_failures[:5]:
                print(f"  fetch failure: {failure}")
        print(f"  discovered detail pages={len(self.detail_urls)}; parsed listings={self.parsed}")
        print(f"  rejected pages/items={sum(rejects.values())}; top reject reasons: {top_rejects}")


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


def fetch(url: str, log: SourceLog | None = None, kind: str = "page", session: requests.Session | None = None) -> str | None:
    try:
        client = session or requests
        r = client.get(url, headers={"User-Agent": UA, "Accept": "text/html"}, timeout=30)
        if log:
            log.fetched(r.status_code)
        if r.status_code >= 400:
            print(f"WARN {r.status_code}: {url}")
            if log:
                log.failed(url, f"{kind} HTTP {r.status_code}")
            return None
        return r.text
    except requests.RequestException as exc:
        print(f"WARN fetch failed {url}: {exc}")
        if log:
            log.failed(url, str(exc))
        return None


def post_webform(session: requests.Session, url: str, soup: BeautifulSoup, target: str, argument: str, log: SourceLog) -> str | None:
    data = {inp.get("name"): inp.get("value", "") for inp in soup.find_all("input") if inp.get("name")}
    data["__EVENTTARGET"] = target
    data["__EVENTARGUMENT"] = argument
    try:
        r = session.post(
            url,
            data=data,
            headers={"User-Agent": UA, "Accept": "text/html", "Referer": url},
            timeout=30,
        )
        log.fetched(r.status_code)
        if r.status_code >= 400:
            print(f"WARN {r.status_code}: {url} POST {target}")
            log.failed(url, f"postback {target} HTTP {r.status_code}")
            return None
        return r.text
    except requests.RequestException as exc:
        print(f"WARN postback failed {url} {target}: {exc}")
        log.failed(url, f"postback {target}: {exc}")
        return None


def same_domain(base: str, url: str) -> bool:
    b = urlparse(base)
    u = urlparse(url)
    return (not u.netloc) or u.netloc == b.netloc


def url_path_query(url: str) -> str:
    u = urlparse(url)
    return f"{u.path}?{u.query}" if u.query else u.path


def safe_http_url(base: str, value: str | None) -> str | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw or re.match(r"^(?:data|javascript|mailto|tel):", raw, re.I):
        return None
    joined = urljoin(base, raw)
    parsed = urlparse(joined)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return joined


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


def last_price(text: str) -> tuple[float | None, str | None]:
    prices = prices_in(text)
    if not prices:
        return None, None
    _, value, currency = prices[-1]
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
    label_only = re.compile(r"^[A-Za-z][A-Za-z /#-]{1,32}:$")
    for idx, line in enumerate(lines):
        m = pat.match(line)
        if m:
            value = clean(m.group(1))
            if value:
                return value
            for next_line in lines[idx + 1:idx + 4]:
                if label_only.match(next_line):
                    return None
                if clean(next_line):
                    return clean(next_line)
            return None
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
        r"\b(?:NWA\s*\d+|Northwest Africa\s*\d+|H\s?[3-6](?:\.\d)?(?:\s*[/\-]\s*[3-6](?:\.\d)?)?|H/L\s?3?|L\s?[3-6](?:\.\d)?(?:\s*[/\-]\s*[3-6](?:\.\d)?)?|LL\s?[3-7](?:\.\d)?(?:\s*[/\-]\s*[3-7](?:\.\d)?)?|L\s?\(\s?LL\s?\)\s?3|OC|C\s?2|CM\s?2|CV\s?3|CVred\s?3|CVoxA\s?3|CO\s?3|CR\s?2|CI\s?1|R\s?[3-6]|IIA|IAB|IIAB|IIIAB|IVA|IVB|IIE|IRUNGR|EUC|eucrite|diogenite|howardite|ureilite|aubrite|angrite|shergottite|nakhlite|pallasite|mesosiderite|iron)\b",
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
        image_url = safe_http_url(page_url, content)
        if image_url and not BAD_IMAGE_RE.search(image_url):
            return image_url
    for img in soup.find_all("img"):
        src = img.get("src")
        image_url = safe_http_url(page_url, src)
        if image_url and not BAD_IMAGE_RE.search(image_url):
            return image_url
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


def discover_details(site: dict, detail_re: re.Pattern, index_re: re.Pattern | None = None, log: SourceLog | None = None) -> list[str]:
    base = site["base_url"]
    queue = [urljoin(base, u) for u in site.get("inventory_urls", [])]
    seen_indexes = set()
    details: dict[str, None] = {}

    while queue and len(seen_indexes) < MAX_INDEX_PAGES_PER_SITE and len(details) < MAX_DETAIL_PAGES_PER_SITE:
        index_url = queue.pop(0).split("#", 1)[0]
        if index_url in seen_indexes:
            continue
        seen_indexes.add(index_url)
        if log:
            log.index(index_url)
        html = fetch(index_url, log, "index")
        time.sleep(DELAY)
        if not html:
            if log:
                log.reject_page("index_fetch_failed")
            continue
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            href = urljoin(index_url, a.get("href")).split("#", 1)[0]
            if not same_domain(base, href):
                continue
            path_query = url_path_query(href)
            if detail_re.search(path_query):
                details[href] = None
                if log:
                    log.detail(href)
            elif index_re and index_re.search(path_query) and href not in seen_indexes and href not in queue:
                queue.append(href)
    return list(details.keys())


def discover_webform_index_pages(site: dict, detail_re: re.Pattern, log: SourceLog) -> list[tuple[str, str]]:
    pages: list[tuple[str, str]] = []
    for start_url in site.get("inventory_urls", []):
        session = requests.Session()
        start_url = urljoin(site["base_url"], start_url)
        log.index(start_url)
        html = fetch(start_url, log, "index", session=session)
        time.sleep(DELAY)
        if not html:
            log.reject_page("index_fetch_failed")
            continue

        queue = [(start_url, html)]
        seen_pages: set[tuple[str, ...]] = set()
        seen_attempts: set[tuple[tuple[str, ...], str, str]] = set()

        while queue and len(pages) < MAX_INDEX_PAGES_PER_SITE:
            page_url, page_html = queue.pop(0)
            soup = BeautifulSoup(page_html, "lxml")
            detail_urls = sorted(
                {
                    urljoin(page_url, a.get("href")).split("#", 1)[0]
                    for a in soup.find_all("a", href=True)
                    if detail_re.search(url_path_query(urljoin(page_url, a.get("href")).split("#", 1)[0]))
                }
            )
            fingerprint = tuple(detail_urls) or (hashlib.sha1(page_html.encode("utf-8", "ignore")).hexdigest(),)
            if fingerprint in seen_pages:
                continue
            seen_pages.add(fingerprint)
            pages.append((page_url, page_html))
            for detail_url in detail_urls:
                log.detail(detail_url)

            for a in soup.find_all("a", href=True):
                match = POSTBACK_RE.search(a.get("href") or "")
                if not match:
                    continue
                label = clean(a.get_text(" ", strip=True))
                if not label:
                    continue
                target, argument = match.groups()
                attempt_key = (fingerprint, target, argument)
                if attempt_key in seen_attempts:
                    continue
                seen_attempts.add(attempt_key)
                log.index(f"{page_url} POST {target}")
                post_html = post_webform(session, page_url, soup, target, argument, log)
                time.sleep(DELAY)
                if post_html:
                    queue.append((page_url, post_html))
                else:
                    log.reject_page("postback_fetch_failed")
    return pages


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


def card_has_detail(card, page_url: str, detail_re: re.Pattern) -> bool:
    return any(
        detail_re.search(url_path_query(urljoin(page_url, a.get("href")).split("#", 1)[0]))
        for a in card.find_all("a", href=True)
    )


def inventory_card_listing(
    site: dict,
    page_url: str,
    card,
    detail_re: re.Pattern,
    *,
    parser: str,
    fallback_type: str | None = None,
    log: SourceLog,
) -> dict | None:
    detail_url = None
    for a in card.find_all("a", href=True):
        href = urljoin(page_url, a.get("href")).split("#", 1)[0]
        if same_domain(site["base_url"], href) and detail_re.search(url_path_query(href)):
            detail_url = href
            break
    if not detail_url:
        log.reject("card_missing_detail_url")
        return None

    title_node = card.select_one(".card-header")
    title = clean(title_node.get_text(" ", strip=True) if title_node else "")
    if not title:
        log.reject("card_missing_title")
        return None

    lines = lines_from(card)
    text = "\n".join(lines)
    listed_class = labeled_value(lines, "Class")
    explicit_type = listed_class or labeled_value(lines, "Type") or fallback_type
    if listed_class and not re.search(re.escape(listed_class), title, re.I):
        title = f"{title} ({listed_class})"

    price, currency = last_price(text)
    if price is None:
        log.reject("card_missing_price")
        return None

    weight = labeled_weight(lines) or first_weight_g(text)
    if weight is None:
        log.reject("card_missing_weight")
        return None

    item_id_match = re.search(r"[?&]id=(\d+)", detail_url)
    item = make_listing(
        site,
        detail_url,
        title,
        price=price,
        currency=currency,
        weight_g=weight,
        detail_text=text,
        explicit_type=explicit_type,
        image_url=image_for(card, page_url),
        item_key=item_id_match.group(1) if item_id_match else None,
        available=not re.search(r"\b(sold|on hold)\b", text, re.I),
        parser=parser,
    )
    if not item:
        log.reject("make_listing_filtered")
        return None
    log.parsed_listing()
    return item


def scrape_baitylia(site: dict, log: SourceLog) -> list[dict]:
    detail_re = re.compile(r"/(?:Meteorite|unclassified_meteorite|Tektite)\.aspx\?[^#]*\bid=\d+", re.I)
    listings = []
    seen_urls: set[str] = set()
    for page_url, html in discover_webform_index_pages(site, detail_re, log):
        soup = BeautifulSoup(html, "lxml")
        fallback_type = None
        if re.search(r"/Tektites\.aspx", page_url, re.I):
            fallback_type = "tektite"
        elif re.search(r"/Unclassified\.aspx", page_url, re.I):
            fallback_type = "unclassified meteorite"
        for card in soup.select(".card"):
            if not card_has_detail(card, page_url, detail_re):
                continue
            item = inventory_card_listing(site, page_url, card, detail_re, parser="baitylia", fallback_type=fallback_type, log=log)
            if item and item["url"] not in seen_urls:
                listings.append(item)
                seen_urls.add(item["url"])
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


def scrape_sv_meteorites(site: dict, log: SourceLog) -> list[dict]:
    detail_re = re.compile(r"/Meteorite\.aspx\?[^#]*\bid=\d+", re.I)
    listings = []
    seen_urls: set[str] = set()
    for page_url, html in discover_webform_index_pages(site, detail_re, log):
        soup = BeautifulSoup(html, "lxml")
        for card in soup.select(".card"):
            if not card_has_detail(card, page_url, detail_re):
                continue
            item = inventory_card_listing(site, page_url, card, detail_re, parser="sv_meteorites", log=log)
            if item and item["url"] not in seen_urls:
                listings.append(item)
                seen_urls.add(item["url"])
    return listings


def meteorlab_direct_rows(table) -> list:
    return [row for row in table.find_all("tr") if row.find_parent("table") is table]


def meteorlab_direct_cells(row) -> list:
    return row.find_all(["td", "th"], recursive=False)


def meteorlab_cell_text(cell) -> str:
    return clean(cell.get_text(" ", strip=True))


def meteorlab_title(raw_title: str) -> str:
    title = clean(raw_title)
    title = re.sub(r"\bsold\b(?![\s-]+by\b).*$", "", title, flags=re.I)
    title = re.sub(r"\b(?:Image|Images?)\b.*$", "", title, flags=re.I)
    title = re.sub(r"\s*[-\u2013\u2014]\s*(?:front|reverse|back).*", "", title, flags=re.I)
    title = re.split(
        r"\b(?:Fell|Found|Purchased|Recovered|Classified|A shower|A single|Single stone|TKW|Total known weight|One stone|More about)\b",
        title,
        maxsplit=1,
        flags=re.I,
    )[0]
    title = re.sub(r"\s+meteoritestructures\.org.*$", "", title, flags=re.I)
    title = clean(title.strip(" .,-;:"))
    if len(title) > 140:
        title = clean(re.split(r"[.;]", title, maxsplit=1)[0])
    return title


def meteorlab_price(text: str) -> tuple[float | None, str | None]:
    price, currency = last_price(text)
    if price is not None:
        return price, currency
    # Some old cells omit the dollar sign: "2.08 grams, 40.00".
    if WEIGHT_RE.search(text):
        matches = list(METEORLAB_LOOSE_PRICE_RE.finditer(text))
        if matches:
            value = num(matches[-1].group(1))
            if value is not None:
                return value, "USD"
    return None, None


def meteorlab_weight(title_text: str, price_text: str) -> float | None:
    start_weight = re.match(r"^\s*([0-9]+(?:[,.][0-9]+)?)\s*(g|gm|gms|gr|grs|grams?)\b", price_text, re.I)
    if start_weight:
        value = num(start_weight.group(1))
        return weight_to_g(value, start_weight.group(2)) if value is not None else None

    title_weight = first_weight_g(meteorlab_title(title_text))
    if title_weight is not None:
        return title_weight

    price_matches = prices_in(price_text)
    price_pos = price_matches[-1][0] if price_matches else len(price_text)
    for match in reversed(list(WEIGHT_RE.finditer(price_text[:price_pos]))):
        context = price_text[max(0, match.start() - 45):match.end() + 45].lower()
        if re.search(r"total|tkw|known|found|recovered|single mass|totalling|weighing", context):
            continue
        value = num(match.group(1))
        if value is not None:
            return weight_to_g(value, match.group(2))
    return None


def meteorlab_img_dimension(img, attr: str) -> int | None:
    value = img.get(attr)
    if not value:
        return None
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None


def meteorlab_img_srcs(cell) -> list[str]:
    return [img.get("src") or "" for img in cell.find_all("img") if img.get("src")]


def meteorlab_has_sold_image(cell) -> bool:
    for img in cell.find_all("img"):
        src = img.get("src") or ""
        path = unquote(urlparse(src).path)
        marker_text = clean(" ".join(str(img.get(attr) or "") for attr in ["alt", "title"]))
        if re.search(r"(?:^|/)sold\.(?:jpe?g|png|gif)$", path, re.I) or SOLD_STATUS_RE.search(marker_text):
            return True
    return False


def meteorlab_product_image_url(img, page_url: str) -> str | None:
    src = img.get("src") or ""
    image_url = safe_http_url(page_url, src)
    if not image_url or METEORLAB_BAD_IMAGE_RE.search(image_url):
        return None
    width = meteorlab_img_dimension(img, "width")
    height = meteorlab_img_dimension(img, "height")
    if width is not None and height is not None and width <= 24 and height <= 24:
        return None
    return image_url


def meteorlab_product_images(cell, page_url: str) -> list[str]:
    urls = []
    for img in cell.find_all("img"):
        image_url = meteorlab_product_image_url(img, page_url)
        if image_url:
            urls.append(image_url)
    return urls


def meteorlab_has_product_image(cell) -> bool:
    return bool(meteorlab_product_images(cell, "https://meteorlab.com/"))


def meteorlab_status_like(text: str, cell) -> bool:
    return bool(
        meteorlab_has_sold_image(cell)
        or SOLD_STATUS_RE.search(text)
        or EMAIL_PRICE_RE.search(text)
        or PRICE_RE.search(text)
        or (WEIGHT_RE.search(text) and METEORLAB_LOOSE_PRICE_RE.search(text))
    )


def meteorlab_context_text(text: str) -> bool:
    if not text or text in {".", "-"} or re.fullmatch(r"[A-Z]", text):
        return False
    if re.search(
        r"refresh|ordering page|questions on|conditions of sale|copyright|indicates observed fall|menu page|page \d",
        text,
        re.I,
    ):
        return False
    return True


def meteorlab_image_title_fallback(cell) -> str | None:
    labels = []
    for img in cell.find_all("img"):
        if not meteorlab_product_image_url(img, "https://meteorlab.com/"):
            continue
        for attr in ["title", "alt"]:
            label = clean(str(img.get(attr) or ""))
            if not label or SOLD_STATUS_RE.search(label):
                continue
            if re.search(r"\{\s*short description|meteorite image file", label, re.I):
                continue
            if re.fullmatch(r"(?:image|photo|thumbnail|front|reverse|back)", label, re.I):
                continue
            if meteorlab_context_text(label):
                labels.append(label)
    return clean(" ".join(labels)) or None


def meteorlab_title_from_image(image_url: str | None) -> str | None:
    if not image_url:
        return None
    filename = unquote(urlparse(image_url).path.rsplit("/", 1)[-1])
    stem = re.sub(r"\.[a-z0-9]{2,5}$", "", filename, flags=re.I)
    stem = clean(stem.replace("_", " ").replace("-", " "))
    stem = re.sub(r"\s*\b(?:front|reverse|back)\b.*$", "", stem, flags=re.I)
    stem = re.sub(r"\s*\b[0-9]+(?:[,.][0-9]+)?\s*(?:kg|kilograms?|g|gm|gms|gr|grs|grams?|mg|milligrams?|oz|ounces?)\b.*$", "", stem, flags=re.I)
    title = meteorlab_title(stem)
    return title or None


def meteorlab_weight_from_image(image_url: str | None) -> float | None:
    if not image_url:
        return None
    filename = unquote(urlparse(image_url).path.rsplit("/", 1)[-1])
    return first_weight_g(filename)


def meteorlab_new_state() -> dict:
    return {"texts": [], "image_url": None, "sold": False}


def meteorlab_layout_columns(table) -> list[int]:
    rows = meteorlab_direct_rows(table)
    column_scores: Counter[int] = Counter()
    column_strong_scores: Counter[int] = Counter()
    score7 = 0
    rows7 = 0
    score5 = 0
    rows5 = 0
    for row in rows:
        cells = meteorlab_direct_cells(row)
        for idx, cell in enumerate(cells):
            text = meteorlab_cell_text(cell)
            strong = meteorlab_has_product_image(cell) or meteorlab_status_like(text, cell)
            if strong or METEORITE_RE.search(text) or WEIGHT_RE.search(text):
                column_scores[idx] += 1
            if strong:
                column_strong_scores[idx] += 1
        if len(cells) >= 7:
            rows7 += 1
            for idx in [0, 2, 4, 6]:
                text = meteorlab_cell_text(cells[idx])
                if meteorlab_has_product_image(cells[idx]) or meteorlab_status_like(text, cells[idx]) or METEORITE_RE.search(text) or WEIGHT_RE.search(text):
                    score7 += 1
        if len(cells) >= 5:
            rows5 += 1
            for idx in [1, 3]:
                text = meteorlab_cell_text(cells[idx])
                if meteorlab_has_product_image(cells[idx]) or meteorlab_status_like(text, cells[idx]) or METEORITE_RE.search(text) or WEIGHT_RE.search(text):
                    score5 += 1
    if rows7 >= 3 and score7 >= 8:
        return [0, 2, 4, 6]
    if rows5 >= 3 and score5 >= 4:
        return [1, 3]
    flexible_cols = [idx for idx in sorted(column_scores) if column_strong_scores[idx] and column_scores[idx] >= 2]
    if 1 <= len(flexible_cols) <= 6:
        return flexible_cols
    return []


def meteorlab_listing_from_state(
    site: dict,
    page_url: str,
    state: dict,
    status_text: str,
    *,
    table_index: int,
    row_index: int,
    col_index: int,
    sold_now: bool,
    log: SourceLog,
) -> dict | None:
    title_text = clean(" ".join(state["texts"]))
    context = clean(f"{title_text} {status_text}")
    if state["sold"] or sold_now or SOLD_STATUS_RE.search(status_text):
        log.reject("meteorlab_sold")
        return None

    email_price = bool(EMAIL_PRICE_RE.search(status_text))
    price, currency = (None, None) if email_price else meteorlab_price(status_text)
    if price is None and not email_price:
        log.reject("meteorlab_missing_price")
        return None

    image_url = state["image_url"]
    title = meteorlab_title(title_text)
    title_from_image = False
    if (not title or re.search(r"\{\s*short description", title, re.I)) and image_url:
        image_title = meteorlab_title_from_image(image_url)
        if image_title:
            title = image_title
            title_from_image = True
    if not title:
        log.reject("meteorlab_missing_title")
        return None
    if re.search(r"\breverse side\b", title_text, re.I):
        log.reject("meteorlab_reverse_side")
        return None
    if not METEORITE_RE.search(title) and (METEORITE_RE.search(title_text) or title_from_image):
        title = f"{title} meteorite"

    weight = meteorlab_weight(title_text, status_text) or meteorlab_weight_from_image(image_url)
    if price is not None and weight is None:
        log.reject("meteorlab_missing_weight")
        return None

    item = make_listing(
        site,
        page_url,
        title,
        price=price,
        currency=currency or ("USD" if price is not None else None),
        weight_g=weight,
        detail_text=context,
        explicit_type=None,
        image_url=image_url,
        item_key=f"{table_index}:{row_index}:{col_index}:{title}:{weight}:{price}:{image_url}",
        available=True,
        parser="meteorlab",
    )
    if not item:
        log.reject("make_listing_filtered")
        return None
    log.parsed_listing()
    return item


def meteorlab_items_from_table(site: dict, page_url: str, table, logical_cols: list[int], table_index: int, log: SourceLog) -> list[dict]:
    listings = []
    states = {idx: meteorlab_new_state() for idx in logical_cols}

    for row_index, row in enumerate(meteorlab_direct_rows(table)):
        cells = meteorlab_direct_cells(row)
        if len(cells) <= max(logical_cols):
            continue
        for col_index in logical_cols:
            cell = cells[col_index]
            state = states[col_index]
            text = meteorlab_cell_text(cell)
            product_images = meteorlab_product_images(cell, page_url)
            sold_now = bool(meteorlab_has_sold_image(cell) or SOLD_STATUS_RE.search(text))
            status_like = meteorlab_status_like(text, cell)
            has_hr = bool(cell.find("hr"))

            if product_images:
                if state["image_url"] and (state["texts"] or state["sold"]) and not status_like:
                    state = meteorlab_new_state()
                    states[col_index] = state
                state["image_url"] = product_images[0]
                image_title = meteorlab_image_title_fallback(cell)
                if image_title and not text and image_title not in state["texts"]:
                    state["texts"].append(image_title)

            if status_like:
                status_has_only_sold_marker = sold_now and not (PRICE_RE.search(text) or EMAIL_PRICE_RE.search(text) or METEORLAB_LOOSE_PRICE_RE.search(text))
                if status_has_only_sold_marker and not state["texts"] and not state["image_url"]:
                    states[col_index] = meteorlab_new_state()
                    continue
                if sold_now:
                    state["sold"] = True
                if not state["texts"] and not state["image_url"]:
                    log.reject("meteorlab_status_without_context")
                    states[col_index] = meteorlab_new_state()
                    continue
                item = meteorlab_listing_from_state(
                    site,
                    page_url,
                    state,
                    text,
                    table_index=table_index,
                    row_index=row_index,
                    col_index=col_index,
                    sold_now=sold_now,
                    log=log,
                )
                if item:
                    listings.append(item)
                states[col_index] = meteorlab_new_state()
                continue

            if text and meteorlab_context_text(text):
                state["texts"].append(text)

            if has_hr or (not text and not product_images and not state["image_url"]):
                states[col_index] = meteorlab_new_state()

    return listings


def meteorlab_items_from_rows(site: dict, page_url: str, soup: BeautifulSoup, log: SourceLog) -> list[dict]:
    listings = []
    seen_keys: set[tuple] = set()
    for table_index, table in enumerate(soup.find_all("table")):
        logical_cols = meteorlab_layout_columns(table)
        if not logical_cols:
            continue
        for item in meteorlab_items_from_table(site, page_url, table, logical_cols, table_index, log):
            key = (item.get("title"), item.get("price"), item.get("weight_g"), item.get("image_url"))
            if key in seen_keys:
                log.reject("meteorlab_duplicate_in_page")
                continue
            seen_keys.add(key)
            listings.append(item)
    return listings


def scrape_meteorlab(site: dict, log: SourceLog) -> list[dict]:
    listings = []
    for url in site.get("inventory_urls", []):
        log.index(url)
        html = fetch(url, log, "index")
        time.sleep(DELAY)
        if not html:
            log.reject_page("index_fetch_failed")
            continue
        soup = BeautifulSoup(html, "lxml")
        for bad in soup(["script", "style", "noscript"]):
            bad.decompose()
        page_items = meteorlab_items_from_rows(site, url, soup, log)
        if not page_items:
            log.reject_page("meteorlab_no_row_items")
        listings.extend(page_items)
    return listings


def meta_content(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        node = soup.find("meta", property=name) or soup.find("meta", attrs={"name": name})
        if node and node.get("content"):
            return clean(node.get("content"))
    return None


def json_ld_objects(soup: BeautifulSoup) -> list:
    objects = []
    for script in soup.find_all("script", type=re.compile(r"ld\+json", re.I)):
        raw = script.string or script.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            objects.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return objects


def iter_json_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_json_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_json_nodes(child)


def schema_product(soup: BeautifulSoup) -> dict | None:
    for root in json_ld_objects(soup):
        for node in iter_json_nodes(root):
            node_type = node.get("@type")
            if isinstance(node_type, list):
                types = {str(x).lower() for x in node_type}
            else:
                types = {str(node_type).lower()}
            if "product" in types:
                return node
    return None


def first_schema_offer(product: dict | None) -> dict:
    if not product:
        return {}
    offers = product.get("offers") or {}
    if isinstance(offers, list):
        return next((offer for offer in offers if isinstance(offer, dict)), {})
    return offers if isinstance(offers, dict) else {}


def schema_image_url(product: dict | None, page_url: str) -> str | None:
    if not product:
        return None
    image = product.get("image")
    if isinstance(image, list):
        image = next((x for x in image if x), None)
    if isinstance(image, dict):
        image = image.get("url") or image.get("contentUrl")
    if isinstance(image, str):
        image_url = safe_http_url(page_url, image)
        if image_url and not BAD_IMAGE_RE.search(image_url):
            return image_url
    return None


def product_detail_listing(site: dict, url: str, html: str, parser: str, log: SourceLog, fallback_type: str | None = None) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    product = schema_product(soup)
    offer = first_schema_offer(product)
    for bad in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        bad.decompose()

    title = clean((product or {}).get("name") if isinstance((product or {}).get("name"), str) else "")
    title = title or meta_content(soup, "og:title", "twitter:title") or title_for(soup)
    lines = lines_from(soup)
    text = "\n".join(lines[:120])
    availability = clean(str(offer.get("availability") or meta_content(soup, "product:availability") or ""))
    if re.search(r"outofstock|unavailable|discontinued", availability, re.I) or SOLD_STATUS_RE.search(availability) or SOLD_STATUS_RE.search(text[:800]) or re.search(r"out of stock", text[:800], re.I):
        log.reject("product_unavailable")
        return None

    price = num(str(offer.get("price") or offer.get("lowPrice") or ""))
    currency = clean(str(offer.get("priceCurrency") or meta_content(soup, "product:price:currency") or "")) or None
    if price is None:
        price = num(meta_content(soup, "product:price:amount"))
    if price is None:
        price, currency_from_text = last_price(text)
        currency = currency or currency_from_text
    if price is None:
        log.reject("product_missing_price")
        return None

    weight = first_weight_g(title) or labeled_weight(lines) or first_weight_g(text[:1600])
    if weight is None:
        log.reject("product_missing_weight")
        return None

    image_url = schema_image_url(product, url) or meta_content(soup, "og:image", "twitter:image")
    if image_url:
        image_url = safe_http_url(url, image_url)
    item = make_listing(
        site,
        url,
        title,
        price=price,
        currency=currency or "USD",
        weight_g=weight,
        detail_text=text,
        explicit_type=fallback_type,
        image_url=image_url or image_for(soup, url),
        item_key=clean(str((product or {}).get("sku") or offer.get("sku") or title)),
        parser=parser,
    )
    if not item:
        log.reject("make_listing_filtered")
        return None
    log.parsed_listing()
    return item


def discover_product_cards(site: dict, log: SourceLog, detail_re: re.Pattern, card_selectors: list[str]) -> list[str]:
    details: dict[str, None] = {}
    queue = [urljoin(site["base_url"], url) for url in site.get("inventory_urls", [])]
    seen_indexes: set[str] = set()
    while queue and len(seen_indexes) < MAX_INDEX_PAGES_PER_SITE and len(details) < MAX_DETAIL_PAGES_PER_SITE:
        page_url = queue.pop(0).split("#", 1)[0]
        if page_url in seen_indexes:
            continue
        seen_indexes.add(page_url)
        log.index(page_url)
        html = fetch(page_url, log, "index")
        time.sleep(DELAY)
        if not html:
            log.reject_page("index_fetch_failed")
            continue
        soup = BeautifulSoup(html, "lxml")
        cards = []
        for selector in card_selectors:
            cards.extend(soup.select(selector))
        for card in cards:
            card_text = clean(card.get_text(" ", strip=True))
            if SOLD_STATUS_RE.search(card_text) or re.search(r"out of stock", card_text, re.I):
                continue
            for a in card.find_all("a", href=True):
                href = urljoin(page_url, a.get("href")).split("#", 1)[0]
                if not same_domain(site["base_url"], href):
                    continue
                if re.search(r"add[-_]?to[-_]?cart|cart\.php|quickview|login|compare|search", href, re.I):
                    continue
                if detail_re.search(url_path_query(href)):
                    details[href] = None
                    log.detail(href)
                    break
        for rel_next in soup.find_all(["a", "link"], rel=re.compile("next", re.I)):
            href = rel_next.get("href")
            if href:
                next_url = urljoin(page_url, href).split("#", 1)[0]
                if same_domain(site["base_url"], next_url) and next_url not in seen_indexes and next_url not in queue:
                    queue.append(next_url)
    return list(details.keys())


def scrape_product_card_details(site: dict, log: SourceLog, parser: str, detail_re: re.Pattern, card_selectors: list[str], fallback_type: str | None = None) -> list[dict]:
    listings = []
    for url in discover_product_cards(site, log, detail_re, card_selectors):
        html = fetch(url, log, "detail")
        time.sleep(DELAY)
        if not html:
            log.reject_page("detail_fetch_failed")
            continue
        item = product_detail_listing(site, url, html, parser, log, fallback_type=fallback_type)
        if item:
            listings.append(item)
    return listings


def scrape_meteorite_exchange(site: dict, log: SourceLog) -> list[dict]:
    detail_re = re.compile(r"/[^/#?]+\.html$", re.I)
    return scrape_product_card_details(site, log, "meteorite_exchange", detail_re, ["li.product", ".product", ".wc-block-grid__product"])


def scrape_fossilera(site: dict, log: SourceLog) -> list[dict]:
    detail_re = re.compile(r"^/meteorites/[^/?#]+", re.I)
    return scrape_product_card_details(site, log, "fossilera", detail_re, [".specimen-listing"])


def scrape_galactic_stone(site: dict, log: SourceLog) -> list[dict]:
    detail_re = re.compile(r"^/(?!cart\.php|login\.php|search\.php|compare/?$)[a-z0-9][a-z0-9-]+/?$", re.I)
    return scrape_product_card_details(site, log, "galactic_stone", detail_re, ["article.card"])


def meteorite_market_page_title(soup: BeautifulSoup) -> str:
    title = title_for(soup)
    title = re.sub(r"\s+for Sale\b.*$", "", title, flags=re.I)
    return clean(title)


def scrape_meteorite_market(site: dict, log: SourceLog) -> list[dict]:
    listings = []
    for url in site.get("inventory_urls", []):
        log.index(url)
        html = fetch(url, log, "index")
        time.sleep(DELAY)
        if not html:
            log.reject_page("index_fetch_failed")
            continue
        soup = BeautifulSoup(html, "lxml")
        page_title = meteorite_market_page_title(soup)
        explicit_type = labeled_value(lines_from(soup), "Classification")
        for table_index, table in enumerate(soup.find_all("table")):
            rows = [meteorlab_direct_cells(row) for row in meteorlab_direct_rows(table)]
            if len(rows) < 5 or not rows[0]:
                continue
            columns = max(len(row) for row in rows)
            for col in range(columns):
                col_cells = [row[col] for row in rows if col < len(row)]
                text_cells = [meteorlab_cell_text(cell) for cell in col_cells]
                price_text = next((text for text in text_cells if re.search(r"\bPrice\s*:", text, re.I)), "")
                if not price_text or SOLD_STATUS_RE.search(price_text):
                    continue
                price, currency = first_price(price_text)
                weight_text = next((text for text in text_cells if re.search(r"\bWeight\s*:", text, re.I)), "")
                weight = first_weight_g(weight_text)
                item_id = clean(next((text for text in text_cells if text.startswith("#")), ""))
                image_url = None
                for cell in col_cells:
                    image_url = image_for(cell, url)
                    if image_url and not re.search(r"scale|spacer|line|buy\.gif|mmhead", image_url, re.I):
                        break
                    image_url = None
                if price is None or weight is None:
                    continue
                item = make_listing(
                    site,
                    url,
                    clean(f"{page_title} {item_id}"),
                    price=price,
                    currency=currency or "USD",
                    weight_g=weight,
                    detail_text=" ".join(text_cells),
                    explicit_type=explicit_type,
                    image_url=image_url,
                    item_key=f"{table_index}:{col}:{item_id}:{weight}:{price}",
                    parser="meteorite_market",
                )
                if item:
                    listings.append(item)
                    log.parsed_listing()
    return listings


def scrape_arizona_skies(site: dict, log: SourceLog) -> list[dict]:
    detail_re = re.compile(r"/(?:AZ_Skies_Links/(?:Lunar|Martian|Achondrites|Chondrites_Main|Irons|Stony_Irons)|Inexpensive_Meteorites)[^#]*", re.I)
    return scrape_product_card_details(site, log, "arizona_skies", detail_re, ["body"], fallback_type="meteorite")


def scrape_generic(site: dict, log: SourceLog) -> list[dict]:
    detail_re = re.compile(r"/(?:meteorite|specimen|product|item)\.(?:aspx|php|html?)\?[^#]*\bid=\d+|/(?:product|products|shop|store|specimen|item)s?/[^/#?]+", re.I)
    listings = []
    for url in discover_details(site, detail_re, log=log):
        html = fetch(url, log, "detail")
        time.sleep(DELAY)
        if not html:
            log.reject_page("detail_fetch_failed")
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
            log.parsed_listing()
        else:
            log.reject("make_listing_filtered")
    return listings


def scrape_site(site: dict, log: SourceLog) -> list[dict]:
    parser = site.get("parser") or "generic"
    if parser == "baitylia":
        return scrape_baitylia(site, log)
    if parser == "sv_meteorites":
        return scrape_sv_meteorites(site, log)
    if parser == "meteorlab":
        return scrape_meteorlab(site, log)
    if parser == "meteorite_exchange":
        return scrape_meteorite_exchange(site, log)
    if parser == "fossilera":
        return scrape_fossilera(site, log)
    if parser == "galactic_stone":
        return scrape_galactic_stone(site, log)
    if parser == "meteorite_market":
        return scrape_meteorite_market(site, log)
    if parser == "arizona_skies":
        return scrape_arizona_skies(site, log)
    return scrape_generic(site, log)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape configured meteorite seller inventory.")
    parser.add_argument(
        "--rotate",
        action="store_true",
        help="Scrape one enabled source chosen deterministically from the rotation key.",
    )
    parser.add_argument(
        "--rotation-key",
        help="Seed for --rotate. Defaults to GITHUB_RUN_NUMBER, then the current 5-minute time slot.",
    )
    parser.add_argument(
        "--site",
        action="append",
        default=[],
        help="Scrape one enabled source by name or parser id. Can be repeated.",
    )
    parser.add_argument(
        "--sites",
        help="Comma-separated enabled source names or parser ids to scrape.",
    )
    parser.add_argument(
        "--preserve-existing",
        dest="preserve_existing",
        action="store_true",
        help="Merge refreshed sources into the existing listings file and keep enabled sources not scraped now.",
    )
    parser.add_argument(
        "--no-preserve-existing",
        dest="preserve_existing",
        action="store_false",
        help="Write only listings scraped in this run.",
    )
    parser.set_defaults(preserve_existing=None)
    return parser.parse_args()


def normalize_site_selector(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def site_aliases(site: dict) -> set[str]:
    return {
        normalize_site_selector(str(site.get("name") or "")),
        normalize_site_selector(str(site.get("parser") or "generic")),
    }


def requested_site_tokens(args: argparse.Namespace) -> list[str]:
    tokens = list(args.site or [])
    if args.sites:
        tokens.extend(args.sites.split(","))
    return [token.strip() for token in tokens if token.strip()]


def default_rotation_key() -> str:
    return os.environ.get("GITHUB_RUN_NUMBER") or str(int(time.time() // 300))


def rotation_seed(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return int(hashlib.sha1(value.encode("utf-8", "ignore")).hexdigest(), 16)


def select_named_sites(enabled_sites: list[dict], tokens: list[str]) -> list[dict]:
    selected = []
    selected_names = set()
    missing = []
    for token in tokens:
        normalized = normalize_site_selector(token)
        match = next((site for site in enabled_sites if normalized in site_aliases(site)), None)
        if not match:
            missing.append(token)
            continue
        if match["name"] not in selected_names:
            selected.append(match)
            selected_names.add(match["name"])
    if missing:
        valid = ", ".join(site["name"] for site in enabled_sites) or "none"
        raise SystemExit(f"Unknown or disabled source(s): {', '.join(missing)}. Enabled sources: {valid}")
    return selected


def select_run_sites(args: argparse.Namespace, enabled_sites: list[dict]) -> tuple[list[dict], dict]:
    tokens = requested_site_tokens(args)
    if args.rotate and tokens:
        raise SystemExit("--rotate cannot be combined with --site or --sites")
    if args.rotate:
        if not enabled_sites:
            raise SystemExit("No enabled sources are available for rotation")
        key = args.rotation_key or default_rotation_key()
        seed = rotation_seed(key)
        index = ((seed - 1) if seed > 0 else seed) % len(enabled_sites)
        return [enabled_sites[index]], {
            "rotation_index": index,
            "rotation_total": len(enabled_sites),
            "rotation_key": key,
        }
    if tokens:
        return select_named_sites(enabled_sites, tokens), {}
    return enabled_sites, {}


def sort_listings(listings) -> list[dict]:
    return sorted(
        listings,
        key=lambda x: (
            x.get("meteorite_type") or "unknown",
            x.get("subtype") or "",
            x.get("price_per_g") if x.get("price_per_g") is not None else 10**9,
            x.get("title") or "",
        ),
    )


def source_ordered_names(names: set[str], sites: list[dict]) -> list[str]:
    return [site["name"] for site in sites if site["name"] in names]


def load_existing_data() -> dict:
    if not OUT.exists():
        return {}
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"WARN unable to read existing listings for preservation: {exc}")
        return {}


def scrape_selected_sites(selected_sites: list[dict]) -> tuple[dict[str, dict], dict[str, int]]:
    by_id = {}
    scraped_counts = {}
    for site in selected_sites:
        log = SourceLog(site)
        print(f"Scraping {site['name']} with {site.get('parser', 'generic')} parser")
        for item in scrape_site(site, log):
            by_id[item["id"]] = item
        scraped_counts[site["name"]] = sum(1 for item in by_id.values() if item.get("source") == site["name"])
        log.summary()
    return by_id, scraped_counts


def merge_listings(
    existing_data: dict,
    refreshed_by_id: dict[str, dict],
    scraped_counts: dict[str, int],
    scraped_sources: set[str],
    enabled_sources: set[str],
) -> tuple[list[dict], set[str], set[str]]:
    merged_by_id = {}
    preserved_sources = set()
    empty_refresh_preserved_sources = set()

    for item in existing_data.get("listings", []):
        source = item.get("source")
        item_id = item.get("id")
        if source not in enabled_sources or not item_id:
            continue
        if source in scraped_sources and scraped_counts.get(source, 0) > 0:
            continue
        if source in scraped_sources:
            empty_refresh_preserved_sources.add(source)
        preserved_sources.add(source)
        merged_by_id[str(item_id)] = item

    merged_by_id.update(refreshed_by_id)
    return list(merged_by_id.values()), preserved_sources, empty_refresh_preserved_sources


def output_payload(
    *,
    listings: list[dict],
    enabled_sites: list[dict],
    selected_sites: list[dict],
    preserved_sources: set[str],
    empty_refresh_preserved_sources: set[str],
    rotation_info: dict,
    preserve_existing: bool,
) -> dict:
    scraped_sources = [site["name"] for site in selected_sites]
    mode = "rotation" if rotation_info else "selected" if len(selected_sites) != len(enabled_sites) else "full"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_count": len(enabled_sites),
        "listing_count": len(listings),
        "scrape_mode": mode,
        "preserve_existing": preserve_existing,
        "scraped_sources": scraped_sources,
        "preserved_sources": source_ordered_names(preserved_sources, enabled_sites),
    }
    if rotation_info:
        payload.update(rotation_info)
    if empty_refresh_preserved_sources:
        payload["empty_refresh_preserved_sources"] = source_ordered_names(empty_refresh_preserved_sources, enabled_sites)
    payload["listings"] = listings
    return payload


def main() -> None:
    args = parse_args()
    sites = json.loads(SITES.read_text(encoding="utf-8"))
    enabled_sites = [s for s in sites if s.get("enabled", True)]
    selected_sites, rotation_info = select_run_sites(args, enabled_sites)
    preserve_existing = args.preserve_existing if args.preserve_existing is not None else args.rotate

    if not selected_sites:
        raise SystemExit("No sources selected")
    if rotation_info:
        site = selected_sites[0]
        print(
            f"Rotation selected {site['name']} "
            f"({rotation_info['rotation_index'] + 1}/{rotation_info['rotation_total']}, key={rotation_info['rotation_key']})"
        )
    elif len(selected_sites) != len(enabled_sites):
        print(f"Scraping selected sources: {', '.join(site['name'] for site in selected_sites)}")
    else:
        print("Scraping all enabled sources")

    refreshed_by_id, scraped_counts = scrape_selected_sites(selected_sites)
    scraped_sources = {site["name"] for site in selected_sites}
    enabled_sources = {site["name"] for site in enabled_sites}

    if preserve_existing:
        listings, preserved_sources, empty_refresh_preserved_sources = merge_listings(
            load_existing_data(),
            refreshed_by_id,
            scraped_counts,
            scraped_sources,
            enabled_sources,
        )
    else:
        listings = list(refreshed_by_id.values())
        preserved_sources = set()
        empty_refresh_preserved_sources = set()

    listings = sort_listings(listings)
    payload = output_payload(
        listings=listings,
        enabled_sites=enabled_sites,
        selected_sites=selected_sites,
        preserved_sources=preserved_sources,
        empty_refresh_preserved_sources=empty_refresh_preserved_sources,
        rotation_info=rotation_info,
        preserve_existing=preserve_existing,
    )
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Wrote {OUT} with {len(listings)} listings")
    print(f"Scraped sources: {', '.join(payload['scraped_sources']) or 'none'}")
    if payload["preserved_sources"]:
        print(f"Preserved sources: {', '.join(payload['preserved_sources'])}")
    if payload.get("empty_refresh_preserved_sources"):
        print(f"Preserved empty refresh sources: {', '.join(payload['empty_refresh_preserved_sources'])}")


if __name__ == "__main__":
    main()

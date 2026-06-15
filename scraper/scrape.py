#!/usr/bin/env python3
"""Site-specific public-page meteorite inventory scraper."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
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
    r"northwest africa|"
    r"sikhote|gibeon|campo|diablo|tektite|moldavite|eucrite|diogenite|howardite|"
    r"shergottite|nakhlite|aubrite|ureilite|angrite|mesosiderite|octahedrite|ataxite|"
    r"\b(?:IIA|IAB|IIAB|IIIAB|IVA|IVB|IIE|IRUNGR|EUC)\b",
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
    ("iron", r"\b(iron meteorite|octahedrite|ataxite|hexahedrite|sikhote|campo del cielo|canyon diablo|gibeon|muonionalusta|seymchan|IIA|IAB|IIAB|IIIAB|IVA|IVB|IIE|IRUNGR|I\s*C)\b"),
    ("carbonaceous chondrite", r"\b(carbonaceous|c\s?2|cv\s?3|cvred\s?3|cvox[a-z]?\s?3|cm\s?2|ci\s?1|co\s?3|cr\s?2|ck|c3-?ung|c2-?ung|c1-?ung)\b"),
    ("ordinary chondrite", r"\b(ordinary chondrite|oc|h\s?[3-6](?:\.\d)?|h/l\s?3?|l\s?[3-6](?:\.\d)?|ll\s?[3-7](?:\.\d)?|l\s?\(\s?ll\s?\)\s?3|h/l|l/ll|H|L|LL)\b"),
    ("achondrite", r"\b(achondrite|eucrite|EUC|diogenite|howardite|hed\b|ureilite|aubrite|angrite|acapulcoite|lodranite|winonaite)\b"),
    ("chondrite", r"\b(chondrite|chondritic)\b"),
    ("tektite/impactite", r"\b(tektite|moldavite|libyan desert glass|impactite|impact melt)\b"),
]
SUBTYPE_RE = re.compile(
    r"\b(H|L|LL)\s*-?\s*([3-6](?:\.\d)?)\b|"
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
BAD_IMAGE_RE = re.compile(r"favicon|ajax-loader|logo|spinner|counter", re.I)
POSTBACK_RE = re.compile(r"__doPostBack\('([^']*)','([^']*)'\)")
METEORLAB_LOOSE_PRICE_RE = re.compile(r"\b(?:g|gr|grs|grams?)\b\s*,?\s+([0-9][0-9,]*(?:\.[0-9]{2}))\b", re.I)


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
        r"\b(?:NWA\s*\d+|Northwest Africa\s*\d+|H\s?[3-6](?:\.\d)?|H/L\s?3?|L\s?[3-6](?:\.\d)?|LL\s?[3-7](?:\.\d)?|L\s?\(\s?LL\s?\)\s?3|OC|C\s?2|CM\s?2|CV\s?3|CVred\s?3|CVoxA\s?3|CO\s?3|CR\s?2|CI\s?1|R\s?[3-6]|IIA|IAB|IIAB|IIIAB|IVA|IVB|IIE|IRUNGR|EUC|eucrite|diogenite|howardite|ureilite|aubrite|angrite|shergottite|nakhlite|pallasite|mesosiderite|iron)\b",
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


def meteorlab_row_cells(row) -> list[str]:
    return [clean(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"], recursive=False)]


def meteorlab_title(raw_title: str) -> str:
    title = clean(raw_title)
    title = re.sub(r"\b(?:Image|Images?)\b.*$", "", title, flags=re.I)
    title = re.split(
        r"\b(?:Fell|Found|Purchased|Recovered|Classified|A shower|A single|Single stone|TKW|Total known weight|One stone)\b",
        title,
        maxsplit=1,
        flags=re.I,
    )[0]
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
    start_weight = re.match(r"^\s*([0-9]+(?:[,.][0-9]+)?)\s*(g|gr|grs|grams?)\b", price_text, re.I)
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


def meteorlab_items_from_rows(site: dict, page_url: str, soup: BeautifulSoup, log: SourceLog) -> list[dict]:
    listings = []
    last_item_cells: list[str] = []
    item_index = 0

    for row in soup.find_all("tr"):
        cells = meteorlab_row_cells(row)
        if not cells:
            continue
        nonempty = [cell for cell in cells if cell]
        row_text = " ".join(nonempty)
        if len(cells) <= 2 and len(row_text) > 500:
            continue

        price_like = any(PRICE_RE.search(cell) or (WEIGHT_RE.search(cell) and METEORLAB_LOOSE_PRICE_RE.search(cell)) or re.search(r"\bSOLD\b", cell, re.I) for cell in cells)
        if price_like and len(cells) == 1 and len(last_item_cells) > 1:
            continue
        if price_like and last_item_cells:
            for idx, price_text in enumerate(cells):
                if not price_text:
                    continue
                title_text = last_item_cells[idx] if idx < len(last_item_cells) else ""
                if not title_text:
                    continue
                context = clean(f"{title_text} {price_text}")
                if re.search(r"\bSOLD\b|email for price", context, re.I):
                    log.reject("meteorlab_sold_or_missing_price")
                    continue
                price, currency = meteorlab_price(price_text)
                if price is None:
                    log.reject("meteorlab_missing_price")
                    continue
                title = meteorlab_title(title_text)
                if not title:
                    log.reject("meteorlab_missing_title")
                    continue
                if not METEORITE_RE.search(title) and METEORITE_RE.search(title_text):
                    title = f"{title} meteorite"
                weight = meteorlab_weight(title_text, price_text)
                item = make_listing(
                    site,
                    page_url,
                    title,
                    price=price,
                    currency=currency or "USD",
                    weight_g=weight,
                    detail_text=context,
                    explicit_type=None,
                    image_url=None,
                    item_key=f"{item_index}:{idx}:{title}:{weight}:{price}",
                    available=True,
                    parser="meteorlab",
                )
                if item:
                    listings.append(item)
                    log.parsed_listing()
                    item_index += 1
                else:
                    log.reject("make_listing_filtered")
            continue

        if not price_like and any(METEORITE_RE.search(cell) or WEIGHT_RE.search(cell) for cell in nonempty):
            last_item_cells = cells

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
    return scrape_generic(site, log)


def main() -> None:
    sites = json.loads(SITES.read_text(encoding="utf-8"))
    by_id = {}
    enabled_sites = [s for s in sites if s.get("enabled", True)]
    for site in enabled_sites:
        log = SourceLog(site)
        print(f"Scraping {site['name']} with {site.get('parser', 'generic')} parser")
        for item in scrape_site(site, log):
            by_id[item["id"]] = item
        log.summary()
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

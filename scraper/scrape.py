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
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SITES = ROOT / "data" / "sites.json"
OUT = ROOT / "data" / "listings.json"
UA = "MeteoriteMetaSearchBot/0.3 (+https://github.com/rayborg/meteorite-meta-search)"
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
DELAY = 2.0
MAX_INDEX_PAGES_PER_SITE = 80
MAX_DETAIL_PAGES_PER_SITE = 300
MAX_SHOPIFY_PAGES_PER_SITE = 4
SHOPIFY_PRODUCTS_PER_SITE_CAP = MAX_SHOPIFY_PAGES_PER_SITE * 250
SHOPIFY_JSON_RETRIES = 3

METEORITE_RE = re.compile(
    r"meteorite|chondrite|achondrite|pallasite|lunar|martian|nwa\s*\d+|"
    r"northwest africa|"
    r"sikhote|gibeon|campo|diablo|tektite|moldavite|eucrite|diogenite|howardite|"
    r"shergottite|nakhlite|aubrite|ureilite|angrite|mesosiderite|octahedrite|ataxite|"
    r"saffordite|"
    r"\b(?:IIA|IAB|IIAB|IIIAB|IVA|IVB|IIE|IRUNGR|EUC)\b",
    re.I,
)
WEIGHT_NUMBER_RE = r"(?:[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+(?:[,.][0-9]+)?|[,.][0-9]+)"
WEIGHT_RE = re.compile(
    rf"(?<![0-9A-Za-z])({WEIGHT_NUMBER_RE})\s*(kg|kilograms?|g|gm|gms|gr|grs|grams?|mg|milligrams?|oz|ounces?)\b",
    re.I,
)
WEIGHT_RANGE_RE = re.compile(
    rf"(?<![0-9A-Za-z])(?:{WEIGHT_NUMBER_RE}\s*(?:kg|kilograms?|g|gm|gms|gr|grs|grams?|mg|milligrams?|oz|ounces?)|[0-9]+[,.][0-9]+|[,.][0-9]+)\s*"
    rf"(?:-|\u2013|\u2014|to)\s*{WEIGHT_NUMBER_RE}\s*(?:kg|kilograms?|g|gm|gms|gr|grs|grams?|mg|milligrams?|oz|ounces?)\b",
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
    ("iron", r"\b(iron\s+meteorites?|octahedrite|ataxite|hexahedrite|sikhote|campo del cielo|canyon diablo|gibeon|muonionalusta|seymchan|IIA|IAB|IIAB|IIIAB|IVA|IVB|IIE|IRUNGR|I\s*C)\b"),
    ("carbonaceous chondrite", r"\b(carbonaceous|c\s?2|cv\s?3|cvred\s?3|cvox[a-z]?\s?3|cm\s?2|ci\s?1|co\s?3|cr\s?2|ck\s?\d?|ch\s?\d?|cb\s?[ab]?|c3-?ung|c2-?ung|c1-?ung)\b"),
    ("ordinary chondrite", r"\b(ordinary chondrite|oc|h\s?[3-6](?:\.\d)?(?:\s*[/\-]\s*[3-6](?:\.\d)?)?|h/l\s?3?|l\s?[3-6](?:\.\d)?(?:\s*[/\-]\s*[3-6](?:\.\d)?)?|ll\s?[3-7](?:\.\d)?(?:\s*[/\-]\s*[3-7](?:\.\d)?)?|l\s?\(\s?ll\s?\)\s?3|h/l|l/ll|H|L|LL)\b"),
    ("achondrite", r"\b(achondrite|brachinite|eucrite|EUC|diogenite|howardite|hed\b|ureilite|aubrite|angrite|acapulcoite|lodranite|winonaite)\b"),
    ("chondrite", r"\b(chondrite|chondritic)\b"),
    ("stone", r"\bstone\s*\([^)]*\)|\bmeteorite\s+type\s*:\s*stone\b"),
    ("tektite/impactite", r"\b(tektite|moldavite|libyan desert glass|impactite|impact melt|saffordite)\b"),
]
SUBTYPE_RE = re.compile(
    r"\b(H|L|LL)\s*-?\s*([3-7](?:\.\d)?(?:\s*[/\-]\s*[3-7](?:\.\d)?)?)\b|"
    r"\b(L\s?\(\s?LL\s?\)\s?3|L\s*-\s*melt breccia|LL\s?7)\b|"
    r"\b(CBa|CBb)\b|"
    r"\b(CI|CM|CO|CV|CR|CK|CH|CB)\s*-?\s*(\d(?:\.\d)?)\b|"
    r"\b(C)\s*-?\s*(2)\b|"
    r"\b(CVred|CVoxA)\s*-?\s*3\b|"
    r"\b(OC|H/L\s?3?)\b|"
    r"\b(R)\s*-?\s*([3-6](?:\s*-\s*[3-6])?)\b|"
    r"\b(EH|EL)\s*-?\s*([3-7])\b|"
    r"\b(IIA|IAB|IIAB|IIIAB|IVA|IVB|IIE|IRUNGR|I\s*C)\b|"
    r"\b(HED|EUC|eucrite|diogenite|howardite|ureilite|aubrite|angrite|brachinite|shergottite|nakhlite|chassignite|octahedrite|ataxite|hexahedrite|acapulcoite|lodranite|winonaite|mesosiderite|achondrite(?:-ung)?)\b",
    re.I,
)
BAD_IMAGE_RE = re.compile(r"favicon|ajax-loader|logo|spinner|counter|placeholder|heart/(?:dis|en)abled|sold\.jpg|red(?:%20|\s)*dot", re.I)
PRODUCT_DETAIL_STOP_RE = re.compile(r"^(?:Related products|Related items|Shopping cart|You may also like|Recently viewed)$", re.I)
PRODUCT_LABEL_BOUNDARY_RE = re.compile(
    r"\s+(?:Weight|Measurements?|Approximate Measurements?|Dimensions?|Size|Category|Categories|Availability|Price|SKU)\s*:",
    re.I,
)
POSTBACK_RE = re.compile(r"__doPostBack\('([^']*)','([^']*)'\)")
METEORLAB_LOOSE_PRICE_RE = re.compile(r"\b(?:g|gm|gms|gr|grs|grams?)\b\s*,?\s+([0-9][0-9,]*(?:\.[0-9]{2}))\b", re.I)
SOLD_STATUS_RE = re.compile(r"\b(on\s+hold|reserved|unavailable)\b|\bsold\b(?![\s-]+by\b)(?:\s+out\b)?", re.I)
EMAIL_PRICE_RE = re.compile(r"\bemail\s+for(?:\s+new)?\s+price\b", re.I)
NON_SPECIMEN_PRODUCT_RE = re.compile(
    r"\b(?:jewelry|jewellery|pendants?|rings?|necklaces?|bracelets?|earrings?|beads?|cabochons?|"
    r"watches?|cufflinks?|dog\s*tags?|knives?|book|books|posters?|prints?|shirts?|t-?shirts?|"
    r"apparel|mugs?|stands?|display\s+(?:cases?|boxes?|stands?|frames?)|(?:in|with)\s+(?:a\s+)?(?:floating\s+)?frames?|spheres?|riker|equipment|gifts?|gift\s*cards?|"
    r"souvenirs?|catalog(?:ue)?s?|guides?|magazines?|dvds?|vials?|dust|stickers?|sets?|lots?|"
    r"matched[-_\s]+pairs?|roof[-_\s]+panels?)\b",
    re.I,
)
ARIZONA_NON_SPECIMEN_RE = re.compile(
    r"\b(?:jewelry|jewellery|rings?|watches?|cufflinks?|dog\s*tags?|knives?|dust|vials?|"
    r"display\s+(?:boxes?|frames?)|(?:in|with)\s+(?:a\s+)?(?:floating\s+)?frames?|spheres?|fossils?|minerals?|collectibles?|military|samurai|swords?|relics?|"
    r"paintings?|prints?|art|teeth|tusks?|trilobites?|petrified\s+wood|dinosaurs?|gifts?)\b",
    re.I,
)
ARIZONA_BAD_IMAGE_RE = re.compile(
    r"favicon|logo|seal|bbb|AZ_Skies_MiniMe|Moon\.jpg|Mars\.jpg|Lunar-Meteorite-Display-Box|"
    r"Meteorite-Star-Dust|Star-Dust|Dust-Vials",
    re.I,
)
ARIZONA_FOOTER_START_RE = re.compile(
    r"^(?:To place your order|Arizona Skies Meteorites|Fossils & Meteorites For Sale|"
    r"To See other wonderful|We accept|We can accept)\b",
    re.I,
)
IMPACTIKA_API_PER_PAGE = 10
IMPACTIKA_API_TIMEOUT = 90
IMPACTIKA_API_RETRIES = 3
IMPACTIKA_AMBIGUOUS_ROW_RE = re.compile(
    r"\b(?:lots?|sets?|groups?|collections?|assort(?:ed|ment)|several|many|multiple|"
    r"choose|choice|sizes?|weights?|pieces?\s+(?:available|from|between)|"
    r"fragments?\s+(?:available|from|between)|slices?\s+(?:available|from|between)|"
    r"per\s+(?:gram|g)|/\s*(?:gram|g)\b|from\s+\$|starting\s+at)\b|"
    rf"\b(?:from|between)\s+{WEIGHT_NUMBER_RE}\s*(?:kg|kilograms?|g|gm|gms|gr|grs|grams?|mg|milligrams?|oz|ounces?)\s*"
    rf"(?:to|and|-|\u2013)\s*{WEIGHT_NUMBER_RE}\s*(?:kg|kilograms?|g|gm|gms|gr|grs|grams?|mg|milligrams?|oz|ounces?)\b|"
    rf"\b{WEIGHT_NUMBER_RE}\s*(?:kg|kilograms?|g|gm|gms|gr|grs|grams?|mg|milligrams?|oz|ounces?)\s*"
    rf"(?:to|-|\u2013)\s*{WEIGHT_NUMBER_RE}\s*(?:kg|kilograms?|g|gm|gms|gr|grs|grams?|mg|milligrams?|oz|ounces?)\b",
    re.I,
)
METEORITE_EXCHANGE_NON_SPECIMEN_RE = re.compile(
    r"\b(?:jewelry|jewellery|pendants?|rings?|necklaces?|bracelets?|earrings?|beads?|cabochons?|"
    r"stands?|display\s*(?:stands?|cases?|boxes?|frames?)?|(?:in|with)\s+(?:a\s+)?(?:floating\s+)?frames?|spheres?|riker|gifts?|gift\s*cards?|souvenirs?|"
    r"books?|posters?|prints?|shirts?|t-?shirts?|apparel|mugs?|equipment|catalog(?:ue)?s?|"
    r"dust|vials?|collection|collections?|sets?|lots?|filters?)\b",
    re.I,
)
AEROLITE_NON_INDIVIDUAL_RE = re.compile(r"matched[-_\s]*pairs?", re.I)
METEOLOVERS_NON_INDIVIDUAL_RE = re.compile(
    r"(?:^|[-_/])lots?(?:[-_/]|$)|\b(?:lots?|collections?|sets?|groups?|mixed|assort(?:ed|ment)|"
    r"multiple\s+(?:pieces?|specimens?|individuals?)|small\s+individuals|"
    r"choose[-_\s]*(?:your|a)[-_\s]*(?:pieces?|specimens?|slices?|fragments?)|"
    r"variable[-_\s]*(?:pieces?|specimens?|weights?|sizes?)|many\s+(?:pieces?|specimens?|slices?|fragments?)|"
    rf"(?:pieces?|specimens?|slices?|fragments?)\s+from\s+{WEIGHT_NUMBER_RE}\s*(?:to|-|\u2013)\s*{WEIGHT_NUMBER_RE}\s*(?:kg|kilograms?|g|gm|gms|gr|grs|grams?|mg|milligrams?|oz|ounces?)|"
    r"roof[-_\s]+panels?|broken[-_\s]+roof|"
    r"\d+\s+(?:pieces?|individuals?|fragments?|slices?|endcuts?)\b.*\b\d+\s+(?:pieces?|individuals?|fragments?|slices?|endcuts?)|"
    r"(?:slices?|endcuts?|individuals?)\s*,\s*(?:\d+\s+)?(?:slices?|endcuts?|individuals?)|"
    r"(?:slices?|endcuts?)\s*(?:and|,)\s*(?:slices?|endcuts?))\b",
    re.I,
)
JUSTMETEORITES_NON_SPECIMEN_RE = re.compile(
    r"\b(?:jewelry|jewellery|pendants?|rings?|necklaces?|bracelets?|earrings?|beads?|books?|"
    r"knives?|posters?|prints?|display\s+(?:cases?|boxes?|stands?|frames?)|(?:in|with)\s+(?:a\s+)?(?:floating\s+)?frames?|spheres?|riker|gift|souvenirs?|vials?|dust|sets?|lots?)\b",
    re.I,
)
GALACTIC_STONE_NON_SPECIMEN_RE = re.compile(
    r"\b(?:collections?|collector\s+lots?|lots?|sets?|jewelry|jewellery|pendants?|rings?|"
    r"necklaces?|bracelets?|earrings?|beads?|displays?|display\s+(?:cases?|boxes?|stands?|frames?)|(?:in|with)\s+(?:a\s+)?(?:floating\s+)?frames?|spheres?|"
    r"memorabilia|souvenirs?|glass\s+vials?|vials?|dust|sample\s+cards?|faux\s+meteorites?|"
    r"meteorwrongs?|replicas?|stickers?|pins?)\b",
    re.I,
)
GALACTIC_STONE_TITLE_METEORITE_RE = re.compile(
    r"\b(?:meteorite|chondrite|achondrite|pallasite|lunar|martian|shergottite|nakhlite|"
    r"eucrite|diogenite|howardite|aubrite|ureilite|angrite|mesosiderite|octahedrite|"
    r"ataxite|tektite|moldavite|impactite|nwa\s*\d+|northwest\s+africa\s*\d+|"
    r"(?:H|L|LL|EH|EL|R|CK|CM|CV|CO|CR|CI)\s*-?\s*\d(?:\.\d)?|"
    r"IAB|IIAB|IIIAB|IVA|IVB|IIE|IRUNGR|HED|EUC)\b",
    re.I,
)
SHOPIFY_PLACEHOLDER_PRICE_RE = re.compile(r"\b(price\s+on\s+request|contact\s+for\s+price|call\s+for\s+price)\b", re.I)
NON_INDIVIDUAL_WEIGHT_CONTEXT_RE = re.compile(
    r"\b(?:total|tkw|known|fall|fell|found|recovered|largest|main\s+mass|dimensions?|measures?|"
    r"display|shipping|million|years?|crater|area|strewn|shower|approximately\s+[0-9.]+\s*(?:cm|mm|inches?))\b",
    re.I,
)
METEORLAB_BAD_IMAGE_RE = re.compile(
    r"favicon|ajax-loader|logo|spinner|counter|meteor50|red(?:%20|\s)*dot|sold\.jpg|frontis|wid%2012|micro%20enhanced",
    re.I,
)
METEORLAB_NON_SPECIMEN_WEIGHT_RE = re.compile(
    r"total|tkw|known|found|recovered|single mass|totalling|weighing|mass of|fell|fall|shower",
    re.I,
)
METEORLAB_TITLE_FIXES = [
    (re.compile(r"\bA\s+ll\s+ende\b", re.I), "Allende"),
    (re.compile(r"\bC\s+umberland\b", re.I), "Cumberland"),
    (re.compile(r"\bSikhote\s+Alin\b", re.I), "Sikhote-Alin"),
]
METEORLAB_CLASS_START_RE = re.compile(
    r"\b(?:ordinary\s+chondrite|carbonaceous\s+chondrite|enstatite\s+chondrite|rumuruti\s+chondrite|"
    r"primitive\s+achondrite|achondrite|chondrite(?:-ung)?|brachinite|acapulcoite|aubrite|diogenite|"
    r"eucrite|howardite|angrite|ureilite|shergottite|nakhlite|pallasite|mesosiderite|stony[- ]iron|"
    r"iron\s+meteorite|tektite|moldavite|impact[- ]?melt|impactite|meteorite|AEUC-M|ADIO|ANGR|"
    r"EUC|MES-A4|PMG|PAL-MG|HED|OC|IAB|IIAB|IIIAB|IVA|IVB|IIE|IIF|IRUNGR|"
    r"(?:H|L|LL|EL|EH|R|CK|CM|CV|CO|CR|CI)\s*-?\s*\d(?:\.\d)?(?:\s*[/\-]\s*\d(?:\.\d)?)?)\b",
    re.I,
)
METEORLAB_LOCATION_START_RE = re.compile(
    r"\b(?:North\s*west\s+Africa|Northwest\s+Africa|Western\s+Australia|South\s+Australia|"
    r"New\s+South\s+Wales|Northern\s+Territory|Nullarbor\s+Plain|Atacama(?:\s+Desert)?|"
    r"Buenos\s+Aires(?:\s+province)?|Santa\s+Fe(?:\s+Province)?|Santiago\s+del\s+Estero|"
    r"Rio\s+Negro(?:\s+Province)?|Rio\s+de\s+Oro|Jiddat\s+al\s+Harasis|Al\s+Wusta|"
    r"Casas\s+Grandes|Kem\s+Kem\s+Region|Occidental\s+Saharan\s+desert|"
    r"Chihuahua|Sonora|Aldama|Tatawin|Tatahouine|Madaniyin|Temara|Zagora|Tagounite|Erfoud|"
    r"Tindouf|Mali|Chubut|Antofagasta|Hidalgo|Jacala|Vendee|Indre|Charente|Saskatchewan|"
    r"Punjab|Nurpur|Piemonte|East\s+Java|Equatoria|Cunere|Matabeleland\s+North|Zemgale|"
    r"Old\s+Castillia|Burgos|"
    r"Morocco|Algeria|Libya|Burkina\s+Faso|Tunisia|Oman|Canada|Nigeria|Uruguay|Ukraine|"
    r"Poland|France|Brazil|Pakistan|Niger|Norway|Turkey|China|Tanzania|Peru|Romania|Italy|"
    r"Indonesia|South\s+Sudan|Angola|Zimbabwe|Latvia|Spain|"
    r"Chile|Argentina|Mexico|Australia|USA|Kenya|Tasmania|Queensland|Victoria|Texas|"
    r"Oklahoma|Nebraska|Kansas|Colorado|New\s+Mexico|Arizona|Missouri|Iowa|South\s+Dakota|Ohio|"
    r"Florida|Idaho|Wyoming|Arkansas|Tennessee|North\s+Dakota|Utah|Nevada|Kentucky)\b",
    re.I,
)
METEORLAB_ADMIN_WORD_RE = re.compile(r"\b(?:County|Co\.?|district|Station|Plain|Desert|Region|Province|Municipality)\b", re.I)
METEORLAB_MULTIWORD_ADMIN_PREFIXES = {"val", "de", "del", "santa", "san", "rio", "los", "new", "north", "south", "western", "northern", "st", "rural"}


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
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    text = re.sub(r"\s+([)\]])", r"\1", text)
    return text


def lines_from(soup: BeautifulSoup) -> list[str]:
    return [clean(x) for x in soup.get_text("\n", strip=True).splitlines() if clean(x)]


def product_main_lines(lines: list[str]) -> list[str]:
    main_lines = []
    for line in lines:
        if PRODUCT_DETAIL_STOP_RE.match(line):
            break
        main_lines.append(line)
    return main_lines


def product_scope(soup: BeautifulSoup):
    for selector in [
        "div[id^='product-'].product.type-product",
        "div[id^='product-'].product",
        "div.product.type-product",
        ".productView",
        "main",
    ]:
        node = soup.select_one(selector)
        if node:
            return node
    return soup


def num(text: str | None) -> float | None:
    if not text:
        return None
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


def price_num(text: str | None, *, european: bool = False) -> float | None:
    if not text:
        return None
    value = text.replace("\xa0", "").strip()
    if european and re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?", value):
        value = value.replace(".", "").replace(",", ".")
    elif european and "," in value and "." not in value:
        value = value.replace(",", ".")
    else:
        value = value.replace(",", "")
    try:
        return float(value)
    except ValueError:
        return None


def fetch(
    url: str,
    log: SourceLog | None = None,
    kind: str = "page",
    session: requests.Session | None = None,
    headers: dict | None = None,
    timeout: int = 30,
) -> str | None:
    try:
        client = session or requests
        request_headers = {"User-Agent": UA, "Accept": "text/html"}
        if headers:
            request_headers.update(headers)
        r = client.get(url, headers=request_headers, timeout=timeout)
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


def fetch_json(
    url: str,
    log: SourceLog | None = None,
    kind: str = "api",
    headers: dict | None = None,
    session: requests.Session | None = None,
    timeout: int = 30,
):
    text = fetch(url, log, kind, session=session, headers={"Accept": "application/json", **(headers or {})}, timeout=timeout)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        if log:
            log.failed(url, f"{kind} JSON decode failed: {exc}")
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


def prices_in(text: str, *, european: bool = False) -> list[tuple[int, float, str]]:
    found = []
    for m in PRICE_RE.finditer(text):
        groups = m.groups()
        symbol = next((x for x in groups[0::2] if x), "$")
        amount = next((x for x in groups[1::2] if x), None)
        value = price_num(amount, european=european)
        if value is None:
            continue
        currency = "EUR" if symbol and symbol.upper() in {"EUR", "€"} else "USD"
        found.append((m.start(), value, currency))
    return found


def first_price(text: str, *, european: bool = False) -> tuple[float | None, str | None]:
    prices = prices_in(text, european=european)
    if not prices:
        return None, None
    _, value, currency = prices[0]
    return value, currency


def last_price(text: str, *, european: bool = False) -> tuple[float | None, str | None]:
    prices = prices_in(text, european=european)
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


def weight_range_spans(text: str) -> list[tuple[int, int]]:
    return [(match.start(), match.end()) for match in WEIGHT_RANGE_RE.finditer(text)]


def span_inside(span: tuple[int, int], ranges: list[tuple[int, int]]) -> bool:
    return any(start <= span[0] and span[1] <= end for start, end in ranges)


def first_weight_g(text: str) -> float | None:
    ranges = weight_range_spans(text)
    for m in WEIGHT_RE.finditer(text):
        if span_inside((m.start(), m.end()), ranges):
            continue
        value = num(m.group(1))
        if value is not None:
            return weight_to_g(value, m.group(2))
    return None


def first_individual_weight_g(title: str, detail_text: str = "", *, title_only: bool = False) -> float | None:
    weight = first_weight_g(title)
    if weight is not None:
        return weight
    if title_only:
        return None
    for match in WEIGHT_RE.finditer(detail_text):
        context = detail_text[max(0, match.start() - 70):match.end() + 70]
        if NON_INDIVIDUAL_WEIGHT_CONTEXT_RE.search(context):
            continue
        value = num(match.group(1))
        if value is not None:
            return weight_to_g(value, match.group(2))
    return None


def compact_classification_token(value: str | None) -> str:
    return re.sub(r"\s+", "", clean(value or "").upper())


def meteorite_type_for_subtype(subtype: str | None) -> str | None:
    token = clean(subtype or "").upper()
    compact = compact_classification_token(token)
    if not compact:
        return None
    if compact in {"OC", "H/L", "H/L3", "L(LL)3"} or re.fullmatch(r"(?:H|L|LL)-?[3-7](?:\.\d)?(?:[/\-][3-7](?:\.\d)?)?", compact):
        return "ordinary chondrite"
    if re.fullmatch(r"(?:CI|CM|CO|CV|CR|CK|CH|CB)-?\d(?:\.\d)?", compact) or compact in {"C2", "C-2", "CBA", "CBB"} or re.fullmatch(r"CVOX[A-Z]?3|CVRED3", compact):
        return "carbonaceous chondrite"
    if re.fullmatch(r"(?:EH|EL|R)-?[3-7](?:\.\d)?(?:-[3-7](?:\.\d)?)?", compact):
        return "chondrite"
    if re.fullmatch(r"(?:IIA|IAB|IIAB|IIIAB|IVA|IVB|IIE|IRUNGR|IC|OCTAHEDRITE|ATAXITE|HEXAHEDRITE)", compact):
        return "iron"
    if compact in {"PALLASITE"}:
        return "pallasite"
    if compact in {"MESOSIDERITE"}:
        return "mesosiderite"
    if compact in {"SHERGOTTITE", "NAKHLITE", "CHASSIGNITE"}:
        return "martian"
    if compact in {
        "HED",
        "EUC",
        "EUCRITE",
        "DIOGENITE",
        "HOWARDITE",
        "UREILITE",
        "AUBRITE",
        "ANGRITE",
        "BRACHINITE",
        "ACAPULCOITE",
        "LODRANITE",
        "WINONAITE",
        "ACHONDRITE",
        "ACHONDRITE-UNG",
    }:
        return "achondrite"
    return None


def meteorite_family_key(mtype: str | None) -> str | None:
    if mtype in {"ordinary chondrite", "carbonaceous chondrite", "achondrite", "iron", "pallasite", "mesosiderite"}:
        return mtype
    if mtype in {"lunar", "martian"}:
        return "achondrite"
    if mtype == "chondrite":
        return "chondrite"
    return None


def filtered_classification_text(ctext: str | None, mtype: str, subtype: str | None) -> str | None:
    if not ctext:
        return None
    target_family = meteorite_family_key(meteorite_type_for_subtype(subtype) or mtype)
    kept = []
    for bit in [clean(part) for part in ctext.split(",")]:
        if not bit:
            continue
        bit_family = meteorite_family_key(meteorite_type_for_subtype(bit))
        if target_family and bit_family and bit_family != target_family:
            continue
        if bit.lower() not in {value.lower() for value in kept}:
            kept.append(bit)
    return ", ".join(kept[:6]) or None


def normalized_classification(mtype: str, subtype: str | None, ctext: str | None) -> tuple[str, str | None, str | None]:
    subtype_type = meteorite_type_for_subtype(subtype)
    if subtype_type:
        mtype = subtype_type
    return mtype, subtype, filtered_classification_text(ctext, mtype, subtype)


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


def explicit_meteorite_type(schema_description: str, lines: list[str]) -> str | None:
    value = labeled_value(lines, "Meteorite Type")
    if not value:
        match = re.search(r"\bMeteorite\s+Type\s*:\s*(.+)", schema_description, re.I)
        if match:
            value = PRODUCT_LABEL_BOUNDARY_RE.split(match.group(1), 1)[0]
    value = clean(value)
    return value if value and not re.fullmatch(r"[-:]+", value) else None


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
        r"Stone\s*\([^)]*\)|\b(?:NWA\s*\d+|Northwest Africa\s*\d+|H\s?[3-6](?:\.\d)?(?:\s*[/\-]\s*[3-6](?:\.\d)?)?|H/L\s?3?|L\s?[3-6](?:\.\d)?(?:\s*[/\-]\s*[3-6](?:\.\d)?)?|LL\s?[3-7](?:\.\d)?(?:\s*[/\-]\s*[3-7](?:\.\d)?)?|L\s?\(\s?LL\s?\)\s?3|OC|C\s?2|CM\s?2|CV\s?3|CVred\s?3|CVoxA\s?3|CO\s?3|CR\s?2|CI\s?1|CK\s?\d|CH\s?\d|CBa|CBb|R\s?[3-6](?:\s*-\s*[3-6])?|IIA|IAB|IIAB|IIIAB|IVA|IVB|IIE|IRUNGR|EUC|eucrite|diogenite|howardite|ureilite|aubrite|angrite|brachinite|achondrite(?:-ung)?|shergottite|nakhlite|pallasite|mesosiderite|octahedrite|ataxite|hexahedrite)\b",
        text,
        re.I,
    ):
        bit = clean(m.group(0))
        if bit and bit.lower() not in {x.lower() for x in bits}:
            bits.append(bit)
    return normalized_classification(mtype, subtype, ", ".join(bits[:6]) or None)


def classify(title: str, detail_text: str = "", explicit_type: str | None = None) -> tuple[str, str | None, str | None]:
    priority_text = clean(" ".join(x for x in [title, explicit_type] if x))
    result = classify_from_text(priority_text)
    detail_result = classify_from_text(clean(f"{title} {detail_text[:900]}"))
    if result[0] != "unknown" or result[1]:
        if detail_result[1] or detail_result[2]:
            return normalized_classification(result[0], result[1] or detail_result[1], result[2] or detail_result[2])
        return result
    if detail_result[0] != "unknown" or detail_result[1] or detail_result[2]:
        return detail_result
    return result


def product_title_has_meteorite_marker(title: str) -> bool:
    return bool(METEORITE_RE.search(title) or SUBTYPE_RE.search(title) or GALACTIC_STONE_TITLE_METEORITE_RE.search(title))


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


def meteorlab_normalize_title_text(raw_title: str) -> str:
    title = clean(raw_title)
    for pattern, replacement in METEORLAB_TITLE_FIXES:
        title = pattern.sub(replacement, title)
    return clean(title)


def meteorlab_admin_location_start(title: str) -> int | None:
    for marker in METEORLAB_ADMIN_WORD_RE.finditer(title):
        before = title[:marker.start()].rstrip(" ,.;")
        words = list(re.finditer(r"[A-Za-z][A-Za-z'.-]*", before))
        if not words:
            continue
        start = words[-1].start()
        if len(words) >= 2 and words[-2].group(0).lower().rstrip(".") in METEORLAB_MULTIWORD_ADMIN_PREFIXES:
            start = words[-2].start()
        if start > 0:
            return start
    return None


def meteorlab_known_location_start(title: str) -> int | None:
    for match in METEORLAB_LOCATION_START_RE.finditer(title):
        if match.start() == 0:
            continue
        if title[match.start() - 1:match.start()] == "(":
            continue
        return match.start()
    return None


def meteorlab_name_only(title: str) -> str:
    title = re.sub(r"^([A-Za-z][A-Za-z'.-]+),\s*(\d{2,5})\b", r"\1 \2", title)
    nwa = re.match(r"^NWA\s*(\d+)\b", title, re.I)
    if nwa:
        return f"NWA {nwa.group(1)}"
    nwa_long = re.match(r"^North\s*west\s+Africa\s*(\d+)\b|^Northwest\s+Africa\s*(\d+)\b", title, re.I)
    if nwa_long:
        return f"Northwest Africa {next(group for group in nwa_long.groups() if group)}"

    title = re.sub(
        r"\s*[,;:]?\s*\b[0-9]+(?:[,.][0-9]+)?\s*(?:kg|kilograms?|g|gm|gms|gr|grs|grams?|mg|milligrams?|oz|ounces?)\b.*$",
        "",
        title,
        flags=re.I,
    )
    class_start = METEORLAB_CLASS_START_RE.search(title)
    if class_start and class_start.start() > 0:
        title = title[:class_start.start()]

    title = clean(title.strip(" .,-;:"))
    starts = [start for start in [meteorlab_admin_location_start(title), meteorlab_known_location_start(title)] if start]
    if starts:
        title = title[:min(starts)]

    title = clean(title.strip(" .,-;:"))
    title = re.sub(r"\s+\((?:Texas|Queensland|Colorado|Oklahoma|Nebraska|Australia|Canada)\)$", "", title, flags=re.I)
    title = re.sub(r"\(([a-z])\)", r"\1", title, flags=re.I)
    return clean(title.strip(" .,-;:"))


def meteorlab_title(raw_title: str) -> str:
    title = meteorlab_normalize_title_text(raw_title)
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
    title = meteorlab_name_only(title)
    if len(title) > 140:
        title = meteorlab_name_only(re.split(r"[.;]", title, maxsplit=1)[0])
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
    start_weight = re.match(rf"^\s*({WEIGHT_NUMBER_RE})\s*(g|gm|gms|gr|grs|grams?)\b", price_text, re.I)
    if start_weight:
        value = num(start_weight.group(1))
        return weight_to_g(value, start_weight.group(2)) if value is not None else None

    normalized_title_text = meteorlab_normalize_title_text(title_text)
    for match in reversed(list(WEIGHT_RE.finditer(normalized_title_text))):
        context = normalized_title_text[max(0, match.start() - 45):match.end() + 45]
        if METEORLAB_NON_SPECIMEN_WEIGHT_RE.search(context):
            continue
        value = num(match.group(1))
        if value is not None:
            return weight_to_g(value, match.group(2))

    price_matches = prices_in(price_text)
    price_pos = price_matches[-1][0] if price_matches else len(price_text)
    for match in reversed(list(WEIGHT_RE.finditer(price_text[:price_pos]))):
        context = price_text[max(0, match.start() - 45):match.end() + 45].lower()
        if METEORLAB_NON_SPECIMEN_WEIGHT_RE.search(context):
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
    stem = re.sub(r"\s+\d+\.\d+\b$", "", stem)
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
    image_title = meteorlab_title_from_image(image_url)
    if image_title and (
        not title
        or re.search(r"\{\s*short description", title, re.I)
        or title.lower().startswith(f"{image_title.lower()} ")
    ):
        title = image_title
        title_from_image = True
    if not title:
        log.reject("meteorlab_missing_title")
        return None
    if re.search(r"\breverse side\b", title_text, re.I):
        log.reject("meteorlab_reverse_side")
        return None
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


def product_detail_listing(
    site: dict,
    url: str,
    html: str,
    parser: str,
    log: SourceLog,
    fallback_type: str | None = None,
    *,
    reject_title_re: re.Pattern | None = None,
    title_weight_only: bool = False,
    title_or_labeled_weight_only: bool = False,
    allow_missing_price: bool = False,
    allow_missing_weight: bool = False,
    european_price: bool = False,
    ignore_text_sold: bool = False,
    reject_detail_re: re.Pattern | None = None,
    require_title_meteorite: bool = False,
    reject_weight_range_title: bool = False,
    allow_image_fallback: bool = True,
    detail_proof=None,
) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    product = schema_product(soup)
    offer = first_schema_offer(product)
    if detail_proof:
        proof_reject = detail_proof(soup, product, offer, url)
        if proof_reject:
            log.reject(proof_reject)
            return None
    for bad in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        bad.decompose()

    title = clean((product or {}).get("name") if isinstance((product or {}).get("name"), str) else "")
    if re.search(r"\b(?:autogenerated|product\s+title)\b", title, re.I):
        title = ""
    title = title or meta_content(soup, "og:title", "twitter:title") or title_for(soup)
    title = clean(
        re.sub(
            r"\s+(?:For\s+Sale\s*)?-\s+(?:FossilEra\.com|Aerolite Meteorites.*|Meteorite Exchange.*|justMETEORITES|Impactika|SkyFall Meteorites.*|Meteolovers).*$",
            "",
            title,
            flags=re.I,
        )
    )
    title = clean(title.strip(" -"))
    if reject_title_re and reject_title_re.search(title):
        log.reject("product_non_specimen_title")
        return None
    if reject_weight_range_title and WEIGHT_RANGE_RE.search(title):
        log.reject("product_weight_range_title")
        return None
    if require_title_meteorite and not product_title_has_meteorite_marker(title):
        log.reject("product_missing_title_meteorite_marker")
        return None
    scope = product_scope(soup)
    lines = product_main_lines(lines_from(scope))
    schema_description = clean((product or {}).get("description") if isinstance((product or {}).get("description"), str) else "")
    source_type = explicit_meteorite_type(schema_description, lines)
    text = "\n".join([x for x in [schema_description, *lines[:120]] if x])
    if reject_detail_re and reject_detail_re.search("\n".join([url, title, text[:2400]])):
        log.reject("product_non_individual_detail")
        return None
    availability = clean(str(offer.get("availability") or meta_content(soup, "product:availability") or ""))
    sold_text = False if ignore_text_sold else bool(SOLD_STATUS_RE.search(text[:800]))
    if re.search(r"outofstock|unavailable|discontinued", availability, re.I) or SOLD_STATUS_RE.search(availability) or sold_text or re.search(r"out of stock", text[:800], re.I):
        log.reject("product_unavailable")
        return None

    price = num(str(offer.get("price") or offer.get("lowPrice") or ""))
    currency = clean(str(offer.get("priceCurrency") or meta_content(soup, "product:price:currency") or "")) or None
    if price is None:
        price = num(meta_content(soup, "product:price:amount"))
    if price is None:
        price, currency_from_text = last_price(text, european=european_price)
        currency = currency or currency_from_text
    if price is None and not allow_missing_price:
        log.reject("product_missing_price")
        return None
    if price is not None and price <= 0:
        log.reject("product_nonpositive_price")
        return None

    if title_or_labeled_weight_only:
        weight = first_individual_weight_g(title, title_only=True) or labeled_weight(lines)
    elif title_weight_only:
        weight = first_individual_weight_g(title, title_only=True)
    else:
        weight = first_individual_weight_g(title, text[:2000]) or labeled_weight(lines)
    if weight is None and not title_weight_only:
        weight = first_individual_weight_g("", text[:2000])
    if weight is None and not allow_missing_weight:
        log.reject("product_missing_weight")
        return None

    image_url = schema_image_url(product, url) or meta_content(soup, "og:image", "twitter:image")
    if image_url:
        image_url = safe_http_url(url, image_url)
        if image_url and BAD_IMAGE_RE.search(image_url):
            image_url = None
    item = make_listing(
        site,
        url,
        title,
        price=price,
        currency=currency or "USD",
        weight_g=weight,
        detail_text=text,
        explicit_type=source_type or fallback_type,
        image_url=image_url or (image_for(scope, url) if allow_image_fallback else None),
        item_key=clean(str((product or {}).get("sku") or offer.get("sku") or title)),
        parser=parser,
    )
    if not item:
        log.reject("make_listing_filtered")
        return None
    log.parsed_listing()
    return item


def discover_product_cards(
    site: dict,
    log: SourceLog,
    detail_re: re.Pattern,
    card_selectors: list[str],
    *,
    headers: dict | None = None,
    card_reject_re: re.Pattern | None = None,
    card_filter=None,
    link_reject_re: re.Pattern | None = None,
) -> list[str]:
    details: dict[str, None] = {}
    queue = [urljoin(site["base_url"], url) for url in site.get("inventory_urls", [])]
    seen_indexes: set[str] = set()
    while queue and len(seen_indexes) < MAX_INDEX_PAGES_PER_SITE and len(details) < MAX_DETAIL_PAGES_PER_SITE:
        page_url = queue.pop(0).split("#", 1)[0]
        if page_url in seen_indexes:
            continue
        seen_indexes.add(page_url)
        log.index(page_url)
        html = fetch(page_url, log, "index", headers=headers)
        time.sleep(DELAY)
        if not html:
            log.reject_page("index_fetch_failed")
            continue
        soup = BeautifulSoup(html, "lxml")
        cards = []
        for selector in card_selectors:
            cards.extend(soup.select(selector))
        for card in cards:
            if len(details) >= MAX_DETAIL_PAGES_PER_SITE:
                break
            card_text = clean(card.get_text(" ", strip=True))
            card_classes = " ".join(card.get("class") or [])
            if SOLD_STATUS_RE.search(card_text) or re.search(r"out of stock|\boutofstock\b", f"{card_text} {card_classes}", re.I):
                log.reject("card_unavailable")
                continue
            if card_filter:
                filter_reject = card_filter(card, page_url)
                if filter_reject:
                    log.reject(filter_reject)
                    continue
            if card_reject_re and card_reject_re.search(card_text):
                log.reject("card_non_specimen")
                continue
            for a in card.find_all("a", href=True):
                href = urljoin(page_url, a.get("href")).split("#", 1)[0]
                if not same_domain(site["base_url"], href):
                    continue
                if re.search(r"add[-_]?to[-_]?cart|cart\.php|quickview|login|compare|search", href, re.I):
                    continue
                if link_reject_re and link_reject_re.search(href):
                    continue
                if detail_re.search(url_path_query(href)):
                    details[href] = None
                    log.detail(href)
                    break
        if len(details) >= MAX_DETAIL_PAGES_PER_SITE:
            break
        for rel_next in soup.find_all(["a", "link"], rel=re.compile("next", re.I)):
            href = rel_next.get("href")
            if href:
                next_url = urljoin(page_url, href).split("#", 1)[0]
                if same_domain(site["base_url"], next_url) and next_url not in seen_indexes and next_url not in queue:
                    queue.append(next_url)
        for a in soup.find_all("a", href=True):
            label = clean(a.get_text(" ", strip=True)).lower()
            classes = " ".join(a.get("class") or [])
            if not (label in {"next", "next page", ">", "\u00bb"} or re.search(r"\bnext\b|page-numbers", classes, re.I)):
                continue
            next_url = urljoin(page_url, a.get("href")).split("#", 1)[0]
            if same_domain(site["base_url"], next_url) and next_url not in seen_indexes and next_url not in queue:
                queue.append(next_url)
    return list(details.keys())


def scrape_product_card_details(
    site: dict,
    log: SourceLog,
    parser: str,
    detail_re: re.Pattern,
    card_selectors: list[str],
    fallback_type: str | None = None,
    *,
    headers: dict | None = None,
    card_reject_re: re.Pattern | None = None,
    reject_title_re: re.Pattern | None = None,
    title_weight_only: bool = False,
    title_or_labeled_weight_only: bool = False,
    allow_missing_price: bool = False,
    allow_missing_weight: bool = False,
    european_price: bool = False,
    reject_detail_re: re.Pattern | None = None,
    require_title_meteorite: bool = False,
    reject_weight_range_title: bool = False,
    card_filter=None,
    link_reject_re: re.Pattern | None = None,
    detail_proof=None,
) -> list[dict]:
    listings = []
    for url in discover_product_cards(
        site,
        log,
        detail_re,
        card_selectors,
        headers=headers,
        card_reject_re=card_reject_re,
        card_filter=card_filter,
        link_reject_re=link_reject_re,
    ):
        html = fetch(url, log, "detail", headers=headers)
        time.sleep(DELAY)
        if not html:
            log.reject_page("detail_fetch_failed")
            continue
        item = product_detail_listing(
            site,
            url,
            html,
            parser,
            log,
            fallback_type=fallback_type,
            reject_title_re=reject_title_re,
            title_weight_only=title_weight_only,
            title_or_labeled_weight_only=title_or_labeled_weight_only,
            allow_missing_price=allow_missing_price,
            allow_missing_weight=allow_missing_weight,
            european_price=european_price,
            reject_detail_re=reject_detail_re,
            require_title_meteorite=require_title_meteorite,
            reject_weight_range_title=reject_weight_range_title,
            detail_proof=detail_proof,
        )
        if item:
            listings.append(item)
    return listings


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    soup = BeautifulSoup(value, "lxml")
    return clean(soup.get_text(" ", strip=True))


def shopify_inventory_limit(inventory_url: str) -> int:
    query = dict(parse_qsl(urlparse(inventory_url).query, keep_blank_values=True))
    try:
        limit = int(query.get("limit") or 250)
    except ValueError:
        limit = 250
    return min(max(limit, 1), 250)


def shopify_page_limits(inventory_url: str) -> list[int]:
    limits = [shopify_inventory_limit(inventory_url)]
    for fallback in [100, 50]:
        if fallback < limits[0] and fallback not in limits:
            limits.append(fallback)
    return limits


def shopify_products_api_url(site: dict, inventory_url: str, page: int, limit: int | None = None) -> str:
    url = urljoin(site["base_url"], inventory_url)
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if not path.endswith("/products.json"):
        if "/collections/" in path:
            path = f"{path}/products.json"
        else:
            path = "/products.json"
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if limit is None:
        query.setdefault("limit", "250")
    else:
        query["limit"] = str(limit)
    query["page"] = str(page)
    return urlunparse((parsed.scheme, parsed.netloc, path, "", urlencode(query), ""))


def shopify_json_headers(site: dict) -> dict:
    return {
        "User-Agent": BROWSER_UA,
        "Accept": "application/json,text/javascript,*/*;q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": urljoin(site["base_url"], "/"),
    }


def fetch_shopify_json_page(api_url: str, log: SourceLog, session: requests.Session, headers: dict):
    for attempt in range(1, SHOPIFY_JSON_RETRIES + 1):
        log.index(api_url)
        data = fetch_json(api_url, log, "api", headers=headers, session=session)
        if data is not None:
            return data
        if attempt < SHOPIFY_JSON_RETRIES:
            time.sleep(DELAY * attempt)
    return None


def shopify_product_type(product: dict) -> str:
    return clean(str(product.get("product_type") or ""))


def shopify_tags(product: dict) -> list[str]:
    tags = product.get("tags") or []
    if isinstance(tags, str):
        return [clean(x) for x in tags.split(",") if clean(x)]
    if isinstance(tags, list):
        return [clean(str(x)) for x in tags if clean(str(x))]
    return []


def shopify_explicit_type(product: dict, *, include_keyword_tags: bool = True) -> str | None:
    bits = []
    ptype = shopify_product_type(product)
    if ptype:
        bits.append(ptype)
    for tag in shopify_tags(product):
        match = re.search(r"Meteorite Type-([^,]+)$", tag, re.I)
        if match:
            bits.append(clean(match.group(1)))
        elif include_keyword_tags and METEORITE_RE.search(tag):
            bits.append(tag)
    seen = []
    for bit in bits:
        if bit and bit.lower() not in {x.lower() for x in seen}:
            seen.append(bit)
    return ", ".join(seen[:5]) or None


def shopify_available_variant(product: dict) -> dict | None:
    variants = [variant for variant in product.get("variants") or [] if isinstance(variant, dict)]
    return next((variant for variant in variants if variant.get("available") is True), variants[0] if variants else None)


def shopify_image(product: dict) -> str | None:
    images = product.get("images") or []
    for image in images:
        src = image.get("src") if isinstance(image, dict) else None
        if src and not BAD_IMAGE_RE.search(src):
            return src
    return None


def shopify_listing(
    site: dict,
    parser: str,
    product: dict,
    log: SourceLog,
    source_filter,
) -> dict | None:
    variant = shopify_available_variant(product)
    if not variant or variant.get("available") is not True:
        log.reject("shopify_unavailable")
        return None

    title = clean(str(product.get("title") or ""))
    variant_title = clean(str(variant.get("title") or ""))
    if variant_title and not re.fullmatch(r"default\s+title", variant_title, re.I):
        title = clean(f"{title} - {variant_title}")
    tag_text = "" if parser == "top_meteorite" else " ".join(shopify_tags(product))
    detail_text = clean(" ".join([html_to_text(product.get("body_html")), shopify_product_type(product), tag_text]))
    price = price_num(str(variant.get("price") or ""))
    weight = first_individual_weight_g(title, detail_text[:2400])
    reason = source_filter(product, title, detail_text, price, weight, variant)
    if reason:
        log.reject(reason)
        return None

    url = urljoin(site["base_url"], f"/products/{product.get('handle')}")
    item = make_listing(
        site,
        url,
        title,
        price=price,
        currency="USD" if price is not None else None,
        weight_g=weight,
        detail_text=detail_text,
        explicit_type=shopify_explicit_type(product, include_keyword_tags=parser != "top_meteorite"),
        image_url=shopify_image(product),
        item_key=clean(str(variant.get("id") or product.get("id") or title)),
        parser=parser,
    )
    if not item:
        log.reject("make_listing_filtered")
        return None
    log.parsed_listing()
    return item


def scrape_shopify_products_json(site: dict, log: SourceLog, parser: str, source_filter) -> list[dict]:
    listings = []
    seen_products: set[str] = set()
    session = requests.Session()
    headers = shopify_json_headers(site)
    for inventory_url in site.get("inventory_urls", []):
        for limit in shopify_page_limits(inventory_url):
            failed = False
            completed = False
            max_pages = min(MAX_INDEX_PAGES_PER_SITE, max(MAX_SHOPIFY_PAGES_PER_SITE, (SHOPIFY_PRODUCTS_PER_SITE_CAP + limit - 1) // limit))
            for page in range(1, max_pages + 1):
                api_url = shopify_products_api_url(site, inventory_url, page, limit)
                data = fetch_shopify_json_page(api_url, log, session, headers)
                time.sleep(DELAY)
                if data is None:
                    log.reject_page("shopify_api_fetch_failed")
                    failed = True
                    break
                products = data.get("products") if isinstance(data, dict) else None
                if not products:
                    completed = True
                    break
                for product in products:
                    product_key = str(product.get("id") or product.get("handle") or "")
                    if not product_key or product_key in seen_products:
                        continue
                    seen_products.add(product_key)
                    item = shopify_listing(site, parser, product, log, source_filter)
                    if item:
                        listings.append(item)
                if len(products) < limit:
                    completed = True
                    break
            if completed or not failed:
                break
    return listings


def sitemap_product_urls(site: dict, log: SourceLog, *, headers: dict | None = None) -> list[str]:
    urls = []
    seen = set()
    for sitemap_url in site.get("inventory_urls", []):
        sitemap_url = urljoin(site["base_url"], sitemap_url)
        log.index(sitemap_url)
        xml = fetch(sitemap_url, log, "sitemap", headers=headers)
        time.sleep(DELAY)
        if not xml:
            log.reject_page("sitemap_fetch_failed")
            continue
        for url in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", xml, re.I):
            url = clean(url)
            if url and url not in seen:
                urls.append(url)
                seen.add(url)
    return urls


def meteorite_exchange_card_filter(card, page_url: str) -> str | None:
    classes = " ".join(card.get("class") or [])
    if re.search(r"\bproduct-category\b", classes, re.I):
        return "woo_category_card"
    if not re.search(r"\btype-product\b", classes, re.I):
        return "woo_card_missing_type_product"
    title_node = card.select_one(".woocommerce-loop-product__title, h2, h3")
    title = clean(title_node.get_text(" ", strip=True) if title_node else "")
    haystack = clean(" ".join([title, card.get_text(" ", strip=True), classes]))
    if WEIGHT_RANGE_RE.search(title):
        return "meteorite_exchange_weight_range_title"
    if METEORITE_EXCHANGE_NON_SPECIMEN_RE.search(haystack) or NON_SPECIMEN_PRODUCT_RE.search(haystack):
        return "meteorite_exchange_non_specimen"
    return None


def meteorite_exchange_detail_proof(soup: BeautifulSoup, product: dict | None, offer: dict, url: str) -> str | None:
    path = urlparse(url).path.lower()
    if not re.fullmatch(r"/[^/]+\.html", path):
        return "woo_not_root_product_html"
    body_classes = " ".join(soup.body.get("class") or []) if soup.body else ""
    if not re.search(r"\bsingle-product\b", body_classes, re.I):
        return "woo_missing_single_product_body"
    if re.search(r"\b(?:archive|tax-product_cat|post-type-archive|product-category|woocommerce-shop)\b", body_classes, re.I):
        return "woo_archive_page"
    product_node = soup.select_one("div[id^='product-'].product.type-product, div.product.type-product")
    if not product_node:
        return "woo_missing_type_product_detail"
    if clean(meta_content(soup, "og:type") or "").lower() != "product":
        return "woo_missing_product_meta"
    if not (meta_content(soup, "product:retailer_item_id") or product_node.select_one(".product_meta .sku, .product_meta .posted_in")):
        return "woo_missing_product_metadata"
    title = meta_content(soup, "og:title", "twitter:title") or title_for(soup)
    if WEIGHT_RANGE_RE.search(title):
        return "meteorite_exchange_weight_range_title_detail"
    category_text = clean(product_node.select_one(".product_meta").get_text(" ", strip=True) if product_node.select_one(".product_meta") else "")
    if METEORITE_EXCHANGE_NON_SPECIMEN_RE.search(clean(f"{title} {category_text}")):
        return "meteorite_exchange_non_specimen_detail"
    return None


def galactic_stone_card_filter(card, page_url: str) -> str | None:
    title = clean(str(card.get("data-name") or ""))
    if not title:
        title_node = card.select_one(".card-title")
        title = clean(title_node.get_text(" ", strip=True) if title_node else "")
    categories = clean(str(card.get("data-product-category") or ""))
    haystack = clean(f"{title} {categories}")
    if not card.get("data-entity-id"):
        return "galactic_card_missing_product_id"
    if not (card.select_one('[data-button-type="add-cart"]') or card.select_one('a[href*="cart.php?action=add"]')):
        return "galactic_card_not_add_to_cart"
    if GALACTIC_STONE_NON_SPECIMEN_RE.search(haystack) or NON_SPECIMEN_PRODUCT_RE.search(haystack):
        return "galactic_non_specimen"
    if first_weight_g(title) is None:
        return "galactic_missing_title_weight"
    if not product_title_has_meteorite_marker(title):
        return "galactic_missing_title_meteorite_marker"
    return None


def galactic_stone_detail_proof(soup: BeautifulSoup, product: dict | None, offer: dict, url: str) -> str | None:
    if clean(meta_content(soup, "platform") or "").lower() != "bigcommerce.stencil":
        return "bigcommerce_missing_platform_meta"
    product_view = soup.select_one('.productView[data-event-type="product"][data-entity-id]')
    if not product_view:
        return "bigcommerce_missing_product_view"
    if clean(meta_content(soup, "og:type") or "").lower() != "product":
        return "bigcommerce_missing_product_meta"
    title = clean(str(product_view.get("data-name") or meta_content(soup, "og:title", "twitter:title") or title_for(soup)))
    categories = clean(str(product_view.get("data-product-category") or ""))
    haystack = clean(f"{title} {categories}")
    if GALACTIC_STONE_NON_SPECIMEN_RE.search(haystack) or NON_SPECIMEN_PRODUCT_RE.search(haystack):
        return "galactic_non_specimen_detail"
    if first_weight_g(title) is None:
        return "galactic_missing_title_weight_detail"
    if not product_title_has_meteorite_marker(title):
        return "galactic_missing_title_meteorite_marker_detail"
    script_text = " ".join(script.get_text(" ", strip=True) for script in soup.find_all("script") if "BCData" in script.get_text(" ", strip=True))
    visible_status = clean(product_view.get_text(" ", strip=True)[:1200])
    if re.search(r'"(?:instock|purchasable)"\s*:\s*false|out\s+of\s+stock|unavailable', f"{script_text} {visible_status}", re.I):
        return "bigcommerce_unavailable"
    if not soup.select_one('form[data-cart-item-add] input[name="product_id"], #form-action-addToCart'):
        return "bigcommerce_missing_add_to_cart"
    return None


def scrape_meteorite_exchange(site: dict, log: SourceLog) -> list[dict]:
    detail_re = re.compile(r"/[^/#?]+\.html$", re.I)
    link_reject_re = re.compile(r"(?:[?&](?:add-to-cart|filter|orderby|min_price|max_price|rating_filter|s)=|/(?:cart|checkout|my-account)(?:/|$)|/product-category/|/feed/?$|/wp-json/)", re.I)
    return scrape_product_card_details(
        site,
        log,
        "meteorite_exchange",
        detail_re,
        ["li.product", ".wc-block-grid__product"],
        fallback_type="meteorite",
        card_reject_re=METEORITE_EXCHANGE_NON_SPECIMEN_RE,
        reject_title_re=METEORITE_EXCHANGE_NON_SPECIMEN_RE,
        reject_weight_range_title=True,
        card_filter=meteorite_exchange_card_filter,
        link_reject_re=link_reject_re,
        detail_proof=meteorite_exchange_detail_proof,
    )


def scrape_fossilera(site: dict, log: SourceLog) -> list[dict]:
    detail_re = re.compile(r"^/meteorites/[^/?#]+/?$", re.I)
    return scrape_product_card_details(
        site,
        log,
        "fossilera",
        detail_re,
        [".specimen-listing"],
        fallback_type="meteorite",
        card_reject_re=NON_SPECIMEN_PRODUCT_RE,
        reject_title_re=NON_SPECIMEN_PRODUCT_RE,
        title_or_labeled_weight_only=True,
    )


def scrape_aerolite(site: dict, log: SourceLog) -> list[dict]:
    detail_re = re.compile(r"^/product/[^/?#]+/?$", re.I)
    headers = {"User-Agent": BROWSER_UA, "Accept": "text/html,application/xhtml+xml"}
    return scrape_product_card_details(
        site,
        log,
        "aerolite",
        detail_re,
        ["li.product", ".wc-block-grid__product"],
        fallback_type="meteorite",
        headers=headers,
        card_reject_re=NON_SPECIMEN_PRODUCT_RE,
        reject_title_re=NON_SPECIMEN_PRODUCT_RE,
        reject_detail_re=AEROLITE_NON_INDIVIDUAL_RE,
    )


def scrape_meteolovers(site: dict, log: SourceLog) -> list[dict]:
    detail_re = re.compile(r"^/product/meteorites/[^?#]+/?$", re.I)
    return scrape_product_card_details(
        site,
        log,
        "meteolovers",
        detail_re,
        [".elementor .product", "li.product"],
        fallback_type="meteorite",
        card_reject_re=NON_SPECIMEN_PRODUCT_RE,
        reject_title_re=NON_SPECIMEN_PRODUCT_RE,
        european_price=True,
        reject_detail_re=METEOLOVERS_NON_INDIVIDUAL_RE,
    )


def scrape_galactic_stone(site: dict, log: SourceLog) -> list[dict]:
    detail_re = re.compile(r"^/(?!cart\.php|login\.php|search\.php|compare/?$)[a-z0-9][a-z0-9-]+/?$", re.I)
    return scrape_product_card_details(
        site,
        log,
        "galactic_stone",
        detail_re,
        ["article.card", ".card"],
        card_reject_re=GALACTIC_STONE_NON_SPECIMEN_RE,
        reject_title_re=GALACTIC_STONE_NON_SPECIMEN_RE,
        title_weight_only=True,
        reject_detail_re=GALACTIC_STONE_NON_SPECIMEN_RE,
        require_title_meteorite=True,
        card_filter=galactic_stone_card_filter,
        detail_proof=galactic_stone_detail_proof,
    )


def fossil_realm_filter(product: dict, title: str, detail_text: str, price: float | None, weight: float | None, variant: dict) -> str | None:
    if shopify_product_type(product).lower() != "meteorites":
        return "fossil_realm_non_meteorite_type"
    if SHOPIFY_PLACEHOLDER_PRICE_RE.search(detail_text) or price is None or price <= 0 or price >= 1_000_000:
        return "fossil_realm_placeholder_price"
    if first_weight_g(title) is None:
        return "fossil_realm_missing_title_weight"
    if NON_SPECIMEN_PRODUCT_RE.search(title) or SOLD_STATUS_RE.search(title):
        return "fossil_realm_non_specimen"
    return None


def scrape_fossil_realm(site: dict, log: SourceLog) -> list[dict]:
    return scrape_shopify_products_json(site, log, "fossil_realm", fossil_realm_filter)


def top_meteorite_filter(product: dict, title: str, detail_text: str, price: float | None, weight: float | None, variant: dict) -> str | None:
    if shopify_product_type(product).lower() != "specimen":
        return "top_non_specimen_type"
    if not (METEORITE_RE.search(title) or METEORITE_RE.search(detail_text)):
        return "top_missing_meteorite_keyword"
    if NON_SPECIMEN_PRODUCT_RE.search(title) or SOLD_STATUS_RE.search(title):
        return "top_non_specimen_title"
    if SHOPIFY_PLACEHOLDER_PRICE_RE.search(detail_text) or price is None or price <= 0 or price >= 1_000_000:
        return "top_missing_price"
    if first_weight_g(title) is None:
        return "top_missing_title_weight"
    return None


def scrape_top_meteorite(site: dict, log: SourceLog) -> list[dict]:
    return scrape_shopify_products_json(site, log, "top_meteorite", top_meteorite_filter)


def mini_museum_filter(product: dict, title: str, detail_text: str, price: float | None, weight: float | None, variant: dict) -> str | None:
    ptype = shopify_product_type(product).lower()
    if "meteorite" not in ptype or "jewelry" in ptype or "exhibits" in ptype or "complete collections" in ptype:
        return "mini_museum_non_specimen_type"
    if NON_SPECIMEN_PRODUCT_RE.search(title) or re.search(r"\b(?:tunguska|cards?|mini\s+museum|edition|amino\s+acids|death\s+of\s+the\s+dinosaurs|k-pg)\b", title, re.I):
        return "mini_museum_gift_or_mixed_item"
    if first_weight_g(title) is None:
        return "mini_museum_missing_title_weight"
    if weight is None:
        return "mini_museum_missing_weight"
    if price is None or price <= 0:
        return "mini_museum_missing_price"
    return None


def scrape_mini_museum(site: dict, log: SourceLog) -> list[dict]:
    return scrape_shopify_products_json(site, log, "mini_museum", mini_museum_filter)


def meteorite_market_page_title(soup: BeautifulSoup) -> str:
    title = title_for(soup)
    title = re.sub(r"\s+for Sale\b.*$", "", title, flags=re.I)
    return clean(title)


def scrape_meteorite_market(site: dict, log: SourceLog) -> list[dict]:
    listings = []
    seen_keys: set[tuple] = set()
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
                key = (item_id, weight, price, image_url)
                if key in seen_keys:
                    log.reject("meteorite_market_duplicate_cell")
                    continue
                seen_keys.add(key)
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


def arizona_bad_image_url(image_url: str | None) -> bool:
    return not image_url or bool(BAD_IMAGE_RE.search(image_url) or ARIZONA_BAD_IMAGE_RE.search(image_url))


def arizona_main_lines(soup: BeautifulSoup) -> list[str]:
    main_lines = []
    for line in lines_from(soup):
        if ARIZONA_FOOTER_START_RE.search(line):
            break
        main_lines.append(line)
    return main_lines


def arizona_clean_title(text: str) -> str:
    title = re.sub(r"\bPrice\s*:.*$", "", text, flags=re.I)
    title = re.sub(r"\b(?:NEW|SOLD)\s*!.*$", "", title, flags=re.I)
    title = re.sub(r"\s+For Sale\s*$", "", title, flags=re.I)
    return clean(title.strip(" !,.;"))


def arizona_exact_price(text: str) -> tuple[float | None, str | None]:
    for start, value, currency in prices_in(text):
        context = text[max(0, start - 60):start + 90]
        if re.search(r"\b(?:under|less\s+than|from|starting\s+at)\b|\bper\s+(?:vial|gram|g)\b|/\s*(?:gram|g)\b", context, re.I):
            continue
        if re.search(r"\b(?:price|available\s+for|only|sale\s+price)\b", context, re.I):
            return value, currency
    return None, None


def arizona_image_for(soup: BeautifulSoup, page_url: str) -> str | None:
    for img in soup.find_all("img"):
        image_url = safe_http_url(page_url, img.get("src"))
        if image_url and not arizona_bad_image_url(image_url):
            return image_url
    return None


def arizona_page_heading(soup: BeautifulSoup) -> str:
    for selector in ["h1", "title"]:
        node = soup.select_one(selector)
        if not node:
            continue
        heading = clean(node.get_text(" ", strip=True))
        heading = clean(re.split(r"\b(?:Price\s*:|To place your order|CONTACT)\b", heading, maxsplit=1, flags=re.I)[0])
        if heading and len(heading) <= 80:
            return heading
    return ""


def arizona_reject_text(text: str) -> bool:
    return bool(NON_SPECIMEN_PRODUCT_RE.search(text) or ARIZONA_NON_SPECIMEN_RE.search(text))


def arizona_link_nearby_text(link) -> str:
    parts = [clean(link.get_text(" ", strip=True))]
    for sibling in link.next_siblings:
        if getattr(sibling, "name", None) == "br":
            break
        value = clean(sibling.get_text(" ", strip=True) if hasattr(sibling, "get_text") else str(sibling))
        if value:
            parts.append(value)
        if len(" ".join(parts)) > 180:
            break
    return clean(" ".join(parts))


def arizona_candidate_links(site: dict, page_url: str, soup: BeautifulSoup, log: SourceLog) -> list[str]:
    links = []
    for a in soup.find_all("a", href=True):
        text = clean(a.get_text(" ", strip=True))
        nearby_text = arizona_link_nearby_text(a)
        href = urljoin(page_url, a.get("href")).split("#", 1)[0]
        if not same_domain(site["base_url"], href):
            continue
        path = urlparse(href).path
        haystack = clean(f"{path} {nearby_text}")
        if arizona_reject_text(haystack) or SOLD_STATUS_RE.search(nearby_text):
            continue
        if re.search(r"/Inexpensive_Meteorites_2/?$", path, re.I):
            links.append(href)
            log.detail(href)
            continue
        if not re.search(r"/AZ_Skies_Links/(?:Lunar|Martian)/", path, re.I):
            continue
        if WEIGHT_RE.search(text) and METEORITE_RE.search(text):
            links.append(href)
            log.detail(href)
        elif re.search(r"\bspecimens?\s+for\s+sale\b", text, re.I):
            links.append(href)
    return links


def arizona_listing_from_page(site: dict, url: str, html: str, log: SourceLog) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    for bad in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        bad.decompose()
    lines = arizona_main_lines(soup)
    text = "\n".join(lines)
    title_line = next(
        (
            arizona_clean_title(line)
            for line in lines
            if WEIGHT_RE.search(line) and METEORITE_RE.search(line) and not arizona_reject_text(line)
        ),
        "",
    )
    if not title_line:
        log.reject("arizona_not_final_specimen_page")
        return None
    if SOLD_STATUS_RE.search(text):
        log.reject("arizona_sold")
        return None
    price, currency = arizona_exact_price(text)
    weight = first_individual_weight_g(title_line, title_only=True)
    image_url = arizona_image_for(soup, url)
    if price is None or weight is None:
        log.reject("arizona_missing_price_or_weight")
        return None
    if arizona_bad_image_url(image_url):
        log.reject("arizona_missing_valid_image")
        return None
    page_title = arizona_page_heading(soup)
    title = title_line
    if page_title and page_title.lower() not in title.lower():
        title = clean(f"{page_title} - {title_line}")
    item = make_listing(
        site,
        url,
        title,
        price=price,
        currency=currency or "USD",
        weight_g=weight,
        detail_text=text,
        explicit_type="meteorite",
        image_url=image_url,
        item_key=f"{url}:{weight}:{price}",
        parser="arizona_skies",
    )
    if not item:
        log.reject("make_listing_filtered")
        return None
    log.parsed_listing()
    return item


def arizona_list_page_rows(site: dict, url: str, soup: BeautifulSoup, log: SourceLog) -> list[dict]:
    listings = []
    current_image = None
    seen_rows = set()
    for idx, node in enumerate(soup.find_all(["img", "font", "a"])):
        if node.name == "img":
            image_url = safe_http_url(url, node.get("src"))
            current_image = None if arizona_bad_image_url(image_url) else image_url
            continue
        line = clean(node.get_text(" ", strip=True))
        if not current_image or not (WEIGHT_RE.search(line) and PRICE_RE.search(line) and METEORITE_RE.search(line)):
            continue
        if line in seen_rows:
            continue
        seen_rows.add(line)
        if SOLD_STATUS_RE.search(line):
            log.reject("arizona_sold")
            continue
        title = arizona_clean_title(line)
        if not title or arizona_reject_text(title):
            log.reject("arizona_non_specimen")
            continue
        price, currency = arizona_exact_price(line)
        weight = first_individual_weight_g(title, title_only=True)
        if price is None or weight is None:
            log.reject("arizona_missing_price_or_weight")
            continue
        item = make_listing(
            site,
            url,
            title,
            price=price,
            currency=currency or "USD",
            weight_g=weight,
            detail_text=line,
            explicit_type="meteorite",
            image_url=current_image,
            item_key=f"row:{idx}:{title}:{weight}:{price}:{current_image}",
            parser="arizona_skies",
        )
        if item:
            listings.append(item)
            log.parsed_listing()
        else:
            log.reject("make_listing_filtered")
    return listings


def scrape_arizona_skies(site: dict, log: SourceLog) -> list[dict]:
    listings = []
    queue = [urljoin(site["base_url"], url) for url in site.get("inventory_urls", [])]
    seen = set()
    while queue and len(seen) < MAX_INDEX_PAGES_PER_SITE and len(listings) < MAX_DETAIL_PAGES_PER_SITE:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        log.index(url)
        html = fetch(url, log, "index")
        time.sleep(DELAY)
        if not html:
            log.reject_page("index_fetch_failed")
            continue
        soup = BeautifulSoup(html, "lxml")
        if re.search(r"/Inexpensive_Meteorites", url, re.I):
            listings.extend(arizona_list_page_rows(site, url, soup, log))
        else:
            item = arizona_listing_from_page(site, url, html, log)
            if item:
                listings.append(item)
        for href in arizona_candidate_links(site, url, soup, log):
            if href not in seen and href not in queue:
                queue.append(href)
    return listings


def impactika_headers(site: dict) -> dict:
    return {
        "User-Agent": BROWSER_UA,
        "Accept": "application/json,text/plain,*/*;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": urljoin(site["base_url"], "/"),
    }


def fetch_impactika_products(api_url: str, log: SourceLog, session: requests.Session, headers: dict):
    for attempt in range(1, IMPACTIKA_API_RETRIES + 1):
        log.index(api_url)
        products = fetch_json(api_url, log, "api", headers=headers, session=session, timeout=IMPACTIKA_API_TIMEOUT)
        if products is not None:
            return products
        if attempt < IMPACTIKA_API_RETRIES:
            time.sleep(DELAY * attempt)
    return None


def impactika_product_available(product: dict) -> bool:
    stock = product.get("stock_availability") or {}
    status_text = clean(
        " ".join(
            str(x or "")
            for x in [
                stock.get("text"),
                stock.get("class"),
                (product.get("add_to_cart") or {}).get("text"),
                (product.get("add_to_cart") or {}).get("description"),
            ]
        )
    )
    if product.get("is_in_stock") is False:
        return False
    return not re.search(r"\b(?:out\s+of\s+stock|sold|unavailable|on\s+backorder)\b", status_text, re.I)


def impactika_exact_row_values(line: str, log: SourceLog) -> tuple[float, str | None, float] | None:
    if IMPACTIKA_AMBIGUOUS_ROW_RE.search(line):
        log.reject("impactika_ambiguous_row")
        return None
    prices = prices_in(line)
    weights = list(WEIGHT_RE.finditer(line))
    if len(prices) != 1 or len(weights) != 1:
        log.reject("impactika_missing_or_multiple_price_weight")
        return None
    weight_match = weights[0]
    context = line[max(0, weight_match.start() - 45):weight_match.end() + 45]
    if NON_INDIVIDUAL_WEIGHT_CONTEXT_RE.search(context):
        log.reject("impactika_non_individual_weight")
        return None
    weight_value = num(weight_match.group(1))
    if weight_value is None:
        log.reject("impactika_missing_or_multiple_price_weight")
        return None
    _, price, currency = prices[0]
    weight = weight_to_g(weight_value, weight_match.group(2))
    if price <= 0 or weight <= 0:
        log.reject("impactika_missing_or_multiple_price_weight")
        return None
    return price, currency, weight


def impactika_image_url(product: dict, base_url: str) -> str | None:
    for image in product.get("images") or []:
        image_url = safe_http_url(base_url, image.get("src"))
        if image_url and not BAD_IMAGE_RE.search(image_url):
            return image_url
    return None


def impactika_taxonomy_names(product: dict, key: str) -> list[str]:
    return [clean(item.get("name")) for item in product.get(key) or [] if clean(item.get("name"))]


def impactika_classification_snippets(text: str) -> str:
    snippets = []
    for sentence in re.split(r"(?<=[.!?])\s+", clean(text)):
        if re.search(
            r"\b(?:classified\s+as|classification|iron\s+meteorites?|ordinary\s+chondrite|"
            r"carbonaceous|achondrite|pallasite|mesosiderite|shergottite|nakhlite|"
            r"chassignite|eucrite|diogenite|howardite|ureilite|aubrite|angrite|"
            r"octahedrite|ataxite|hexahedrite|IVA|IAB|IIAB|IIIAB|IVB|IIE|IRUNGR|"
            r"H\s?[3-7]|L\s?[3-7]|LL\s?[3-7]|CM\s?2|CV\s?3|CO\s?3|CR\s?2|CI\s?1)\b",
            sentence,
            re.I,
        ):
            snippets.append(sentence)
    return " ".join(snippets[:3])


def impactika_classification_context(categories: str, tag_names: list[str], text: str) -> str:
    return clean(" ".join(part for part in [categories, ", ".join(tag_names), impactika_classification_snippets(text)] if part))


def impactika_display_name(name: str) -> str:
    display = clean(name.title())
    return re.sub(r"\b(Nwa|Dag|Nakhla|Nininger)\b", lambda m: {"Nwa": "NWA", "Dag": "DaG"}.get(m.group(1), m.group(1)), display)


def impactika_row_title(name: str, line: str) -> str:
    descriptor = re.sub(r"\$\s*[0-9][0-9,]*(?:\.[0-9]{1,2})?.*$", "", line).strip(" ,.;")
    descriptor = re.sub(r"\bSOLD\b.*$", "", descriptor, flags=re.I).strip(" ,.;")
    display_name = impactika_display_name(name)
    if descriptor and not re.search(re.escape(descriptor), name, re.I):
        return clean(f"{display_name} - {descriptor}")
    return display_name


def scrape_impactika(site: dict, log: SourceLog) -> list[dict]:
    listings = []
    seen_keys = set()
    session = requests.Session()
    headers = impactika_headers(site)
    base_api = urljoin(site["base_url"], "/wp-json/wc/store/v1/products")
    for page in range(1, min(MAX_INDEX_PAGES_PER_SITE, 30) + 1):
        api_url = f"{base_api}?per_page={IMPACTIKA_API_PER_PAGE}&page={page}"
        products = fetch_impactika_products(api_url, log, session, headers)
        time.sleep(DELAY)
        if not products:
            break
        if not isinstance(products, list):
            log.reject_page("impactika_api_not_list")
            break
        for product in products:
            name = clean(BeautifulSoup(str(product.get("name") or ""), "lxml").get_text(" ", strip=True))
            permalink = product.get("permalink") or site["base_url"]
            category_names = impactika_taxonomy_names(product, "categories")
            tag_names = impactika_taxonomy_names(product, "tags")
            categories = ", ".join(category_names)
            if NON_SPECIMEN_PRODUCT_RE.search(name) or re.search(r"\b(?:print|catalog|book|drilling)\b", categories, re.I):
                log.reject("impactika_non_specimen_product")
                continue
            if not impactika_product_available(product):
                log.reject("impactika_unavailable_product")
                continue
            text = BeautifulSoup(product.get("short_description") or product.get("description") or "", "lxml").get_text("\n", strip=True)
            classification_context = impactika_classification_context(categories, tag_names, text)
            log.detail(permalink)
            for idx, line in enumerate([clean(x) for x in text.splitlines() if clean(x)]):
                if not (PRICE_RE.search(line) and WEIGHT_RE.search(line)):
                    continue
                if SOLD_STATUS_RE.search(line):
                    log.reject("impactika_sold_row")
                    continue
                if NON_SPECIMEN_PRODUCT_RE.search(line):
                    log.reject("impactika_non_specimen_row")
                    continue
                row_values = impactika_exact_row_values(line, log)
                if row_values is None:
                    continue
                price, currency, weight = row_values
                key = (permalink, idx, weight, price, line)
                if key in seen_keys:
                    log.reject("impactika_duplicate_row")
                    continue
                seen_keys.add(key)
                item = make_listing(
                    site,
                    permalink,
                    impactika_row_title(name, line),
                    price=price,
                    currency=currency or "USD",
                    weight_g=weight,
                    detail_text=clean(f"{classification_context} {text[:1200]}"),
                    explicit_type=classification_context or categories or "meteorite",
                    image_url=impactika_image_url(product, permalink),
                    item_key=f"{product.get('id')}:{idx}:{line}",
                    parser="impactika",
                )
                if item:
                    listings.append(item)
                    log.parsed_listing()
                else:
                    log.reject("make_listing_filtered")
        if len(products) < IMPACTIKA_API_PER_PAGE:
            break
    return listings


def scrape_sitemap_detail_pages(
    site: dict,
    log: SourceLog,
    parser: str,
    url_filter,
    *,
    reject_title_re: re.Pattern | None = None,
    title_weight_only: bool = False,
    ignore_text_sold: bool = False,
    allow_image_fallback: bool = True,
) -> list[dict]:
    listings = []
    attempts = 0
    for url in sitemap_product_urls(site, log):
        reason = url_filter(url)
        if reason:
            log.reject(reason)
            continue
        if attempts >= MAX_DETAIL_PAGES_PER_SITE:
            break
        attempts += 1
        log.detail(url)
        html = fetch(url, log, "detail")
        time.sleep(DELAY)
        if not html:
            log.reject_page("detail_fetch_failed")
            continue
        item = product_detail_listing(
            site,
            url,
            html,
            parser,
            log,
            fallback_type="meteorite",
            reject_title_re=reject_title_re,
            title_weight_only=title_weight_only,
            ignore_text_sold=ignore_text_sold,
            allow_image_fallback=allow_image_fallback,
        )
        if item:
            listings.append(item)
        if len(listings) >= MAX_DETAIL_PAGES_PER_SITE:
            break
    return listings


def skyfall_url_filter(url: str) -> str | None:
    path = urlparse(url).path.lower()
    if "/meteorites-for-sale/" not in path:
        return "skyfall_not_inventory_path"
    if "/skyfall-collection/" in path or "/meteorite-nfs/" in path or "-nfs" in path:
        return "skyfall_nfs_path"
    if re.search(r"(?:^|[-/])0g(?:[-/]|$)", path):
        return "skyfall_zero_gram_path"
    if NON_SPECIMEN_PRODUCT_RE.search(path):
        return "skyfall_non_specimen_path"
    return None


def scrape_skyfall_meteorites(site: dict, log: SourceLog) -> list[dict]:
    return scrape_sitemap_detail_pages(
        site,
        log,
        "skyfall_meteorites",
        skyfall_url_filter,
        reject_title_re=NON_SPECIMEN_PRODUCT_RE,
        title_weight_only=True,
        allow_image_fallback=False,
    )


def justmeteorites_url_filter(url: str) -> str | None:
    path = urlparse(url).path.lower()
    if not path.startswith("/p/"):
        return "justmeteorites_not_product_path"
    if "/c/sold/" in path or SOLD_STATUS_RE.search(path):
        return "justmeteorites_sold_path"
    if JUSTMETEORITES_NON_SPECIMEN_RE.search(path):
        return "justmeteorites_non_specimen_path"
    return None


def scrape_justmeteorites(site: dict, log: SourceLog) -> list[dict]:
    return scrape_sitemap_detail_pages(
        site,
        log,
        "justmeteorites",
        justmeteorites_url_filter,
        reject_title_re=JUSTMETEORITES_NON_SPECIMEN_RE,
        ignore_text_sold=True,
    )


def scrape_collector_secret(site: dict, log: SourceLog) -> list[dict]:
    log.reject_page("ebay_affiliate_aggregator_not_scraped")
    return []


def scrape_the_space_shop(site: dict, log: SourceLog) -> list[dict]:
    log.reject_page("generic_souvenir_lot_source_not_scraped")
    return []


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
    if parser == "aerolite":
        return scrape_aerolite(site, log)
    if parser == "meteolovers":
        return scrape_meteolovers(site, log)
    if parser == "galactic_stone":
        return scrape_galactic_stone(site, log)
    if parser == "fossil_realm":
        return scrape_fossil_realm(site, log)
    if parser == "top_meteorite":
        return scrape_top_meteorite(site, log)
    if parser == "mini_museum":
        return scrape_mini_museum(site, log)
    if parser == "meteorite_market":
        return scrape_meteorite_market(site, log)
    if parser == "arizona_skies":
        return scrape_arizona_skies(site, log)
    if parser == "impactika":
        return scrape_impactika(site, log)
    if parser == "skyfall_meteorites":
        return scrape_skyfall_meteorites(site, log)
    if parser == "justmeteorites":
        return scrape_justmeteorites(site, log)
    if parser == "collector_secret":
        return scrape_collector_secret(site, log)
    if parser == "the_space_shop":
        return scrape_the_space_shop(site, log)
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
    *,
    preserve_unselected_sources: bool,
) -> tuple[list[dict], set[str], set[str]]:
    merged_by_id = {}
    preserved_sources = set()
    empty_refresh_preserved_sources = set()

    for item in existing_data.get("listings", []):
        source = item.get("source")
        item_id = item.get("id")
        if source not in enabled_sources or not item_id:
            continue
        preserve_item = False
        if source in scraped_sources:
            if scraped_counts.get(source, 0) > 0:
                continue
            empty_refresh_preserved_sources.add(source)
            preserve_item = True
        elif preserve_unselected_sources:
            preserve_item = True
        if not preserve_item:
            continue
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

    listings, preserved_sources, empty_refresh_preserved_sources = merge_listings(
        load_existing_data(),
        refreshed_by_id,
        scraped_counts,
        scraped_sources,
        enabled_sources,
        preserve_unselected_sources=preserve_existing,
    )

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

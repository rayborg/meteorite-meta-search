#!/usr/bin/env python3
"""Site-specific public-page meteorite inventory scraper."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import random
import re
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SITES = ROOT / "data" / "sites.json"
OUT = ROOT / "data" / "listings.json"
METBULL_NAMES = ROOT / "data" / "metbull_names.json"
UA = "MeteoriteMetaSearchBot/0.3 (+https://github.com/rayborg/meteorite-meta-search)"
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
DELAY = 2.0
REQUEST_MIN_INTERVAL = 1.5
REQUEST_JITTER = (0.2, 0.8)
REQUEST_RETRY_STATUSES = {429, 500, 502, 503, 504}
REQUEST_MAX_ATTEMPTS = 3
REQUEST_MAX_BACKOFF = 90.0
HOST_NEXT_REQUEST_AT: dict[str, float] = {}
MAX_INDEX_PAGES_PER_SITE = 80
MAX_DETAIL_PAGES_PER_SITE = 300
MAX_SHOPIFY_PAGES_PER_SITE = 4
SHOPIFY_PRODUCTS_PER_SITE_CAP = MAX_SHOPIFY_PAGES_PER_SITE * 250
SHOPIFY_JSON_RETRIES = 3
FX_SUPPORTED_CURRENCIES = ("USD", "EUR")
FX_TIMEOUT = 15

METEORITE_RE = re.compile(
    r"meteorite|chondrite|achondrite|pallasite|lunar|martian|nwa\s*\d+|"
    r"northwest africa|"
    r"sikhote|gibeon|campo|diablo|gebel\s+kamil|dronino|tektite|moldavite|eucrite|diogenite|howardite|"
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
DIMENSION_NUMBER_RE = r"(?:[0-9]+(?:[,.][0-9]+)?|[,.][0-9]+|[0-9]+\s*/\s*[0-9]+)"
DIMENSION_UNIT_RE = r"(?:\"|in(?:ch(?:es)?)?\.?|cm|mm)"
DIMENSION_RE = re.compile(rf"(?<![0-9A-Za-z]){DIMENSION_NUMBER_RE}\s*{DIMENSION_UNIT_RE}(?![0-9A-Za-z])", re.I)
LEADING_DIMENSION_RE = re.compile(
    rf"^\s*(?:approx(?:imately)?\.?\s*)?{DIMENSION_NUMBER_RE}\s*{DIMENSION_UNIT_RE}(?![0-9A-Za-z])"
    rf"(?:\s*(?:x|by)\s*{DIMENSION_NUMBER_RE}\s*{DIMENSION_UNIT_RE}(?![0-9A-Za-z]))*\s*",
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
    ("iron", r"\b(iron\s+meteorites?|octahedrite|ataxite|hexahedrite|sikhote|campo del cielo|canyon diablo|gibeon|gebel\s+kamil|dronino|muonionalusta|seymchan|IIA|IAB|IIAB|IIIAB|IIIE-AN|IVA|IVB|IIE|IRUNGR|I\s*C)\b"),
    ("carbonaceous chondrite", r"\b(carbonaceous|c\s?2|cv\s?3|cvred\s?3|cvox[a-z]?\s?3|cm\s?2|ci\s?1|co\s?3|cr\s?2|ck\s?\d?|ch\s?\d?|cb\s?[ab]?|c3-?ung|c2-?ung|c1-?ung)\b"),
    ("ordinary chondrite", r"\b(ordinary chondrite|oc|h\s?[3-6](?:\.\d)?(?:\s*[/\-]\s*[3-6](?:\.\d)?)?|h/l\s?3?|l\s?[3-6](?:\.\d)?(?:\s*[/\-]\s*[3-6](?:\.\d)?)?|ll\s?[3-7](?:\.\d)?(?:\s*[/\-]\s*[3-7](?:\.\d)?)?|l\s?\(\s?ll\s?\)\s?3|h/l|l/ll|H|L|LL)\b"),
    ("achondrite", r"\b(achondrite|brachinite|eucrite|EUC|diogenite|howardite|hed\b|ureilite|aubrite|angrite|acapulcoite|lodranite|winonaite)\b"),
    ("chondrite", r"\b(chondrite|chondritic)\b"),
    ("stone", r"\bmeteorite\s+type\s*:\s*stone\b"),
    ("tektite/impactite", r"\b(tektite|moldavite|libyan desert glass|impactite|impact melt|saffordite)\b"),
]
LUNAR_METBULL_TYPE_RE = re.compile(r"^Lunar(?:\s*\(([^)]*)\))?$", re.I)
LUNAR_SUBTYPE_CANONICAL = {
    value.lower(): value
    for value in [
        "anorth",
        "bas/anor",
        "bas. breccia",
        "bas/gab brec",
        "basalt",
        "feldsp. breccia",
        "feldsp. melt breccia",
        "feldsp. melt rock",
        "frag. breccia",
        "gabbro",
        "melt breccia",
        "norite",
        "olivine gabbro",
        "olivine gabbronorite",
        "troct",
        "troct. anorth.",
        "troct. anorth. melt breccia",
        "troct. melt breccia",
        "troct. melt rock",
    ]
}
SUBTYPE_RE = re.compile(
    r"\b(?:H/L|L/LL|H/LL)\s*-?\s*[3-7](?:\.\d)?\b|"
    r"\b(H|L|LL)\s*-?\s*([3-7](?:\.\d)?(?:\s*[/\-]\s*[3-7](?:\.\d)?)?)\b|"
    r"\b(L\s?\(\s?LL\s?\)\s?3|L\s*-\s*melt breccia|LL\s?7)\b|"
    r"\b(CBa|CBb)\b|"
    r"\bC\s*-?\s*[123]\s*-\s*ung\b|"
    r"\b(CI|CM|CO|CV|CR|CK|CH|CB)\s*-?\s*(\d(?:\.\d)?)\b|"
    r"\b(C)\s*-?\s*(2)\b|"
    r"\b(CVred|CVoxA)\s*-?\s*3\b|"
    r"\b(OC|H/L\s?3?)\b|"
    r"\b(R)\s*-?\s*([3-6](?:\s*-\s*[3-6])?)\b|"
    r"\b(EH|EL)\s*-?\s*([3-7](?:\s*[/\-]\s*(?:(?:EH|EL)\s*)?[3-7])?)\b|"
    r"\bEH\s*-\s*melt\s+rock\b|"
    r"\b(IIA|IAB|IIAB|IIIAB|IIIE-AN|IVA|IVB|IIE|IRUNGR|I\s*C)\b|"
    r"\b(HED|EUC|eucrite(?:\s*-\s*(?:mmict|unbr|pmict|br|melt\s+breccia))?|diogenite|howardite|ureilite|aubrite|angrite|brachinite|shergottite|nakhlite|chassignite|octahedrite|ataxite|hexahedrite|acapulcoite|lodranite|winonaite|mesosiderite|achondrite(?:-ung)?)\b",
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
SOLD_STATUS_RE = re.compile(
    r"\b(on\s+hold|reserved|unavailable|discontinued)\b|"
    r"\bsold\b(?![\s-]+by\b)(?:[\s-]+out\b)?|"
    r"\bout[\s_-]*of[\s_-]*stock\b|\boutofstock\b",
    re.I,
)
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
IMPACTIKA_URL_NAME_OVERRIDES = {
    "ab1971-plainview": "Plainview 1917",
    "cm110-north-branch": "Northbranch",
}
IMPACTIKA_INVENTORY_CODE_RE = re.compile(r"^(?:AB|AC|CM|OC)\s*-?\s*\d+[A-Za-z]?$", re.I)
IMPACTIKA_SPLIT_INVENTORY_CODE_RE = re.compile(r"^(?:AB|AC|CM|OC)$", re.I)
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
ASTRO_WEST_NON_SPECIMEN_RE = re.compile(
    r"\b(?:jewelry|jewellery|pendants?|rings?|necklaces?|bracelets?|earrings?|beads?|dog\s*tags?|wearable|"
    r"collector(?:'s)?\s+display\s+box(?:es)?|collector\s+box(?:es)?|display\s+box(?:es)?|box\s+sets?|space\s+crystals?|"
    r"souvenirs?|stands?|display\s+(?:cases?|stands?|frames?)|cubes?|pyramids?|carvings?|shapes?|sets?|lots?)\b",
    re.I,
)
ASTRO_WEST_CATEGORY_NON_SPECIMEN_RE = re.compile(
    r"\b(?:jewelry|jewellery|meteorite\s+jewelry|pendants?|necklaces?|box\s+sets?|display\s+boxes?)\b",
    re.I,
)
PREHISTORIC_FOSSILS_NON_SPECIMEN_RE = re.compile(
    r"\b(?:gem\s*jars?|jars?|frames?|riker|display|boxes?|shadow\s*boxes?|bundles?|sets?|lots?|bulk|"
    r"jewelry|jewellery|pendants?|rings?|necklaces?|bracelets?|earrings?|beads?|"
    r"replicas?|casts?|currently\s+sold\s+out)\b",
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
GALACTIC_STONE_ECRATER_PRODUCT_RE = re.compile(r"^/p/\d+/[a-z0-9-]+/?$", re.I)
POLANDMET_NON_SPECIMEN_RE = re.compile(
    r"\b(?:collection|collections?|sets?|lots?|display\s*(?:case|box|stand)?|gembox|coin|coins|cast|casts|"
    r"wiresaw|cutting\s+service|mineral|teschenite|box|case|stand|coupon|gift|souvenir)\b",
    re.I,
)
KD_NON_SPECIMEN_URL_RE = re.compile(
    r"MeteoriteKnives|MeteoriteJewelry|MeteoriteGift|GiftCertificates|MeteoriteCare|MeteorWrongs|"
    r"Identifying|Identification|MeteoriteAdventures|MeteorAdventures|About|CheckOut|otherlinks|index|"
    r"WeBuy|KDMeteoriteCollection|AdmireGemstones|SpearPoints|Firelight|LakeSuperior|OtherCoolFinds|"
    r"coveretchediron|stone\.htm|Newspaper|Newspapers|Certificate|Gift",
    re.I,
)
KD_NON_SPECIMEN_TEXT_RE = re.compile(
    r"\b(?:knife|knives|jewelry|jewellery|pendants?|rings?|bracelets?|earrings?|beads?|"
    r"gemstones?|spear\s*points?|gift\s*certificates?|newspapers?|display\s*stands?|"
    r"chain\s+not\s+included|meteorwrongs?|meteorite\s+care|firelight)\b",
    re.I,
)
KD_BAD_LABEL_RE = re.compile(
    r"^(?:home|about\s+us|links?|check\s+out|stone\s+meteorites?|iron\s+meteorites?|stony\s+iron\s+meteorites?|"
    r"pallasite\s+meteorite\s+nuggets?|meteorite\s+(?:knives|jewelry|care|identification|adventures|gift\s+ideas)|"
    r"finding\s+meteorites\s+since\s+1990!?|kd\s+meteorites?)$",
    re.I,
)
KD_HUB_PATHS = [
    "IronMeteoritesForSale.html",
    "EtchedMeteoriteSlicesForSale.html",
    "PallasiteMeteoritesForSale.html",
    "PallasiteMeteoriteNuggetsForSale.html",
    "ChondriteMeteoritesForSale.html",
    "WhatsNewAtKDMeteorites.html",
]
WWMETEORITES_BAD_PATH_RE = re.compile(
    r"^(?:$|accueil|my-account|account|fullscreen-page|mammoth|mammothtooth|nuvvuagittuq|nuvvuagittuq-bif|"
    r"gallium|trinitite|marsbluff|putorano)$",
    re.I,
)
WWMETEORITES_NON_SPECIMEN_RE = re.compile(
    r"\b(?:mammoths?|tusks?|ivory|fossils?|terrestrial\s+(?:native\s+)?iron|oldest\s+terrestrial|"
    r"nuvvuagittuq|gallium|trinitite|atomic\s+bomb|nuclear\s+weapon|mars\s+bluff|"
    r"banded\s+iron\s+formation|\bBIF\b)\b",
    re.I,
)
WWMETEORITES_AMBIGUOUS_ROW_RE = re.compile(
    r"\b(?:lots?|sets?|groups?|matched[-_\s]+pairs?|choose|choice|several|many|multiple|assort(?:ed|ment)|"
    r"various|per\s*(?:gram|g)|/\s*(?:gram|g)|from\s+\$|starting\s+at|price\s+on\s+request|contact\s+for\s+price)\b|"
    r"\b\d+\s+(?:pieces?|fragments?|slices?|individuals?|specimens?)\b",
    re.I,
)
WWMETEORITES_PRICE_RE = re.compile(
    rf"(?:(?P<symbol_before>US\$|\$|USD|€|EUR)\s*(?P<amount_before>{WEIGHT_NUMBER_RE})|"
    rf"(?P<amount_after>{WEIGHT_NUMBER_RE})\s*(?P<symbol_after>US\$|\$|USD|€|EUR))",
    re.I,
)
WWMETEORITES_BAD_IMAGE_RE = re.compile(
    r"favicon|facebook|instagram|logo|a8e1f3e15ccb41b88df85a10bb90531a|e0678ef25486466ba65ef6ad47b559e1|"
    r"vesta[-_\s]*aster|spacecraft|cambridge|binary-alt",
    re.I,
)
ECOMMERCE_CLEAN_TITLE_PARSERS = {
    "aerolite",
    "astro_west",
    "buy_meteorite",
    "fossil_realm",
    "fossilera",
    "galactic_stone",
    "galactic_stone_ecrater",
    "impactika",
    "justmeteorites",
    "kd_meteorites",
    "polandmet",
    "prehistoric_fossils",
    "meteolovers",
    "meteorite_exchange",
    "mini_museum",
    "skyfall_meteorites",
    "top_meteorite",
    "wwmeteorites",
}
CATALOG_NAME_RE = re.compile(r"\b(NWA|North\s*west\s+Africa|Northwest\s+Africa)\s*(\d{2,6})(?:\s*([A-Z]))?\b", re.I)
NUMBERED_OFFICIAL_NAME_RE = re.compile(
    r"\b(?:Abadla|Adrar|Al\s+Haggounia|Al\s+Khuwaymat|Bechar|DaG|Dar\s+al\s+Gani|Denader|Dhofar|Erg\s+Chech|JAH|Jiddat\s+al\s+Harasis|"
    r"Jikharra|Ksar\s+Ghilane|Laayoune|NEA|Northeast\s+Africa|Oued\s+el\s+Hamim|RaS|Ramlat\s+as\s+Sahmah|"
    r"SaU|Sayh\s+al\s+Uhaymir|Taoudenni|Tibertatine|Tirhert)\s+\d{2,6}[A-Za-z]?\b",
    re.I,
)
KNOWN_DISPLAY_NAME_RE = re.compile(
    r"\b(?:Aba\s+Panu|Abadla\s+002|Agoudal|Aguas\s+Zarcas|Ait\s+Saoun|Allende|Borzya|Canyon\s+Diablo|"
    r"Campo\s+del\s+Cielo|Chergach|Chelyabinsk|Dronino|El\s+Menia|Gebel\s+Kamil|Gibeon|Holbrook|Brenham|Imilac|"
    r"Kapustin\s+Yar|Mundrabilla|Murchison|Salaices|Seymchan|Sikhote[-\s]+Alin)\b",
    re.I,
)
CANONICAL_ALIAS_PATTERNS = [
    (re.compile(r"\b(?:baby\s+campocito|campocito)\b", re.I), "Campo del Cielo"),
]
TEKTITE_DISPLAY_NAME_RE = re.compile(
    r"\b(?:Moldavite|Libyan\s+Desert\s+Glass|Irghizite|Australite|Indochinite|Saffordite|Wabar\s+Pearl|Atacamaite)\b",
    re.I,
)
DISPLAY_CLASS_START_RE = re.compile(
    r"\b(?:ordinary\s+chondrite|carbonaceous\s+chondrite|chondrite|achondrite|lunar|martian|"
    r"aubrite|eucrite|diogenite|howardite|ureilite|angrite|brachinite|acapulcoite|lodranite|winonaite|meteorites?|"
    r"shergottite|nakhlite|chassignite|pallasite|mesosiderite|iron\s+meteorite|octahedrite|ataxite|hexahedrite|"
    r"tektite|impactite|impact\s+glass|"
    r"HED|EUC|OC|(?:H|L|LL|EH|EL|R|CK|CM|CV|CO|CR|CI)\s*-?\s*\d(?:\.\d)?|"
    r"IIA|IAB|IIAB|IIIAB|IVA|IVB|IIE|IRUNGR)\b",
    re.I,
)
DISPLAY_PRODUCT_TRAILING_RE = re.compile(
    r"(?:[,;:]?\s*\b(?:polished|complete|full|part|partial|thin|thick|end\s*cut|endcut|slice|section|fragment|fragement|"
    r"endpiece|individual|specimen|hammer\s+stone|stone|piece|main\s+mass|window|cut|oriented|crusted|fresh\s+crust|fusion\s+crust|"
    r"flight\s+lines?|flow\s+lines?|full\s+of\s+clasts?)\b)+$",
    re.I,
)
DISPLAY_PRODUCT_LEADING_RE = re.compile(r"^(?:polished|complete|full|part|partial|thin|thick|authentic|genuine|natural|beautiful|rare|superb|gorgeous|fresh|oriented|crusted)\s+", re.I)
DISPLAY_GENERIC_SUFFIX_RE = re.compile(
    r"^(?:new\s+find|fresh\s+(?:19|20)\d{2}\s+fall|(?:19|20)\d{2}\s+witnessed\s+fall|witnessed\s+fall|from\b|for\s+sale|"
    r"main\s+mass|museum\s+quality|rare|beautiful|complete|full|part|partial|thin|thick|"
    r"slice|section|fragment|fragement|end\s*cut|endcut|endpiece|specimen|piece|main\s+mass|hammer\s+stone|stone|oriented|crusted|fresh\s+crust|"
    r"fusion\s+crust|flight\s+lines?|flow\s+lines?)\b",
    re.I,
)
DISPLAY_GENERIC_PREFIX_RE = re.compile(
    r"^(?:unclassified(?:\s+(?:NWA|north\s*west\s+africa|northwest\s+africa))?|ungrouped|primitive|polymict|brecciated|"
    r"aqueous\s+altered|authentic|genuine|natural|beautiful|rare|superb|gorgeous|oriented|crusted)$",
    re.I,
)
GENERIC_DISPLAY_ADJECTIVE_RE = re.compile(
    r"^(?:authentic|genuine|natural|fresh|beautiful|beauty|gorgeous|superb|rare|amazing|great|fantastic|oriented|crusted)$",
    re.I,
)
DISPLAY_SUFFIX_ONLY_RE = re.compile(
    r"^(?:Algeria|Argentina|Australia|Austria|Brazil|Canada|Chile|China|Czech\s+Republic|France|Indonesia|Italy|Kenya|Libya|Mexico|Morocco|"
    r"Nigeria|Oman|Pakistan|Peru|Poland|Romania|Russia|Spain|Tunisia|Turkey|Ukraine|Uruguay|USA|Zimbabwe|"
    r"Arizona|Arkansas|Colorado|Florida|Idaho|Iowa|Kansas|Kentucky|Missouri|Nebraska|Nevada|New\s+Mexico|North\s+Dakota|Ohio|Oklahoma|"
    r"South\s+Dakota|Tennessee|Texas|Utah|Wyoming|Queensland|Tasmania|Victoria|Western\s+Australia|South\s+Australia|Northern\s+Territory|"
    r"Besednice\s*,\s*Czech\s+Republic|Fresh\s+(?:19|20)\d{2}\s+Fall|(?:19|20)\d{2}\s+Fall|"
    r"(?:19|20)\d{2}\s+Witnessed\s+Fall|Witnessed\s+Fall|New\s+Find)\s*!?$",
    re.I,
)
CLASSIFICATION_PRODUCT_TEXT_RE = re.compile(
    r"\b(?:hammer\s+stone|end\s+slice|slice|section|fragment|fragement|end\s*cut|endcut|endpiece|main\s+mass|specimen|individual|piece|polished|"
    r"oriented|crusted|fresh\s+crust|fusion\s+crust|flight\s+lines?|flow\s+lines?|widmanst[a\u00e4]tten\s+patterns?)\b",
    re.I,
)
DISPLAY_CLASSIFICATION_ONLY_RE = re.compile(
    r"^(?:(?:Iron|Stone|Stony[-\s]+Iron)\s*,?\s*)?"
    r"(?:IIA|IAB|IIAB|IIIAB|IIIE-AN|IVA|IVB|IIE|IRUNGR|IC|"
    r"H|L|LL|EH|EL|R|CI|CM|CO|CV|CR|CK|CH|CB|C|OC)\s*-?\s*\d?(?:\.\d)?(?:\s*/\s*\d(?:\.\d)?)?"
    r"(?:\s+(?:Iron|Meteorite|Chondrite|Achondrite|Pallasite|Mesosiderite|Stone))*$",
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


def unavailable_status_text(text: str | None) -> bool:
    return bool(SOLD_STATUS_RE.search(text or ""))


def currency_code(value: str | None) -> str | None:
    code = clean(str(value or "")).upper()
    if code in {"$", "US$"}:
        return "USD"
    if code == "€":
        return "EUR"
    return code or None


def numeric_value(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def round_rate(value: float) -> float:
    return round(float(value), 8)


def normalized_catalog_name(match: re.Match) -> str:
    prefix, number, suffix = match.groups()
    suffix_text = f" {suffix.upper()}" if suffix else ""
    if re.match(r"NWA", prefix, re.I):
        return f"NWA {number}{suffix_text}"
    return f"Northwest Africa {number}{suffix_text}"


def first_catalog_name(text: str) -> str | None:
    match = CATALOG_NAME_RE.search(text or "")
    return normalized_catalog_name(match) if match else None


def display_case_name(name: str) -> str:
    name = clean(name)
    if name.isupper() and len(name) > 3:
        name = name.title()
    name = re.sub(r"\bCampo\s+Del\s+Cielo\b", "Campo del Cielo", name)
    return re.sub(
        r"\b(?:Nwa|Nea|Jah|Dag|Sau|Ras)\b",
        lambda m: {"Nwa": "NWA", "Nea": "NEA", "Jah": "JAH", "Dag": "DaG", "Sau": "SaU", "Ras": "RaS"}[m.group(0)],
        name,
    )


def first_numbered_official_name(text: str) -> str | None:
    match = NUMBERED_OFFICIAL_NAME_RE.search(text or "")
    return display_case_name(match.group(0)) if match else None


def first_known_display_name(text: str) -> str | None:
    match = KNOWN_DISPLAY_NAME_RE.search(text or "")
    if match and re.fullmatch(r"Sikhote[-\s]+Alin", match.group(0), re.I):
        return "Sikhote-Alin"
    return display_case_name(match.group(0)) if match else None


def first_tektite_display_name(text: str) -> str | None:
    match = TEKTITE_DISPLAY_NAME_RE.search(text or "")
    return display_case_name(match.group(0)) if match else None


def strip_product_measurements(text: str) -> str:
    text = clean(text)
    text = re.sub(
        rf"\([^)]*(?:{WEIGHT_NUMBER_RE}\s*(?:kg|kilograms?|g|gm|gms|gr|grs|grams?|mg|milligrams?|oz|ounces?)|{DIMENSION_NUMBER_RE}\s*{DIMENSION_UNIT_RE})[^)]*\)",
        " ",
        text,
        flags=re.I,
    )
    text = WEIGHT_RANGE_RE.sub(" ", text)
    text = WEIGHT_RE.sub(" ", text)
    text = DIMENSION_RE.sub(" ", text)
    text = re.sub(r"\(\s*\)", " ", text)
    return clean(text)


def tidy_display_candidate(text: str) -> str:
    candidate = strip_product_measurements(text)
    candidate = re.sub(r"\b(?:For\s+Sale|New\s+Find|Witnessed\s+Fall)\b.*$", "", candidate, flags=re.I)
    candidate = re.sub(r"\s*(?:-|\u2013|\u2014)\s*widmanst[a\u00e4]tten\s+patterns?\b.*$", " ", candidate, flags=re.I)
    candidate = re.sub(
        r"\b(?:hammer\s+stone|end\s+slice|thin\s+slice|thick\s+slice|full\s+slice|part\s+slice|partial\s+slice|"
        r"slice|section|fragment|fragement|end\s*cut|endcut|specimen|individual|piece)\b",
        " ",
        candidate,
        flags=re.I,
    )
    previous = None
    while candidate and candidate != previous:
        previous = candidate
        candidate = clean(DISPLAY_PRODUCT_LEADING_RE.sub("", candidate))
        candidate = clean(DISPLAY_PRODUCT_TRAILING_RE.sub("", candidate).strip(" .,-;:!"))
    return clean(candidate.strip(" .,-;:!"))


def clean_suffix_name(segment: str) -> str | None:
    segment = clean(segment.strip(" .,-;:!"))
    catalog = first_catalog_name(segment)
    if catalog:
        return catalog
    numbered_name = first_numbered_official_name(segment)
    if numbered_name:
        return numbered_name
    known_name = first_known_display_name(segment)
    if known_name:
        return known_name
    tektite_name = first_tektite_display_name(segment)
    if tektite_name:
        return tektite_name
    candidate = tidy_display_candidate(segment)
    if not candidate or len(candidate) > 80:
        return None
    if not re.search(r"[A-Za-z]", candidate):
        return None
    if DISPLAY_SUFFIX_ONLY_RE.fullmatch(candidate):
        return None
    if DISPLAY_CLASSIFICATION_ONLY_RE.fullmatch(candidate):
        return None
    if DISPLAY_GENERIC_SUFFIX_RE.search(candidate):
        return None
    if CLASSIFICATION_PRODUCT_TEXT_RE.search(candidate):
        return None
    if re.search(r"\b(?:meteorite|chondrite|achondrite|shergottite|eucrite|diogenite|howardite|aubrite|ureilite|pallasite|tektite|impactite)\b", candidate, re.I):
        return None
    return candidate


def name_before_classification(candidate: str) -> str | None:
    match = DISPLAY_CLASS_START_RE.search(candidate)
    if not match or match.start() == 0:
        return None
    prefix = tidy_display_candidate(candidate[:match.start()])
    prefix = clean(re.sub(r"[\s\(\[\{\-/\u2013\u2014]+$", "", prefix))
    if not prefix or len(prefix) < 3 or DISPLAY_GENERIC_PREFIX_RE.fullmatch(prefix):
        return None
    if CLASSIFICATION_PRODUCT_TEXT_RE.search(prefix):
        return None
    return display_case_name(prefix)


def product_identity_from_title(raw_title: str) -> str | None:
    candidate = tidy_display_candidate(raw_title)
    candidate = clean(re.sub(r"\s+-\s+(?:AB|AC|CM|OC)\s*-?\d+[A-Za-z]?\b.*$", "", candidate, flags=re.I))
    if not candidate or not re.search(r"[A-Za-z]", candidate):
        return None
    catalog = first_catalog_name(candidate)
    if catalog:
        return catalog
    numbered_name = first_numbered_official_name(candidate)
    if numbered_name:
        return numbered_name
    known_name = first_known_display_name(candidate)
    if known_name:
        return known_name
    tektite_name = first_tektite_display_name(candidate)
    if tektite_name:
        return tektite_name
    named_prefix = name_before_classification(candidate)
    if named_prefix:
        return named_prefix
    if len(candidate) <= 80 and not DISPLAY_SUFFIX_ONLY_RE.fullmatch(candidate) and not DISPLAY_CLASSIFICATION_ONLY_RE.fullmatch(candidate) and not DISPLAY_GENERIC_SUFFIX_RE.search(candidate):
        if not CLASSIFICATION_PRODUCT_TEXT_RE.search(candidate) and not DISPLAY_CLASS_START_RE.fullmatch(candidate):
            return display_case_name(candidate)
    return None


def product_identity_from_url(url: str | None) -> str | None:
    if not url:
        return None
    slug = unquote(urlparse(url).path.rstrip("/").rsplit("/", 1)[-1])
    if not slug:
        return None
    slug = re.sub(r"--+\d+$", "", slug)
    slug_text = clean(re.sub(r"[-_]+", " ", slug))
    tokens = slug_text.split()
    while len(tokens) > 1 and re.fullmatch(r"\d+", tokens[0]):
        tokens.pop(0)
    slug_title = " ".join(tokens).title()
    return product_identity_from_title(slug_title)


METBULL_CACHE: dict | None = None


def normalize_name_key(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", clean(str(value or "")))
    text = "".join(char for char in text if not unicodedata.combining(char)).lower()
    text = re.sub(r"[\u2018\u2019'`]", "", text)
    text = re.sub(r"[-_]+", " ", text)
    text = re.sub(r"\bmeteorites?\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_metbull_cache() -> dict:
    global METBULL_CACHE
    if METBULL_CACHE is not None:
        return METBULL_CACHE
    if not METBULL_NAMES.exists():
        METBULL_CACHE = {"names": {}, "aliases": {}}
        return METBULL_CACHE
    try:
        data = json.loads(METBULL_NAMES.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        METBULL_CACHE = {"names": {}, "aliases": {}}
        return METBULL_CACHE
    names = data.get("names") if isinstance(data.get("names"), dict) else {}
    aliases = data.get("aliases") if isinstance(data.get("aliases"), dict) else {}
    METBULL_CACHE = {
        "names": {normalize_name_key(key): value for key, value in names.items() if isinstance(value, dict)},
        "aliases": {normalize_name_key(key): normalize_name_key(value) for key, value in aliases.items()},
    }
    return METBULL_CACHE


def metbull_lookup(candidate: str | None) -> dict | None:
    key = normalize_name_key(candidate)
    if not key:
        return None
    cache = load_metbull_cache()
    key = cache.get("aliases", {}).get(key, key)
    return cache.get("names", {}).get(key)


def metbull_canonical_info(candidate: str, source: str) -> dict | None:
    entry = metbull_lookup(candidate)
    if not entry:
        return None
    name = clean(str(entry.get("name") or candidate))
    display_name = clean(str(entry.get("display_name") or entry.get("abbrev") or name))
    info = {
        "canonical_name": name,
        "canonical_name_display": display_name,
        "canonical_name_status": "metbull_verified",
        "canonical_name_source": source,
    }
    if entry.get("code") is not None:
        info["metbull_code"] = str(entry.get("code"))
    if entry.get("status"):
        info["metbull_status"] = clean(str(entry.get("status")))
    if entry.get("type"):
        info["metbull_type"] = clean(str(entry.get("type")))
    return info


def parsed_canonical_info(candidate: str, source: str) -> dict:
    display_name = display_case_name(candidate)
    return {
        "canonical_name": display_name,
        "canonical_name_display": display_name,
        "canonical_name_status": "parsed_high",
        "canonical_name_source": source,
    }


def catalog_name_candidates(text: str | None) -> list[str]:
    candidates = []
    text = text or ""
    for match in CATALOG_NAME_RE.finditer(text):
        tail = text[match.end():match.end() + 16]
        if re.match(r"\s*(?:kg|kilograms?|g|gm|gms|gr|grs|grams?|mg|milligrams?|oz|ounces?)\b", tail, re.I):
            continue
        candidates.append(normalized_catalog_name(match))
    return candidates


def numbered_name_candidates(text: str | None) -> list[str]:
    candidates = []
    for match in NUMBERED_OFFICIAL_NAME_RE.finditer(text or ""):
        candidate = display_case_name(match.group(0))
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def known_name_candidates(text: str | None) -> list[str]:
    candidates = []
    for pattern, canonical in CANONICAL_ALIAS_PATTERNS:
        if pattern.search(text or "") and canonical not in candidates:
            candidates.append(canonical)
    for match in KNOWN_DISPLAY_NAME_RE.finditer(text or ""):
        candidate = display_case_name(match.group(0))
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def url_name_text(url: str | None) -> str:
    if not url:
        return ""
    slug = unquote(urlparse(url).path.rstrip("/").rsplit("/", 1)[-1])
    return clean(re.sub(r"[-_]+", " ", slug))


def classification_display_from_context(text: str | None) -> str | None:
    text = clean(text or "")
    if re.search(r"\bordinary\b.*\bchondrite\b|\bchondrite\b.*\bordinary\b", text, re.I):
        return "Ordinary chondrite"
    if re.search(r"\bcarbonaceous\b.*\bchondrite\b|\bchondrite\b.*\bcarbonaceous\b", text, re.I):
        return "Carbonaceous chondrite"
    for label in [
        "eucrite",
        "diogenite",
        "howardite",
        "aubrite",
        "ureilite",
        "angrite",
        "pallasite",
        "mesosiderite",
        "chondrite",
        "iron meteorite",
        "lunar meteorite",
        "martian meteorite",
    ]:
        if re.search(rf"\b{re.escape(label)}\b", text, re.I):
            return label.capitalize()
    return None


def canonical_name_info(raw_title: str, display_name: str, detail_text: str, url: str) -> dict:
    sources = [
        (display_name, "title"),
        (raw_title, "raw_title"),
        (url_name_text(url), "url"),
    ]
    for text, source in sources:
        for candidate in [*known_name_candidates(text), *catalog_name_candidates(text), *numbered_name_candidates(text)]:
            verified = metbull_canonical_info(candidate, source)
            if verified:
                return verified
            if source in {"title", "raw_title", "url"} and (catalog_name_candidates(candidate) or numbered_name_candidates(candidate)):
                return parsed_canonical_info(candidate, source)

    fallback = product_identity_from_title(display_name)
    verified = metbull_canonical_info(fallback, "title_identity") if fallback else None
    if verified:
        return verified

    # Detail descriptions often contain history, Wikipedia excerpts, or recommendations.
    # Only allow official numbered/catalog names from this wider text, not broad names
    # such as Holbrook or Allende that commonly appear as unrelated examples.
    for candidate in [*catalog_name_candidates(detail_text[:1600]), *numbered_name_candidates(detail_text[:1600])]:
        verified = metbull_canonical_info(candidate, "detail_text")
        if verified:
            return verified

    return {
        "canonical_name": None,
        "canonical_name_display": None,
        "canonical_name_status": "unknown",
        "canonical_name_source": None,
    }


def ecommerce_display_title(raw_title: str, parser: str, url: str | None = None) -> str:
    title = clean(raw_title)
    if parser == "impactika":
        if re.search(r"\s+-\s+(?:AB|AC|CM|OC)\s*-?\d+[A-Za-z]?\b", title, re.I):
            return title
        impactika_name = impactika_name_from_url(url)
        if impactika_name:
            return impactika_name
    if parser == "aerolite":
        title = clean(re.sub(r"\s*\|\s*Aerolite Meteorites.*$", "", title, flags=re.I))
    parts = re.split(r"\s+-\s+", title)
    if len(parts) > 1:
        for segment in reversed(parts[1:]):
            suffix_name = clean_suffix_name(segment)
            if suffix_name:
                return suffix_name

    leading_name = product_identity_from_title(parts[0] if parts else title)
    if leading_name:
        return leading_name
    whole_title_name = product_identity_from_title(title)
    if whole_title_name:
        return whole_title_name
    url_name = product_identity_from_url(url)
    if url_name:
        return url_name
    candidate = tidy_display_candidate(parts[0] if parts else title)
    if candidate and not DISPLAY_SUFFIX_ONLY_RE.fullmatch(candidate):
        return candidate
    if GENERIC_DISPLAY_ADJECTIVE_RE.fullmatch(title):
        classification_title = classification_display_from_context(f"{title} {urlparse(url or '').path}")
        if classification_title:
            return classification_title
    return title


def display_title(raw_title: str, parser: str | None = None, url: str | None = None) -> str:
    parser = parser or "generic"
    title = clean(raw_title)
    if parser in ECOMMERCE_CLEAN_TITLE_PARSERS:
        return ecommerce_display_title(title, parser, url)
    return title


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


def host_key(url: str) -> str:
    return urlparse(url).netloc.lower()


def throttle_host(url: str, base_delay: float = REQUEST_MIN_INTERVAL) -> None:
    host = host_key(url)
    if not host:
        return
    now = time.monotonic()
    next_at = HOST_NEXT_REQUEST_AT.get(host, 0.0)
    if next_at > now:
        time.sleep(next_at - now)
    HOST_NEXT_REQUEST_AT[host] = time.monotonic() + base_delay + random.uniform(*REQUEST_JITTER)


def retry_after_seconds(response: requests.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return min(float(value), REQUEST_MAX_BACKOFF)
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return min(max(0.0, retry_at.timestamp() - time.time()), REQUEST_MAX_BACKOFF)


def polite_request(
    method: str,
    url: str,
    *,
    log: SourceLog | None = None,
    kind: str = "request",
    session: requests.Session | None = None,
    headers: dict | None = None,
    timeout: int = 30,
    max_attempts: int = REQUEST_MAX_ATTEMPTS,
    **kwargs,
) -> requests.Response | None:
    client = session or requests
    for attempt in range(1, max_attempts + 1):
        try:
            throttle_host(url)
            response = client.request(method, url, headers=headers, timeout=timeout, **kwargs)
            if log:
                log.fetched(response.status_code)
            if response.status_code not in REQUEST_RETRY_STATUSES or attempt >= max_attempts:
                return response
            wait = retry_after_seconds(response)
            if wait is None:
                wait = min(REQUEST_MAX_BACKOFF, (2 ** (attempt - 1)) * DELAY) + random.uniform(0.5, 2.0)
            print(f"WARN transient HTTP {response.status_code}: {url}; retrying in {wait:.1f}s")
            time.sleep(wait)
        except requests.RequestException as exc:
            if attempt >= max_attempts:
                print(f"WARN {kind} failed {url}: {exc}")
                if log:
                    log.failed(url, str(exc))
                return None
            wait = min(REQUEST_MAX_BACKOFF, (2 ** (attempt - 1)) * DELAY) + random.uniform(0.5, 2.0)
            print(f"WARN {kind} attempt {attempt} failed {url}: {exc}; retrying in {wait:.1f}s")
            time.sleep(wait)
    return None


def site_int(site: dict, key: str, default: int, hard_max: int) -> int:
    try:
        value = int(site.get(key, default))
    except (TypeError, ValueError):
        value = default
    return min(max(value, 0), hard_max)


def fetch(
    url: str,
    log: SourceLog | None = None,
    kind: str = "page",
    session: requests.Session | None = None,
    headers: dict | None = None,
    timeout: int = 30,
) -> str | None:
    request_headers = {"User-Agent": UA, "Accept": "text/html"}
    if headers:
        request_headers.update(headers)
    r = polite_request("GET", url, log=log, kind=kind, session=session, headers=request_headers, timeout=timeout)
    if r is None:
        return None
    if r.status_code >= 400:
        print(f"WARN {r.status_code}: {url}")
        if log:
            log.failed(url, f"{kind} HTTP {r.status_code}")
        return None
    return r.text


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


def fx_date_from_open_exchange(data: dict) -> str:
    timestamp = numeric_value(data.get("time_last_update_unix"))
    if timestamp:
        return datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()
    text = clean(str(data.get("time_last_update_utc") or ""))
    if text:
        try:
            return parsedate_to_datetime(text).date().isoformat()
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc).date().isoformat()


def open_exchange_fx_metadata(data: dict) -> dict | None:
    rates = data.get("rates") if isinstance(data, dict) else None
    if not isinstance(rates, dict):
        return None
    rates_to_usd = {"USD": 1.0}
    for currency in FX_SUPPORTED_CURRENCIES:
        if currency == "USD":
            continue
        units_per_usd = numeric_value(rates.get(currency))
        if units_per_usd and units_per_usd > 0:
            rates_to_usd[currency] = round_rate(1 / units_per_usd)
    if len(rates_to_usd) < len(FX_SUPPORTED_CURRENCIES):
        return None
    return {
        "base": "USD",
        "target": "USD",
        "rates_to_usd": rates_to_usd,
        "date": fx_date_from_open_exchange(data),
        "source": "open.er-api.com",
    }


def frankfurter_fx_metadata(data: dict) -> dict | None:
    rates = data.get("rates") if isinstance(data, dict) else None
    usd_per_eur = numeric_value(rates.get("USD")) if isinstance(rates, dict) else None
    if not usd_per_eur or usd_per_eur <= 0:
        return None
    return {
        "base": "USD",
        "target": "USD",
        "rates_to_usd": {"USD": 1.0, "EUR": round_rate(usd_per_eur)},
        "date": clean(str(data.get("date") or "")) or datetime.now(timezone.utc).date().isoformat(),
        "source": "frankfurter.app",
    }


def fetch_current_fx_metadata() -> dict | None:
    endpoints = [
        ("https://open.er-api.com/v6/latest/USD", open_exchange_fx_metadata),
        ("https://api.frankfurter.app/latest?from=EUR&to=USD", frankfurter_fx_metadata),
    ]
    for url, parser in endpoints:
        try:
            response = polite_request("GET", url, kind="fx", headers={"User-Agent": UA, "Accept": "application/json"}, timeout=FX_TIMEOUT)
            if response is None:
                continue
            if response.status_code >= 400:
                print(f"WARN FX fetch HTTP {response.status_code}: {url}")
                continue
            metadata = parser(response.json())
            if metadata:
                print(f"Using FX rates from {metadata['source']} for {metadata['date']}")
                return metadata
            print(f"WARN FX response missing required USD/EUR rates: {url}")
        except (requests.RequestException, ValueError) as exc:
            print(f"WARN FX fetch failed {url}: {exc}")
    return None


def normalize_fx_metadata(metadata: dict | None, source: str) -> dict | None:
    if not isinstance(metadata, dict):
        return None
    raw_rates = metadata.get("rates_to_usd")
    if not isinstance(raw_rates, dict):
        return None
    rates_to_usd = {"USD": 1.0}
    for raw_currency, raw_rate in raw_rates.items():
        currency = currency_code(str(raw_currency))
        rate = numeric_value(raw_rate)
        if currency and rate and rate > 0:
            rates_to_usd[currency] = round_rate(rate)
    date = clean(str(metadata.get("date") or metadata.get("fx_rate_date") or ""))
    if not date:
        return None
    return {
        "base": "USD",
        "target": "USD",
        "rates_to_usd": rates_to_usd,
        "date": date,
        "source": clean(str(metadata.get("source") or source)),
    }


def existing_fx_metadata(existing_data: dict) -> dict | None:
    metadata = normalize_fx_metadata(existing_data.get("exchange_rates"), "existing data")
    if metadata:
        return metadata

    rates_to_usd = {"USD": 1.0}
    date = ""
    for item in existing_data.get("listings", []):
        currency = currency_code(item.get("currency"))
        rate = numeric_value(item.get("fx_rate_to_usd"))
        if currency and rate and rate > 0:
            rates_to_usd[currency] = round_rate(rate)
            date = date or clean(str(item.get("fx_rate_date") or ""))
    if date and len(rates_to_usd) > 1:
        return {
            "base": "USD",
            "target": "USD",
            "rates_to_usd": rates_to_usd,
            "date": date,
            "source": "existing listing fx metadata",
        }
    return None


def usd_only_fx_metadata() -> dict:
    return {
        "base": "USD",
        "target": "USD",
        "rates_to_usd": {"USD": 1.0},
        "date": datetime.now(timezone.utc).date().isoformat(),
        "source": "USD-only fallback",
    }


def resolve_fx_metadata(existing_data: dict) -> dict:
    fetched = fetch_current_fx_metadata()
    if fetched:
        return fetched
    existing = existing_fx_metadata(existing_data)
    if existing:
        print(f"WARN using existing FX rates from {existing['source']} for {existing['date']}")
        return existing
    print("WARN using USD-only FX metadata; non-USD prices cannot be normalized without rates")
    return usd_only_fx_metadata()


def post_webform(session: requests.Session, url: str, soup: BeautifulSoup, target: str, argument: str, log: SourceLog) -> str | None:
    data = {inp.get("name"): inp.get("value", "") for inp in soup.find_all("input") if inp.get("name")}
    data["__EVENTTARGET"] = target
    data["__EVENTARGUMENT"] = argument
    r = polite_request(
        "POST",
        url,
        log=log,
        kind=f"postback {target}",
        session=session,
        headers={"User-Agent": UA, "Accept": "text/html", "Referer": url},
        timeout=30,
        data=data,
    )
    if r is None:
        return None
    if r.status_code >= 400:
        print(f"WARN {r.status_code}: {url} POST {target}")
        log.failed(url, f"postback {target} HTTP {r.status_code}")
        return None
    return r.text


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


def image_url_candidates(base: str, values) -> list[str]:
    urls = []
    seen = set()
    for value in values or []:
        image_url = safe_http_url(base, value)
        if not image_url or BAD_IMAGE_RE.search(image_url) or image_url in seen:
            continue
        urls.append(image_url)
        seen.add(image_url)
    return urls


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


def first_weighing_weight_g(text: str) -> float | None:
    match = re.search(rf"\bweigh(?:s|ing)?\s+({WEIGHT_NUMBER_RE})\s*(kg|kilograms?|g|gm|gms|gr|grs|grams?|mg|milligrams?|oz|ounces?)\b", text or "", re.I)
    if not match:
        return None
    value = num(match.group(1))
    return weight_to_g(value, match.group(2)) if value is not None else None


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


def canonical_lunar_subtype(value: str | None) -> str | None:
    text = clean(value or "")
    if not text:
        return None
    metbull_match = LUNAR_METBULL_TYPE_RE.fullmatch(text)
    if metbull_match:
        text = clean(metbull_match.group(1) or "")
    if not text:
        return None
    key = clean(text).lower()
    return LUNAR_SUBTYPE_CANONICAL.get(key)


def lunar_subtype_from_metbull_type(value: str | None) -> str | None:
    match = LUNAR_METBULL_TYPE_RE.fullmatch(clean(value or ""))
    if not match:
        return None
    return canonical_lunar_subtype(match.group(1))


def canonical_subtype(value: str | None) -> str | None:
    subtype = clean(value or "")
    if not subtype:
        return None
    lunar_subtype = canonical_lunar_subtype(subtype)
    if lunar_subtype:
        return lunar_subtype
    subtype = re.sub(r"\s*/\s*", "/", subtype)
    subtype = re.sub(r"\s*-\s*", "-", subtype)
    compact = compact_classification_token(subtype)
    if re.fullmatch(r"C[123]-UNG", compact):
        return compact
    if re.fullmatch(r"C[123]", compact):
        return compact
    if re.fullmatch(r"(?:CI|CM|CO|CV|CR|CK|CH|CB)-?\d(?:\.\d)?", compact):
        return compact.replace("-", "")
    compacted_range = re.fullmatch(r"(H|L|LL)([3-7])([3-7])", compact)
    if compacted_range:
        group, start, end = compacted_range.groups()
        return f"{group}{start}-{end}"
    ordinary = re.fullmatch(r"(H|L|LL)-?([3-7](?:\.\d)?)(?:([/\-])([3-7](?:\.\d)?))?", compact)
    if ordinary:
        group, number, separator, second_number = ordinary.groups()
        return f"{group}{number}{separator or ''}{second_number or ''}"
    mixed_ordinary = re.fullmatch(r"(H/L|L/LL|H/LL)-?([3-7](?:\.\d)?)", compact)
    if mixed_ordinary:
        return f"{mixed_ordinary.group(1)}{mixed_ordinary.group(2)}"
    if compact == "EH-MELTROCK":
        return "EH-MELT ROCK"
    enstatite = re.fullmatch(r"(EH|EL)-?([3-7])(?:([/\-])((?:EH|EL)?)([3-7]))?", compact)
    if enstatite:
        prefix, number, separator, second_prefix, second_number = enstatite.groups()
        if separator:
            return f"{prefix}{number}/{second_prefix}{second_number}"
        return f"{prefix}{number}"
    eucrite = re.fullmatch(r"EUCRITE-(MMICT|UNBR|PMICT|BR|MELTBRECCIA)", compact)
    if eucrite:
        qualifier = {"MELTBRECCIA": "melt breccia"}.get(eucrite.group(1), eucrite.group(1).lower())
        return f"Eucrite-{qualifier}"
    if compact == "ACHONDRITE-UNG":
        return "Achondrite-ung"
    if compact in {
        "OC",
        "H/L",
        "L(LL)3",
        "CBA",
        "CBB",
        "CVRED3",
        "CVOXA3",
        "HED",
        "EUC",
        "EUCRITE",
        "DIOGENITE",
        "HOWARDITE",
        "UREILITE",
        "AUBRITE",
        "ANGRITE",
        "BRACHINITE",
        "SHERGOTTITE",
        "NAKHLITE",
        "CHASSIGNITE",
        "OCTAHEDRITE",
        "ATAXITE",
        "HEXAHEDRITE",
        "ACAPULCOITE",
        "LODRANITE",
        "WINONAITE",
        "MESOSIDERITE",
        "PALLASITE",
        "ACHONDRITE",
        "IIA",
        "IAB",
        "IIAB",
        "IIIAB",
        "IIIE-AN",
        "IVA",
        "IVB",
        "IIE",
        "IRUNGR",
        "IC",
    }:
        return compact
    return subtype.upper()


def clean_classification_bit(value: str | None) -> str | None:
    bit = clean(value or "")
    if not bit:
        return None
    stone_match = re.fullmatch(r"Stone\s*\(([^)]*)\)", bit, re.I)
    if stone_match:
        bit = clean(stone_match.group(1))
    bit = re.sub(r"\bCampo\s+Del\s+Cielo\b", "Campo del Cielo", bit)
    if not bit or WEIGHT_RE.search(bit) or WEIGHT_RANGE_RE.search(bit) or DIMENSION_RE.search(bit):
        return None
    if CLASSIFICATION_PRODUCT_TEXT_RE.search(bit):
        return None
    if re.fullmatch(r"(?:stone|meteorites?|specimens?|pieces?|new\s+find)", bit, re.I):
        return None
    return bit


def meteorite_type_for_subtype(subtype: str | None) -> str | None:
    if re.fullmatch(r"Lunar(?:\s+Meteorite)?", clean(subtype or ""), re.I):
        return "lunar"
    if canonical_lunar_subtype(subtype):
        return "lunar"
    token = clean(subtype or "").upper()
    compact = compact_classification_token(token)
    if not compact:
        return None
    if compact in {"OC", "H/L", "H/L3", "L(LL)3"} or re.fullmatch(r"(?:H|L|LL)-?[3-7](?:\.\d)?(?:[/\-][3-7](?:\.\d)?)?|(?:H/L|L/LL|H/LL)-?[3-7](?:\.\d)?", compact):
        return "ordinary chondrite"
    if re.fullmatch(r"(?:CI|CM|CO|CV|CR|CK|CH|CB)-?\d(?:\.\d)?|C[123]-UNG", compact) or compact in {"C2", "C-2", "CBA", "CBB"} or re.fullmatch(r"CVOX[A-Z]?3|CVRED3", compact):
        return "carbonaceous chondrite"
    if re.fullmatch(r"(?:EH|EL)-?[3-7](?:\.\d)?(?:[/\-](?:EH|EL)?[3-7](?:\.\d)?)?|(?:R)-?[3-7](?:\.\d)?(?:-[3-7](?:\.\d)?)?|EH-MELTROCK", compact):
        return "chondrite"
    if re.fullmatch(r"(?:IIA|IAB|IIAB|IIIAB|IIIE-AN|IVA|IVB|IIE|IRUNGR|IC|OCTAHEDRITE|ATAXITE|HEXAHEDRITE)", compact):
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
    if re.fullmatch(r"EUCRITE-.+", compact):
        return "achondrite"
    return None


def subtype_priority(subtype: str | None) -> int:
    if canonical_lunar_subtype(subtype):
        return 80
    compact = compact_classification_token(subtype)
    if not compact:
        return 0
    if re.fullmatch(r"(?:IIA|IAB|IIAB|IIIAB|IIIE-AN|IVA|IVB|IIE|IRUNGR|IC)", compact):
        return 90
    if compact in {"OCTAHEDRITE", "ATAXITE", "HEXAHEDRITE"}:
        return 20
    if compact in {"ACHONDRITE", "EUCRITE", "EUC", "HED"}:
        return 30
    if re.fullmatch(r"EUCRITE-(?:MMICT|UNBR|PMICT|BR|MELTBRECCIA)", compact):
        return 80
    if compact == "ACHONDRITE-UNG":
        return 80
    if re.search(r"[/\-]|UNG|MELT", compact):
        return 70
    return 50


def best_subtype_from_text(text: str) -> str | None:
    subtypes = [canonical_subtype(match.group(0)) for match in SUBTYPE_RE.finditer(text)]
    subtypes = [subtype for subtype in subtypes if subtype]
    if not subtypes:
        return None
    return max(subtypes, key=subtype_priority)


def meteorite_family_key(mtype: str | None) -> str | None:
    if mtype in {"ordinary chondrite", "carbonaceous chondrite", "achondrite", "iron", "pallasite", "mesosiderite"}:
        return mtype
    if mtype in {"lunar", "martian"}:
        return mtype
    if mtype == "chondrite":
        return "chondrite"
    return None


def filtered_classification_text(ctext: str | None, mtype: str, subtype: str | None) -> str | None:
    if not ctext:
        return None
    target_family = meteorite_family_key(meteorite_type_for_subtype(subtype) or mtype)
    kept = []
    for bit in [clean_classification_bit(part) for part in ctext.split(",")]:
        if not bit:
            continue
        bit_family = meteorite_family_key(meteorite_type_for_subtype(bit))
        if target_family and bit_family and bit_family != target_family:
            continue
        if bit.lower() not in {value.lower() for value in kept}:
            kept.append(bit)
    return ", ".join(kept[:6]) or None


def normalized_classification(mtype: str, subtype: str | None, ctext: str | None) -> tuple[str, str | None, str | None]:
    subtype = canonical_subtype(subtype)
    subtype_type = meteorite_type_for_subtype(subtype)
    if mtype in {"lunar", "martian"} and subtype_type == "achondrite" and compact_classification_token(subtype) == "ACHONDRITE":
        subtype = None
        subtype_type = None
    if subtype_type:
        mtype = subtype_type
    return mtype, subtype, filtered_classification_text(ctext, mtype, subtype)


def merge_classification_text(ctext: str | None, *bits: str | None) -> str | None:
    kept = []
    for bit in [*(ctext or "").split(","), *bits]:
        cleaned = clean_classification_bit(bit)
        if cleaned and cleaned.lower() not in {value.lower() for value in kept}:
            kept.append(cleaned)
    return ", ".join(kept[:8]) or None


def subtype_is_more_specific(candidate: str | None, current: str | None) -> bool:
    candidate = canonical_subtype(candidate)
    current = canonical_subtype(current)
    if not candidate:
        return False
    if not current:
        return True
    candidate_compact = compact_classification_token(candidate)
    current_compact = compact_classification_token(current)
    if candidate_compact == current_compact:
        return candidate != current
    if candidate_compact.startswith(current_compact) and len(candidate_compact) > len(current_compact):
        return True
    if meteorite_type_for_subtype(candidate) != meteorite_type_for_subtype(current):
        return False
    return any(marker in candidate_compact for marker in ["/", "-UNG", "MELT", "MMICT", "UNBR", "PMICT", "BR"])


def classification_title_variants(title: str, url: str | None, mtype: str, subtype: str | None, ctext: str | None) -> tuple[str, str | None, str | None]:
    title_type, title_subtype, title_ctext = classify_from_text(clean(f"{title} {url or ''}"))
    if title_type != "unknown" and (mtype == "unknown" or title_type in {"lunar", "martian"}):
        mtype = title_type
    if subtype_is_more_specific(title_subtype, subtype):
        subtype = title_subtype
        ctext = merge_classification_text(ctext, title_ctext or title_subtype)
    elif title_ctext:
        ctext = merge_classification_text(ctext, title_ctext)
    return normalized_classification(mtype, subtype, ctext)


def numbered_identity_key(text: str | None) -> str | None:
    for candidate in [*catalog_name_candidates(text), *numbered_name_candidates(text)]:
        return normalize_name_key(candidate)
    return None


def wwmeteorites_without_conflicting_url_catalog(title: str, url: str | None, ctext: str | None) -> str | None:
    trusted_key = numbered_identity_key(title)
    url_key = numbered_identity_key(url_name_text(url))
    if not ctext or not trusted_key or not url_key or trusted_key == url_key:
        return ctext

    kept = []
    for bit in ctext.split(","):
        cleaned = clean_classification_bit(bit)
        if not cleaned:
            continue
        if numbered_identity_key(cleaned) == url_key:
            continue
        if cleaned.lower() not in {value.lower() for value in kept}:
            kept.append(cleaned)
    return ", ".join(kept[:8]) or None


def source_specific_classification(
    parser: str,
    title: str,
    url: str | None,
    detail_text: str,
    mtype: str,
    subtype: str | None,
    ctext: str | None,
) -> tuple[str, str | None, str | None]:
    haystack = clean(f"{title} {url or ''} {detail_text[:1200]}")
    title_url_haystack = clean(f"{title} {url or ''}")
    if parser == "fossilera" and re.search(r"\blunar(?:[-\s]+meteorite)?\b", title_url_haystack, re.I):
        mtype = "lunar"
        ctext = merge_classification_text(ctext, "Lunar Meteorite")
    if re.search(r"\btarda\b", haystack, re.I):
        mtype = "carbonaceous chondrite"
        subtype = "C2-UNG"
        ctext = merge_classification_text(ctext, "C2-UNG")
    if parser == "arizona_skies" and re.search(r"\b(?:baby\s+)?campocito\b", haystack, re.I):
        mtype = "iron"
        subtype = None
        ctext = "Campo del Cielo"
    if parser == "justmeteorites" and re.search(r"\bvaca[-\s]+muerta\b", haystack, re.I):
        mtype = "mesosiderite"
        subtype = "MESOSIDERITE"
        ctext = merge_classification_text("Vaca Muerta", "Mesosiderite")
    if parser == "justmeteorites" and re.search(r"\bmonturaqui\b", haystack, re.I) and re.search(r"\bimpactite|impact\s+(?:melt|glass)\b", haystack, re.I):
        mtype = "tektite/impactite"
        subtype = None
        ctext = merge_classification_text("Monturaqui", "impactite")
    if parser == "justmeteorites" and re.search(r"\bmonturaqui[-\s]+meteorite\b", haystack, re.I) and not re.search(r"\bimpactite|impact\s+(?:melt|glass)\b", haystack, re.I):
        mtype = "iron"
        subtype = "IAB"
        ctext = merge_classification_text("Monturaqui", "IAB")
    if parser == "meteorite_exchange" and re.search(r"\bnwa[-\s]+4799\b|eh[-\s]+melt[-\s]+rock", haystack, re.I):
        mtype = "chondrite"
        subtype = "EH-MELT ROCK"
        ctext = merge_classification_text("NWA 4799", "EH melt rock")
    if parser in {"galactic_stone", "galactic_stone_ecrater"} and re.search(r"\bkapustin[-\s]+yar\b", haystack, re.I):
        mtype = "ordinary chondrite"
        subtype = "L/LL6"
        ctext = merge_classification_text("Kapustin Yar", "L/LL6")
    if parser == "fossil_realm" and re.search(r"\baletai\b|huge-iron-meteorite-slice", haystack, re.I):
        mtype = "iron"
        subtype = "IIIE-AN"
        ctext = merge_classification_text("Aletai", "Medium Octahedrite", "IIIE-AN")
    if parser == "wwmeteorites" and re.search(r"\bpica\s+glass\b|\bmeteorite\s+impact\s+glass\b|\bimpact\s+glass\b", haystack, re.I):
        mtype = "tektite/impactite"
        ctext = merge_classification_text(ctext, "Meteorite impact glass")
    if parser == "wwmeteorites" and re.search(r"\bOC\s*4\b|\bOC4\b", haystack, re.I):
        mtype = "ordinary chondrite"
        ctext = merge_classification_text(ctext, "OC4")
    if parser == "wwmeteorites" and re.search(r"\bNEA\s*108\b|\bC\s*3\b", haystack, re.I):
        mtype = "carbonaceous chondrite"
        subtype = subtype or "C3"
        ctext = merge_classification_text(ctext, "C3")
    if parser == "wwmeteorites" and re.search(r"\bNWA\s*11086\b|\bCM[-\s]*Anomalous\b|\bCT\s*3\b", haystack, re.I):
        mtype = "carbonaceous chondrite"
        ctext = merge_classification_text(ctext, "CM-Anomalous", "proposed CT3")
    if parser == "wwmeteorites":
        ctext = wwmeteorites_without_conflicting_url_catalog(title, url, ctext)
    return normalized_classification(mtype, subtype, ctext)


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
    subtype = best_subtype_from_text(text)
    bits = []
    for m in re.finditer(
        r"\b(?:NWA\s*\d+|Northwest Africa\s*\d+|H\s?[3-6](?:\.\d)?(?:\s*[/\-]\s*[3-6](?:\.\d)?)?|(?:H/L|L/LL|H/LL)\s?[3-7](?:\.\d)?|H/L\s?3?|L\s?[3-6](?:\.\d)?(?:\s*[/\-]\s*[3-6](?:\.\d)?)?|LL\s?[3-7](?:\.\d)?(?:\s*[/\-]\s*[3-7](?:\.\d)?)?|L\s?\(\s?LL\s?\)\s?3|OC|C\s?[123]\s*-\s*ung|C\s?2|CM\s?2|CV\s?3|CVred\s?3|CVoxA\s?3|CO\s?3|CR\s?2|CI\s?1|CK\s?\d|CH\s?\d|CBa|CBb|R\s?[3-6](?:\s*-\s*[3-6])?|EH\s?[3-7](?:\s*[/\-]\s*(?:EH\s*)?[3-7])?|EL\s?[3-7](?:\s*[/\-]\s*(?:EL\s*)?[3-7])?|EH\s*-\s*melt\s+rock|IIA|IAB|IIAB|IIIAB|IIIE-AN|IVA|IVB|IIE|IRUNGR|EUC|eucrite(?:\s*-\s*(?:mmict|unbr|pmict|br|melt\s+breccia))?|diogenite|howardite|ureilite|aubrite|angrite|brachinite|achondrite(?:-ung)?|shergottite|nakhlite|pallasite|mesosiderite|octahedrite|ataxite|hexahedrite|campo\s+del\s+cielo)\b",
        text,
        re.I,
    ):
        bit = clean(m.group(0))
        if bit and bit.lower() not in {x.lower() for x in bits}:
            bits.append(bit)
    return normalized_classification(mtype, subtype, ", ".join(bits[:6]) or None)


def classification_from_metbull_type(metbull_type: str | None) -> tuple[str, str | None, str | None]:
    metbull_type = clean(metbull_type or "")
    if not metbull_type:
        return "unknown", None, None
    lunar_match = LUNAR_METBULL_TYPE_RE.fullmatch(metbull_type)
    if lunar_match:
        return "lunar", lunar_subtype_from_metbull_type(metbull_type), metbull_type
    return classify_from_text(metbull_type)


def apply_metbull_classification(
    canonical: dict,
    mtype: str,
    subtype: str | None,
    ctext: str | None,
) -> tuple[str, str | None, str | None]:
    if canonical.get("canonical_name_status") != "metbull_verified":
        return normalized_classification(mtype, subtype, ctext)
    if mtype == "tektite/impactite":
        return normalized_classification(mtype, subtype, ctext)
    official_type, official_subtype, official_text = classification_from_metbull_type(str(canonical.get("metbull_type") or ""))
    if official_type == "unknown":
        return normalized_classification(mtype, subtype, ctext)
    return normalized_classification(official_type, official_subtype, merge_classification_text(ctext, official_text))


def classify(title: str, detail_text: str = "", explicit_type: str | None = None) -> tuple[str, str | None, str | None]:
    priority_text = clean(" ".join(x for x in [title, explicit_type] if x))
    result = classify_from_text(priority_text)
    detail_result = classify_from_text(clean(f"{title} {detail_text[:2400]}"))
    if result[0] != "unknown" or result[1]:
        if detail_result[1] or detail_result[2]:
            return normalized_classification(result[0], result[1] or detail_result[1], result[2] or detail_result[2])
        return result
    if detail_result[0] != "unknown" or detail_result[1] or detail_result[2]:
        return detail_result
    return result


def product_title_has_meteorite_marker(title: str) -> bool:
    return bool(METEORITE_RE.search(title) or SUBTYPE_RE.search(title) or GALACTIC_STONE_TITLE_METEORITE_RE.search(title))


def image_urls_for(soup: BeautifulSoup, page_url: str) -> list[str]:
    values = []
    values.extend(og.get("content") for og in soup.find_all("meta", property="og:image"))
    values.extend(img.get("src") for img in soup.find_all("img"))
    return image_url_candidates(page_url, values)


def image_for(soup: BeautifulSoup, page_url: str) -> str | None:
    urls = image_urls_for(soup, page_url)
    return urls[0] if urls else None


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
    image_urls: list[str] | None = None,
    item_key: str | None = None,
    available: bool = True,
    parser: str | None = None,
) -> dict | None:
    raw_title = clean(title)
    if not raw_title or raw_title.lower() in {"meteorites", "books", "contact", "home", "welcome to baitylia"}:
        return None
    if not (METEORITE_RE.search(raw_title) or METEORITE_RE.search(detail_text) or explicit_type):
        return None
    parser_name = parser or site.get("parser") or "generic"
    title = display_title(raw_title, parser_name, url)
    canonical = canonical_name_info(raw_title, title, detail_text, url)
    if canonical.get("canonical_name_display") and canonical.get("canonical_name_status") in {"metbull_verified", "parsed_high"}:
        title = canonical["canonical_name_display"]
    mtype, subtype, ctext = classify(title, detail_text, explicit_type)
    mtype, subtype, ctext = classification_title_variants(title, url, mtype, subtype, ctext)
    mtype, subtype, ctext = source_specific_classification(parser_name, title, url, detail_text, mtype, subtype, ctext)
    mtype, subtype, ctext = apply_metbull_classification(canonical, mtype, subtype, ctext)
    available = bool(available) and not unavailable_status_text(f"{raw_title} {detail_text[:2000]}")
    ppg = round(price / weight_g, 4) if price and weight_g and weight_g > 0 else None
    image_candidates = []
    for candidate in [image_url, *(image_urls or [])]:
        candidate_url = safe_http_url(url, candidate)
        if candidate_url and not BAD_IMAGE_RE.search(candidate_url) and candidate_url not in image_candidates:
            image_candidates.append(candidate_url)
    primary_image_url = image_candidates[0] if image_candidates else None
    raw_id = f"{site['name']}|{url}|{item_key or raw_title}|{weight_g}|{price}".encode("utf-8", "ignore")
    item = {
        "id": hashlib.sha1(raw_id).hexdigest()[:16],
        "source": site["name"],
        "source_url": site["base_url"],
        "url": url,
        "title": title,
        "canonical_name": canonical.get("canonical_name"),
        "canonical_name_display": canonical.get("canonical_name_display"),
        "canonical_name_status": canonical.get("canonical_name_status"),
        "canonical_name_source": canonical.get("canonical_name_source"),
        "price": price,
        "currency": currency,
        "weight_g": round(weight_g, 4) if weight_g is not None else None,
        "price_per_g": ppg,
        "meteorite_type": mtype,
        "subtype": subtype,
        "classification_text": ctext,
        "image_url": primary_image_url,
        "confidence": confidence(price, weight_g, bool(re.search(r"[?&]id=\d+", url)), explicit_type),
        "available": available,
        "parser": parser_name,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }
    if len(image_candidates) > 1:
        item["image_urls"] = image_candidates
    for key in ["metbull_code", "metbull_status", "metbull_type"]:
        if key == "metbull_type" and mtype == "tektite/impactite":
            continue
        if canonical.get(key):
            item[key] = canonical[key]
    return item


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
        available=not unavailable_status_text(text),
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
    related_queue: list[str] = []
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
                related_queue.append(item["url"])

    processed_related_pages = set()
    while related_queue and len(processed_related_pages) < MAX_DETAIL_PAGES_PER_SITE:
        detail_url = related_queue.pop(0)
        if detail_url in processed_related_pages:
            continue
        processed_related_pages.add(detail_url)
        html = fetch(detail_url, log, "detail")
        time.sleep(DELAY)
        if not html:
            log.reject_page("baitylia_related_detail_fetch_failed")
            continue
        soup = BeautifulSoup(html, "lxml")
        if not re.search(r"\bmore\s+specimens?\s+of\b", soup.get_text(" ", strip=True), re.I):
            continue
        for card in soup.select(".card"):
            if not card_has_detail(card, detail_url, detail_re):
                continue
            related_url = None
            for a in card.find_all("a", href=True):
                href = urljoin(detail_url, a.get("href")).split("#", 1)[0]
                if same_domain(site["base_url"], href) and detail_re.search(url_path_query(href)):
                    related_url = href
                    break
            if not related_url or related_url in seen_urls:
                continue
            log.detail(related_url)
            item = inventory_card_listing(site, detail_url, card, detail_re, parser="baitylia", log=log)
            if not item or item["url"] in seen_urls:
                continue
            listings.append(item)
            seen_urls.add(item["url"])
            related_queue.append(item["url"])
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
        if re.search(r"(?:^|/)sold\.(?:jpe?g|png|gif)$", path, re.I) or unavailable_status_text(marker_text):
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
        or unavailable_status_text(text)
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
            if not label or unavailable_status_text(label):
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
    if state["sold"] or sold_now or unavailable_status_text(status_text):
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
            sold_now = bool(meteorlab_has_sold_image(cell) or unavailable_status_text(text))
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


def schema_image_urls(product: dict | None, page_url: str) -> list[str]:
    if not product:
        return []
    image = product.get("image")
    values = []
    if isinstance(image, list):
        for item in image:
            if isinstance(item, dict):
                values.append(item.get("url") or item.get("contentUrl"))
            else:
                values.append(item)
    elif isinstance(image, dict):
        values.append(image.get("url") or image.get("contentUrl"))
    else:
        values.append(image)
    return image_url_candidates(page_url, values)


def schema_image_url(product: dict | None, page_url: str) -> str | None:
    urls = schema_image_urls(product, page_url)
    return urls[0] if urls else None


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
            r"\s*(?:(?:For\s+Sale\s*)?-\s+|\|\s*)(?:FossilEra\.com|Aerolite Meteorites.*|Astro West.*|Meteorite Exchange.*|justMETEORITES|Impactika|SkyFall Meteorites.*|Meteolovers).*$",
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
    if parser == "fossilera":
        source_type = source_type or labeled_value(lines, "Type")
    text = "\n".join([x for x in [schema_description, *lines[:120]] if x])
    if reject_detail_re and reject_detail_re.search("\n".join([url, title, text[:2400]])):
        log.reject("product_non_individual_detail")
        return None
    availability = clean(str(offer.get("availability") or meta_content(soup, "product:availability") or ""))
    sold_text = False if ignore_text_sold else unavailable_status_text(text[:800])
    if unavailable_status_text(availability) or sold_text:
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
    if weight is None and parser == "prehistoric_fossils":
        weight = first_weighing_weight_g(text[:2000])
    if weight is None and not allow_missing_weight:
        log.reject("product_missing_weight")
        return None

    image_urls = []
    image_urls.extend(schema_image_urls(product, url))
    image_urls.extend(image_url_candidates(url, [meta_content(soup, "og:image", "twitter:image")]))
    if allow_image_fallback:
        image_urls.extend(image_urls_for(scope, url))
    item = make_listing(
        site,
        url,
        title,
        price=price,
        currency=currency or "USD",
        weight_g=weight,
        detail_text=text,
        explicit_type=source_type or fallback_type,
        image_url=image_urls[0] if image_urls else None,
        image_urls=image_urls,
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
    max_detail_pages: int | None = None,
) -> list[str]:
    details: dict[str, None] = {}
    detail_cap = max_detail_pages if max_detail_pages is not None else MAX_DETAIL_PAGES_PER_SITE
    queue = [urljoin(site["base_url"], url) for url in site.get("inventory_urls", [])]
    seen_indexes: set[str] = set()
    while queue and len(seen_indexes) < MAX_INDEX_PAGES_PER_SITE and len(details) < detail_cap:
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
            if len(details) >= detail_cap:
                break
            card_text = clean(card.get_text(" ", strip=True))
            card_classes = " ".join(card.get("class") or [])
            if unavailable_status_text(f"{card_text} {card_classes}"):
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
        if len(details) >= detail_cap:
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
    max_detail_pages: int | None = None,
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
        max_detail_pages=max_detail_pages,
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


def shopify_images(product: dict, base_url: str) -> list[str]:
    images = product.get("images") or []
    return image_url_candidates(base_url, [image.get("src") for image in images if isinstance(image, dict)])


def shopify_image(product: dict) -> str | None:
    images = shopify_images(product, "https://example.invalid/")
    return images[0] if images else None


def shopify_parser_title(parser: str, title: str) -> str:
    title = clean(title)
    if parser == "buy_meteorite":
        title = re.sub(r"\b(end\s*cut|endcut|slice|fragment|individual|specimen)(?=\d)", r"\1 ", title, flags=re.I)
        title = re.sub(rf"({WEIGHT_NUMBER_RE})\s*\.\s*(g|gm|gms|gr|grs|grams?)\b", r"\1 \2", title, flags=re.I)
    return title


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
    title = shopify_parser_title(parser, title)
    tag_text = "" if parser == "top_meteorite" else " ".join(shopify_tags(product))
    detail_text = clean(" ".join([html_to_text(product.get("body_html")), shopify_product_type(product), tag_text]))
    price = price_num(str(variant.get("price") or ""))
    weight = first_individual_weight_g(title, detail_text[:2400])
    reason = source_filter(product, title, detail_text, price, weight, variant)
    if reason:
        log.reject(reason)
        return None

    url = urljoin(site["base_url"], f"/products/{product.get('handle')}")
    images = shopify_images(product, url)
    item = make_listing(
        site,
        url,
        title,
        price=price,
        currency="USD" if price is not None else None,
        weight_g=weight,
        detail_text=detail_text,
        explicit_type=shopify_explicit_type(product, include_keyword_tags=parser != "top_meteorite"),
        image_url=images[0] if images else None,
        image_urls=images,
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


def astro_west_card_filter(card, page_url: str) -> str | None:
    classes = " ".join(card.get("class") or [])
    if not re.search(r"\btype-product\b", classes, re.I):
        return "astro_west_card_missing_type_product"
    if re.search(r"\bproduct_cat-(?:jewelry|meteorite-jewelry|box-sets?|display-box(?:es)?|collector-box(?:es)?)\b", classes, re.I):
        return "astro_west_non_specimen_category"
    title_node = card.select_one(".woocommerce-loop-product__title, h2, h3")
    title = clean(title_node.get_text(" ", strip=True) if title_node else "")
    haystack = clean(" ".join([title, card.get_text(" ", strip=True)]))
    if WEIGHT_RANGE_RE.search(title):
        return "astro_west_weight_range_title"
    if ASTRO_WEST_NON_SPECIMEN_RE.search(haystack) or NON_SPECIMEN_PRODUCT_RE.search(haystack):
        return "astro_west_non_specimen"
    if title and not product_title_has_meteorite_marker(title):
        return "astro_west_missing_title_meteorite_marker"
    return None


def astro_west_detail_proof(soup: BeautifulSoup, product: dict | None, offer: dict, url: str) -> str | None:
    if not re.fullmatch(r"/products/[^/?#]+/?", urlparse(url).path, re.I):
        return "astro_west_not_product_path"
    body_classes = " ".join(soup.body.get("class") or []) if soup.body else ""
    if not re.search(r"\bsingle-product\b", body_classes, re.I):
        return "astro_west_missing_single_product_body"
    product_node = soup.select_one("div[id^='product-'].product.type-product, div.product.type-product")
    if not product_node:
        return "astro_west_missing_type_product_detail"
    if clean(meta_content(soup, "og:type") or "").lower() != "product":
        return "astro_west_missing_product_meta"
    title = clean(meta_content(soup, "og:title", "twitter:title") or title_for(soup))
    category_text = clean(product_node.select_one(".product_meta").get_text(" ", strip=True) if product_node.select_one(".product_meta") else "")
    if ASTRO_WEST_CATEGORY_NON_SPECIMEN_RE.search(category_text):
        return "astro_west_non_specimen_category_detail"
    if ASTRO_WEST_NON_SPECIMEN_RE.search(title) or NON_SPECIMEN_PRODUCT_RE.search(title):
        return "astro_west_non_specimen_detail"
    if WEIGHT_RANGE_RE.search(title):
        return "astro_west_weight_range_title_detail"
    if not product_title_has_meteorite_marker(title):
        return "astro_west_missing_title_meteorite_marker_detail"
    if not (product_node.select_one(".single_add_to_cart_button") or product_node.select_one("form.cart")):
        return "astro_west_missing_add_to_cart"
    return None


def prehistoric_fossils_card_filter(card, page_url: str) -> str | None:
    classes = " ".join(card.get("class") or [])
    if not re.search(r"\btype-product\b", classes, re.I):
        return "prehistoric_card_missing_type_product"
    title_node = card.select_one(".woocommerce-loop-product__title, h2, h3")
    title = clean(title_node.get_text(" ", strip=True) if title_node else "")
    haystack = clean(" ".join([title, card.get_text(" ", strip=True), classes]))
    if PREHISTORIC_FOSSILS_NON_SPECIMEN_RE.search(haystack) or NON_SPECIMEN_PRODUCT_RE.search(haystack):
        return "prehistoric_non_specimen"
    if WEIGHT_RANGE_RE.search(title):
        return "prehistoric_weight_range_title"
    if title and not product_title_has_meteorite_marker(title):
        return "prehistoric_missing_title_meteorite_marker"
    return None


def prehistoric_fossils_detail_proof(soup: BeautifulSoup, product: dict | None, offer: dict, url: str) -> str | None:
    if not re.fullmatch(r"/product/[^/?#]+/?", urlparse(url).path, re.I):
        return "prehistoric_not_product_path"
    body_classes = " ".join(soup.body.get("class") or []) if soup.body else ""
    if not re.search(r"\bsingle-product\b", body_classes, re.I):
        return "prehistoric_missing_single_product_body"
    product_node = soup.select_one("div[id^='product-'].product.type-product, div.product.type-product")
    if not product_node:
        return "prehistoric_missing_type_product_detail"
    title = clean(meta_content(soup, "og:title", "twitter:title") or title_for(soup))
    category_text = clean(product_node.select_one(".product_meta").get_text(" ", strip=True) if product_node.select_one(".product_meta") else "")
    if PREHISTORIC_FOSSILS_NON_SPECIMEN_RE.search(f"{title} {category_text}") or NON_SPECIMEN_PRODUCT_RE.search(f"{title} {category_text}"):
        return "prehistoric_non_specimen_detail"
    if WEIGHT_RANGE_RE.search(title):
        return "prehistoric_weight_range_title_detail"
    if not product_title_has_meteorite_marker(title):
        return "prehistoric_missing_title_meteorite_marker_detail"
    if not (product_node.select_one(".single_add_to_cart_button") or product_node.select_one("form.cart") or re.search(r"\bin\s+stock\b", product_node.get_text(" ", strip=True), re.I)):
        return "prehistoric_missing_stock_or_cart"
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


def galactic_stone_ecrater_card_title(card) -> str:
    link = card.select_one('a[href*="/p/"]')
    image = card.find("img")
    values = [
        link.get("title") if link else None,
        image.get("title") if image else None,
        image.get("alt") if image else None,
        link.get_text(" ", strip=True) if link else None,
    ]
    return next((clean(str(value)) for value in values if clean(str(value or ""))), "")


def galactic_stone_ecrater_card_filter(card, page_url: str) -> str | None:
    link = card.select_one('a[href*="/p/"]')
    if not link:
        return "galactic_ecrater_card_missing_product_link"
    href = urljoin(page_url, link.get("href")).split("#", 1)[0]
    if not same_domain("https://galacticstone.ecrater.com/", href):
        return "galactic_ecrater_card_external_link"
    if not GALACTIC_STONE_ECRATER_PRODUCT_RE.fullmatch(urlparse(href).path):
        return "galactic_ecrater_card_non_product_link"

    title = galactic_stone_ecrater_card_title(card)
    if not title:
        return "galactic_ecrater_card_missing_title"
    text = clean(card.get_text(" ", strip=True))
    haystack = clean(f"{title} {text}")
    price, _ = first_price(text)
    if price is None or price <= 0:
        return "galactic_ecrater_card_missing_price"
    if GALACTIC_STONE_NON_SPECIMEN_RE.search(haystack) or NON_SPECIMEN_PRODUCT_RE.search(haystack):
        return "galactic_ecrater_non_specimen"
    if not product_title_has_meteorite_marker(title):
        return "galactic_ecrater_missing_title_meteorite_marker"
    return None


def galactic_stone_ecrater_detail_proof(soup: BeautifulSoup, product: dict | None, offer: dict, url: str) -> str | None:
    if not GALACTIC_STONE_ECRATER_PRODUCT_RE.fullmatch(urlparse(url).path):
        return "galactic_ecrater_not_product_path"
    if clean(meta_content(soup, "og:type") or "").lower() != "ecrater:item":
        return "galactic_ecrater_missing_item_meta"
    store = clean(meta_content(soup, "ecrater:store") or "").lower()
    if "galacticstone.ecrater.com" not in store:
        return "galactic_ecrater_wrong_store"
    if not soup.select_one('a[href^="/addtocart.php?pid="], a[href*="/addtocart.php?pid="]'):
        return "galactic_ecrater_missing_add_to_cart"

    price = num(meta_content(soup, "ecrater:price_value"))
    if price is None or price <= 0:
        return "galactic_ecrater_missing_price_meta"
    title = clean(meta_content(soup, "og:title", "twitter:title") or title_for(soup))
    category_text = clean(" ".join(a.get_text(" ", strip=True) for a in soup.select('a[href*="/c/135113977/meteorites"]')))
    if not category_text:
        return "galactic_ecrater_not_meteorites_category"
    visible_text = clean(soup.get_text(" ", strip=True)[:3000])
    haystack = clean(f"{title} {category_text} {visible_text[:1600]}")
    if GALACTIC_STONE_NON_SPECIMEN_RE.search(haystack) or NON_SPECIMEN_PRODUCT_RE.search(haystack):
        return "galactic_ecrater_non_specimen_detail"
    if WEIGHT_RANGE_RE.search(title):
        return "galactic_ecrater_weight_range_title"
    if not product_title_has_meteorite_marker(title):
        return "galactic_ecrater_missing_title_meteorite_marker_detail"
    if first_individual_weight_g(title, visible_text[:1600]) is None:
        return "galactic_ecrater_missing_exact_weight"
    return None


def meteor_center_price(card) -> tuple[float | None, str | None]:
    nodes = card.select(".price .woocommerce-Price-amount, .price .amount")
    price_text = clean(nodes[-1].get_text(" ", strip=True) if nodes else "")
    if not price_text:
        price_text = clean(card.select_one(".price").get_text(" ", strip=True) if card.select_one(".price") else "")
    amount_text = re.sub(r"[^0-9,.]", "", price_text.replace("\xa0", "").replace(" ", ""))
    currency = "EUR" if "€" in price_text or re.search(r"\bEUR\b", price_text, re.I) else None
    return price_num(amount_text, european=True), currency


def collecting_meteorites_display_title(title: str, url: str) -> str:
    candidate = clean(re.split(r"\s+(?:-|\u2013|\u2014)\s+", title, maxsplit=1)[0])
    weight_match = WEIGHT_RE.search(candidate)
    if weight_match:
        candidate = clean(candidate[: weight_match.start()])
    candidate = clean(re.sub(r"^(?:(?:big|large|small|nice|beautiful|amazing|great|fantastic)\s+)?(?:piece|slice|part|end\s*piece|fragment|specimen)\s+of\s+", "", candidate, flags=re.I))
    candidate = clean(
        re.sub(
            r"\b(?:iron\s+meteorite|meteorite|chondrite|achondrite|eucrite|diogenite|howardite|aubrite|ureilite|"
            r"shergottite|nakhlite|pallasite|mesosiderite|ataxite|octahedrite|hexahedrite|"
            r"IAB|IIAB|IIIAB|IIIE(?:\s*-?\s*AN|\s+an)?|IVA|IVB|IIE|IICD|IIC|IID|IIIF|IC|"
            r"(?:H|L|LL|EH|EL|R|CI|CM|CO|CV|CR|CK|CH|CB|C)\s*-?\s*\d(?:\.\d)?)\b.*$",
            "",
            candidate,
            flags=re.I,
        )
    )
    identity = product_identity_from_title(candidate)
    if identity and not GENERIC_DISPLAY_ADJECTIVE_RE.fullmatch(identity):
        return identity
    context = f"{title} {url_name_text(url)}"
    if re.search(r"\bHED\b", context, re.I):
        return "HED achondrite"
    if re.search(r"\bNWA\b.*\bunclass", context, re.I):
        return "Unclassified NWA"
    url_identity = product_identity_from_url(url)
    if url_identity and not re.search(r"\b(?:fresh|amazing|great|beautiful|oriented)\b", url_identity, re.I):
        return url_identity
    classification_title = classification_display_from_context(context)
    if classification_title:
        return classification_title
    return tidy_display_candidate(candidate) or clean(title)


def collecting_meteorites_price(price_line: str) -> tuple[float | None, str | None, bool]:
    price_line = clean(price_line)
    if unavailable_status_text(price_line):
        return None, None, True
    sign = None
    direct_match = re.search(r"\bPrice\s*:?\s*(?P<sign>[-\u2212])?\s*(?P<amount>[0-9][0-9\s.,]*)(?P<symbol>€|EUR|Euro|US\$|USD|\$)?", price_line, re.I)
    if direct_match:
        sign = direct_match.group("sign")
        amount = direct_match.group("amount")
        symbol = direct_match.group("symbol")
    else:
        match = WWMETEORITES_PRICE_RE.search(price_line)
        if not match:
            return None, None, False
        amount = match.group("amount_before") or match.group("amount_after")
        symbol = match.group("symbol_before") or match.group("symbol_after")
    currency = currency_code(symbol)
    if not currency and re.search(r"€|\bEUR\b|\bEuro\b", price_line, re.I):
        currency = "EUR"
    if not currency:
        currency = "EUR"
    amount = re.sub(r"\s+", "", amount or "")
    value = price_num(amount, european=currency == "EUR")
    if sign and value is not None:
        value = -value
    return value, currency, False


def collecting_meteorites_price_line(lines: list[str]) -> str:
    for idx, line in enumerate(lines):
        if not re.match(r"^Price\b", line, re.I):
            continue
        parts = [line]
        for next_line in lines[idx + 1: idx + 4]:
            if re.fullmatch(r"(?:(?:€|EUR|Euro|US\$|USD|\$)?\s*/\s*g|(?:€|EUR|Euro|US\$|USD|\$)?\s*/\s*gram|per\s+gram|€|EUR|Euro|US\$|USD|\$)", next_line, re.I):
                parts.append(next_line)
                continue
            break
        return clean(" ".join(parts))
    return ""


def collecting_meteorites_detail_info(href: str, log: SourceLog, headers: dict) -> tuple[float | None, str | None, str] | None:
    log.detail(href)
    html = fetch(href, log, "detail", headers=headers)
    if not html:
        log.reject("collecting_detail_fetch_failed")
        return None
    soup = BeautifulSoup(html, "lxml")
    content = soup.select_one(".entry-content") or soup.select_one("article") or soup
    lines = lines_from(content)
    detail_text = clean(" ".join(lines[:80]))
    price_line = collecting_meteorites_price_line(lines)
    if not price_line:
        log.reject("collecting_detail_missing_price")
        return None
    if re.search(r"(?:/\s*g|/\s*gram|per\s+gram)", price_line, re.I):
        log.reject("collecting_detail_per_gram_price")
        return None
    price, currency, unavailable = collecting_meteorites_price(price_line)
    if unavailable:
        log.reject("collecting_detail_unavailable_price")
        return None
    if price is None:
        log.reject("collecting_detail_unparsed_price")
        return None
    if price <= 0:
        log.reject("collecting_detail_non_positive_price")
        return None
    return price, currency or "EUR", detail_text


def collecting_meteorites_card_listing(site: dict, page_url: str, card, log: SourceLog, headers: dict) -> dict | None:
    title_node = card.select_one("h2.entry-title a, .entry-title a")
    title = clean(title_node.get_text(" ", strip=True) if title_node else "")
    href = urljoin(page_url, title_node.get("href") if title_node else "").split("#", 1)[0]
    if not title or not href or not same_domain(site["base_url"], href):
        log.reject("collecting_missing_title_or_url")
        return None
    if unavailable_status_text(title):
        log.reject("collecting_unavailable")
        return None
    if NON_SPECIMEN_PRODUCT_RE.search(title):
        log.reject("collecting_non_specimen")
        return None
    if re.search(r"\b(?:various|assorted|choose|ask\s+for\s+size|sizes?\s+you\s+need)\b", title, re.I):
        log.reject("collecting_ambiguous_multi_specimen")
        return None
    if WEIGHT_RANGE_RE.search(title):
        log.reject("collecting_weight_range_title")
        return None
    if not product_title_has_meteorite_marker(title):
        log.reject("collecting_missing_title_meteorite_marker")
        return None
    weight = first_individual_weight_g(title, title_only=True)
    if weight is None:
        log.reject("collecting_missing_title_weight")
        return None
    image = card.select_one(".post-thumb img, img.wp-post-image")
    image_urls = image_url_candidates(href, [image.get("src") if image else None])
    category_text = clean(" ".join(a.get_text(" ", strip=True) for a in card.select(".cat-links a")))
    detail_info = collecting_meteorites_detail_info(href, log, headers)
    if not detail_info:
        return None
    price, currency, detail_body = detail_info
    detail_text = clean(f"{title} {category_text} {' '.join(card.get('class') or [])} {detail_body[:1800]}")
    item_id = clean(str(card.get("id") or "")) or href.rstrip("/").rsplit("/", 1)[-1]
    display_title = collecting_meteorites_display_title(title, href)
    item = make_listing(
        site,
        href,
        display_title,
        price=price,
        currency=currency,
        weight_g=weight,
        detail_text=detail_text,
        explicit_type=category_text or "meteorite",
        image_url=image_urls[0] if image_urls else None,
        image_urls=image_urls,
        item_key=item_id,
        parser="collecting_meteorites",
    )
    if not item:
        log.reject("make_listing_filtered")
        return None
    log.detail(href)
    log.parsed_listing()
    return item


def scrape_collecting_meteorites(site: dict, log: SourceLog) -> list[dict]:
    headers = {"User-Agent": BROWSER_UA, "Accept": "text/html,application/xhtml+xml"}
    listings = []
    seen: set[str] = set()
    max_products = site_int(site, "max_products", 140, 200)
    for url in site.get("inventory_urls", []):
        page_url = urljoin(site["base_url"], url)
        log.index(page_url)
        html = fetch(page_url, log, "index", headers=headers)
        time.sleep(DELAY)
        if not html:
            log.reject_page("collecting_index_fetch_failed")
            continue
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select(".blog-post-repeat article")
        if not cards:
            log.reject_page("collecting_no_listing_cards")
        for card in cards:
            if len(listings) >= max_products:
                break
            item = collecting_meteorites_card_listing(site, page_url, card, log, headers)
            if not item:
                continue
            if item["id"] in seen:
                log.reject("collecting_duplicate_item")
                continue
            seen.add(item["id"])
            listings.append(item)
    return listings


def meteor_center_display_title(title: str, url: str) -> str:
    leading = re.split(r"\s+(?:-|\u2013|\u2014)\s+", title, maxsplit=1)[0]
    without_parenthetical = clean(re.sub(r"\s*\([^)]*\)\s*$", "", leading))
    candidates = [without_parenthetical, leading, title]
    for candidate in candidates:
        identity = product_identity_from_title(candidate)
        if identity and not re.search(r"\([^)]*$", identity):
            return identity
    url_identity = product_identity_from_url(url)
    if url_identity:
        return url_identity
    return tidy_display_candidate(without_parenthetical or leading) or clean(title)


def meteor_center_card_listing(site: dict, page_url: str, card, log: SourceLog) -> dict | None:
    classes = " ".join(card.get("class") or [])
    if not re.search(r"\btype-product\b", classes, re.I):
        log.reject("meteor_center_card_missing_type_product")
        return None
    if not re.search(r"\binstock\b", classes, re.I):
        log.reject("meteor_center_card_not_in_stock")
        return None
    if not (re.search(r"\bpurchasable\b", classes, re.I) or card.select_one(".add_to_cart_button")):
        log.reject("meteor_center_missing_add_to_cart")
        return None

    title_node = card.select_one(".woocommerce-loop-product__title, h2, h3")
    title = clean(title_node.get_text(" ", strip=True) if title_node else "")
    if not title:
        log.reject("meteor_center_missing_title")
        return None
    text = clean(card.get_text(" ", strip=True))
    haystack = clean(f"{title} {text} {classes}")
    if unavailable_status_text(haystack):
        log.reject("meteor_center_unavailable")
        return None
    if NON_SPECIMEN_PRODUCT_RE.search(haystack):
        log.reject("meteor_center_non_specimen")
        return None
    if re.search(r"\bnon[-\s]+impactite\b", haystack, re.I):
        log.reject("meteor_center_non_impactite")
        return None
    if re.search(r"\b(?:of|lot|set|bag)\s+(?:fragments?|pieces?|individuals?|slices?)\b", title, re.I):
        log.reject("meteor_center_multi_piece_title")
        return None
    if WEIGHT_RANGE_RE.search(title):
        log.reject("meteor_center_weight_range_title")
        return None
    if not product_title_has_meteorite_marker(title):
        log.reject("meteor_center_missing_title_meteorite_marker")
        return None

    weight = first_individual_weight_g(title, title_only=True)
    if weight is None:
        log.reject("meteor_center_missing_title_weight")
        return None
    price, currency = meteor_center_price(card)
    if price is None or price <= 0:
        log.reject("meteor_center_missing_price")
        return None

    detail_url = None
    detail_re = re.compile(r"^/product/[^/?#]+/?$", re.I)
    for a in card.find_all("a", href=True):
        href = urljoin(page_url, a.get("href")).split("#", 1)[0]
        if same_domain(site["base_url"], href) and detail_re.fullmatch(urlparse(href).path):
            detail_url = href
            break
    if not detail_url:
        log.reject("meteor_center_missing_detail_url")
        return None
    log.detail(detail_url)
    display_title = meteor_center_display_title(title, detail_url)

    categories = [cls.removeprefix("product_cat-").replace("-", " ") for cls in card.get("class") or [] if cls.startswith("product_cat-")]
    image = card.find("img")
    image_urls = image_url_candidates(detail_url, [image.get("src") if image else None])
    add_button = card.select_one(".add_to_cart_button[data-product_id]")
    product_id = clean(str(add_button.get("data-product_id") if add_button else ""))
    if not product_id:
        post_class = next((cls for cls in card.get("class") or [] if re.fullmatch(r"post-\d+", cls)), "")
        product_id = post_class.removeprefix("post-")

    item = make_listing(
        site,
        detail_url,
        display_title,
        price=price,
        currency=currency or "EUR",
        weight_g=weight,
        detail_text=haystack,
        explicit_type=", ".join(categories) or "meteorite",
        image_url=image_urls[0] if image_urls else None,
        image_urls=image_urls,
        item_key=product_id or title,
        parser="meteor_center",
    )
    if not item:
        log.reject("make_listing_filtered")
        return None
    log.parsed_listing()
    return item


def scrape_meteor_center(site: dict, log: SourceLog) -> list[dict]:
    headers = {"User-Agent": BROWSER_UA, "Accept": "text/html,application/xhtml+xml"}
    queue = [urljoin(site["base_url"], url) for url in site.get("inventory_urls", [])]
    seen_indexes: set[str] = set()
    seen_items: set[str] = set()
    listings = []
    max_index_pages = site_int(site, "max_index_pages", 30, 40)
    max_products = site_int(site, "max_products", 340, 400)
    while queue and len(seen_indexes) < max_index_pages and len(listings) < max_products:
        page_url = queue.pop(0).split("#", 1)[0]
        if page_url in seen_indexes:
            continue
        seen_indexes.add(page_url)
        log.index(page_url)
        html = fetch(page_url, log, "index", headers=headers)
        time.sleep(DELAY)
        if not html:
            log.reject_page("meteor_center_index_fetch_failed")
            continue
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("ul.products li.product")
        if not cards:
            log.reject_page("meteor_center_no_product_cards")
        for card in cards:
            item = meteor_center_card_listing(site, page_url, card, log)
            if not item:
                continue
            if item["id"] in seen_items:
                log.reject("meteor_center_duplicate_item")
                continue
            seen_items.add(item["id"])
            listings.append(item)
            if len(listings) >= max_products:
                break
        next_link = soup.select_one("a.next.page-numbers, a.next")
        if next_link and next_link.get("href") and len(listings) < max_products:
            next_url = urljoin(page_url, next_link.get("href")).split("#", 1)[0]
            if same_domain(site["base_url"], next_url) and next_url not in seen_indexes and next_url not in queue:
                queue.append(next_url)
    return listings


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


def scrape_astro_west(site: dict, log: SourceLog) -> list[dict]:
    detail_re = re.compile(r"^/products/[^/?#]+/?$", re.I)
    headers = {"User-Agent": BROWSER_UA, "Accept": "text/html,application/xhtml+xml"}
    link_reject_re = re.compile(
        r"(?:[?&](?:add-to-cart|orderby|s)=|/(?:cart|checkout|my-account|wishlist)(?:/|$)|/wp-json/|/feed/?$)",
        re.I,
    )
    return scrape_product_card_details(
        site,
        log,
        "astro_west",
        detail_re,
        ["li.product", ".wc-block-grid__product"],
        fallback_type="meteorite",
        headers=headers,
        card_reject_re=ASTRO_WEST_NON_SPECIMEN_RE,
        reject_title_re=ASTRO_WEST_NON_SPECIMEN_RE,
        reject_detail_re=ASTRO_WEST_NON_SPECIMEN_RE,
        require_title_meteorite=True,
        reject_weight_range_title=True,
        card_filter=astro_west_card_filter,
        link_reject_re=link_reject_re,
        detail_proof=astro_west_detail_proof,
        max_detail_pages=site_int(site, "max_detail_pages", 80, 150),
    )


def scrape_prehistoric_fossils(site: dict, log: SourceLog) -> list[dict]:
    detail_re = re.compile(r"^/product/[^/?#]+/?$", re.I)
    headers = {"User-Agent": BROWSER_UA, "Accept": "text/html,application/xhtml+xml"}
    link_reject_re = re.compile(
        r"(?:[?&](?:add-to-cart|orderby|s)=|/(?:cart|checkout|my-account|wishlist)(?:/|$)|/wp-json/|/feed/?$)",
        re.I,
    )
    return scrape_product_card_details(
        site,
        log,
        "prehistoric_fossils",
        detail_re,
        ["li.product", ".wc-block-grid__product"],
        fallback_type="meteorite",
        headers=headers,
        card_reject_re=PREHISTORIC_FOSSILS_NON_SPECIMEN_RE,
        reject_title_re=PREHISTORIC_FOSSILS_NON_SPECIMEN_RE,
        require_title_meteorite=True,
        reject_weight_range_title=True,
        card_filter=prehistoric_fossils_card_filter,
        link_reject_re=link_reject_re,
        detail_proof=prehistoric_fossils_detail_proof,
        max_detail_pages=site_int(site, "max_detail_pages", 140, 180),
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


def scrape_galactic_stone_ecrater(site: dict, log: SourceLog) -> list[dict]:
    return scrape_product_card_details(
        site,
        log,
        "galactic_stone_ecrater",
        GALACTIC_STONE_ECRATER_PRODUCT_RE,
        [".galleryBorder_g"],
        fallback_type="meteorite",
        card_reject_re=GALACTIC_STONE_NON_SPECIMEN_RE,
        reject_title_re=GALACTIC_STONE_NON_SPECIMEN_RE,
        reject_detail_re=GALACTIC_STONE_NON_SPECIMEN_RE,
        require_title_meteorite=True,
        card_filter=galactic_stone_ecrater_card_filter,
        detail_proof=galactic_stone_ecrater_detail_proof,
        max_detail_pages=site_int(site, "max_detail_pages", 30, 80),
    )


def fossil_realm_filter(product: dict, title: str, detail_text: str, price: float | None, weight: float | None, variant: dict) -> str | None:
    if shopify_product_type(product).lower() != "meteorites":
        return "fossil_realm_non_meteorite_type"
    if SHOPIFY_PLACEHOLDER_PRICE_RE.search(detail_text) or price is None or price <= 0 or price >= 1_000_000:
        return "fossil_realm_placeholder_price"
    if first_weight_g(title) is None:
        return "fossil_realm_missing_title_weight"
    if NON_SPECIMEN_PRODUCT_RE.search(title) or unavailable_status_text(title):
        return "fossil_realm_non_specimen"
    return None


def scrape_fossil_realm(site: dict, log: SourceLog) -> list[dict]:
    return scrape_shopify_products_json(site, log, "fossil_realm", fossil_realm_filter)


def top_meteorite_filter(product: dict, title: str, detail_text: str, price: float | None, weight: float | None, variant: dict) -> str | None:
    if shopify_product_type(product).lower() != "specimen":
        return "top_non_specimen_type"
    if not (METEORITE_RE.search(title) or METEORITE_RE.search(detail_text)):
        return "top_missing_meteorite_keyword"
    if NON_SPECIMEN_PRODUCT_RE.search(title) or unavailable_status_text(title):
        return "top_non_specimen_title"
    if SHOPIFY_PLACEHOLDER_PRICE_RE.search(detail_text) or price is None or price <= 0 or price >= 1_000_000:
        return "top_missing_price"
    if first_weight_g(title) is None:
        return "top_missing_title_weight"
    return None


def scrape_top_meteorite(site: dict, log: SourceLog) -> list[dict]:
    return scrape_shopify_products_json(site, log, "top_meteorite", top_meteorite_filter)


def buy_meteorite_filter(product: dict, title: str, detail_text: str, price: float | None, weight: float | None, variant: dict) -> str | None:
    ptype = shopify_product_type(product).lower()
    tags = {tag.lower() for tag in shopify_tags(product)}
    if "meteorite" not in ptype or "meteorite" not in tags:
        return "buy_meteorite_non_meteorite_type"
    if not (METEORITE_RE.search(title) or METEORITE_RE.search(detail_text) or SUBTYPE_RE.search(title) or SUBTYPE_RE.search(detail_text)):
        return "buy_meteorite_missing_meteorite_marker"
    if NON_SPECIMEN_PRODUCT_RE.search(title) or unavailable_status_text(title):
        return "buy_meteorite_non_specimen_title"
    if SHOPIFY_PLACEHOLDER_PRICE_RE.search(detail_text) or price is None or price <= 0 or price >= 1_000_000:
        return "buy_meteorite_missing_price"
    if first_weight_g(title) is None or weight is None:
        return "buy_meteorite_missing_title_weight"
    if not shopify_image(product):
        return "buy_meteorite_missing_image"
    return None


def scrape_buy_meteorite(site: dict, log: SourceLog) -> list[dict]:
    return scrape_shopify_products_json(site, log, "buy_meteorite", buy_meteorite_filter)


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
                if not price_text or unavailable_status_text(price_text):
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
        if arizona_reject_text(haystack) or unavailable_status_text(nearby_text):
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
    if unavailable_status_text(text):
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
        if unavailable_status_text(line):
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
    return not unavailable_status_text(status_text) and not re.search(r"\bon\s+backorder\b", status_text, re.I)


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


def impactika_image_urls(product: dict, base_url: str) -> list[str]:
    return image_url_candidates(base_url, [image.get("src") for image in product.get("images") or [] if isinstance(image, dict)])


def impactika_image_url(product: dict, base_url: str) -> str | None:
    urls = impactika_image_urls(product, base_url)
    return urls[0] if urls else None


def impactika_inventory_code(text: str | None) -> str | None:
    match = re.search(r"\b(?:AB|AC|CM|OC)\s*-?\s*\d+[A-Za-z]?\b", text or "", re.I)
    if not match:
        return None
    return re.sub(r"\s+", "", match.group(0).upper())


def impactika_row_image_urls(product: dict, base_url: str, line: str) -> list[str]:
    urls = impactika_image_urls(product, base_url)
    code = impactika_inventory_code(line)
    if not code:
        return urls
    code_key = re.sub(r"[^a-z0-9]", "", code.lower())
    matched = []
    remaining = []
    for image_url in urls:
        image_key = re.sub(r"[^a-z0-9]", "", unquote(urlparse(image_url).path.rsplit("/", 1)[-1]).lower())
        if code_key and code_key in image_key:
            matched.append(image_url)
        else:
            remaining.append(image_url)
    return [*matched, *remaining]


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


def impactika_name_from_url(url: str | None) -> str | None:
    if not url:
        return None
    slug = unquote(urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]).lower()
    if not slug:
        return None
    if slug in IMPACTIKA_URL_NAME_OVERRIDES:
        return IMPACTIKA_URL_NAME_OVERRIDES[slug]
    tokens = clean(re.sub(r"[-_]+", " ", slug)).split()
    cleaned = []
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if IMPACTIKA_INVENTORY_CODE_RE.fullmatch(token):
            idx += 1
            continue
        if IMPACTIKA_SPLIT_INVENTORY_CODE_RE.fullmatch(token) and idx + 1 < len(tokens) and re.fullmatch(r"\d+[A-Za-z]?", tokens[idx + 1], re.I):
            idx += 2
            continue
        cleaned.append(token)
        idx += 1
    while len(cleaned) > 1 and re.fullmatch(r"\d+", cleaned[0]):
        cleaned.pop(0)
    if len(cleaned) > 1 and re.fullmatch(r"[2-9]", cleaned[-1]) and cleaned[0].lower() not in {"nwa", "nea", "dag", "dhofar", "sau", "jah", "ras"}:
        cleaned.pop()
    candidate = clean(" ".join(cleaned))
    return display_case_name(candidate.title()) if candidate else None


def impactika_display_name(name: str, url: str | None = None) -> str:
    display = impactika_name_from_url(url) or clean(name.title())
    return re.sub(r"\b(Nwa|Dag|Nakhla|Nininger)\b", lambda m: {"Nwa": "NWA", "Dag": "DaG"}.get(m.group(1), m.group(1)), display)


def impactika_row_title(name: str, url: str | None, line: str) -> str:
    code = impactika_inventory_code(line)
    display_name = impactika_display_name(name, url)
    if code and not re.search(rf"\b{re.escape(code)}\b", display_name, re.I):
        return clean(f"{display_name} - {code}")
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
                if unavailable_status_text(line) and WEIGHT_RE.search(line):
                    log.reject("impactika_sold_row")
                    continue
                if not (PRICE_RE.search(line) and WEIGHT_RE.search(line)):
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
                image_urls = impactika_row_image_urls(product, permalink, line)
                item = make_listing(
                    site,
                    permalink,
                    impactika_row_title(name, permalink, line),
                    price=price,
                    currency=currency or "USD",
                    weight_g=weight,
                    detail_text=clean(f"{classification_context} {text[:1200]}"),
                    explicit_type=classification_context or categories or "meteorite",
                    image_url=image_urls[0] if image_urls else None,
                    image_urls=image_urls,
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
    if "/c/sold/" in path or unavailable_status_text(path):
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


def polandmet_headers(site: dict) -> dict:
    return {
        "User-Agent": BROWSER_UA,
        "Accept": "application/json,text/plain,*/*;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": urljoin(site["base_url"], "/meteorite-shop/"),
    }


def polandmet_price(product: dict) -> tuple[float | None, str | None]:
    prices = product.get("prices") if isinstance(product.get("prices"), dict) else {}
    price = price_num(str(prices.get("price") or ""))
    if price is None:
        return None, None
    try:
        minor_unit = int(prices.get("currency_minor_unit") or 0)
    except (TypeError, ValueError):
        minor_unit = 0
    if minor_unit > 0:
        price = price / (10 ** minor_unit)
    return price, currency_code(str(prices.get("currency_code") or "USD")) or "USD"


def polandmet_image_urls(product: dict, base_url: str) -> list[str]:
    values = []
    for image in product.get("images") or []:
        if not isinstance(image, dict):
            continue
        values.extend([image.get("src"), image.get("thumbnail")])
    return image_url_candidates(base_url, values)


def polandmet_taxonomy_names(product: dict, key: str) -> list[str]:
    return [html_to_text(item.get("name")) for item in product.get(key) or [] if isinstance(item, dict) and html_to_text(item.get("name"))]


def polandmet_available(product: dict) -> bool:
    stock = product.get("stock_availability") if isinstance(product.get("stock_availability"), dict) else {}
    cart = product.get("add_to_cart") if isinstance(product.get("add_to_cart"), dict) else {}
    status_text = clean(
        " ".join(
            str(x or "")
            for x in [
                stock.get("text"),
                stock.get("class"),
                cart.get("text"),
                cart.get("description"),
            ]
        )
    )
    if product.get("is_in_stock") is not True or product.get("is_purchasable") is not True:
        return False
    if product.get("is_on_backorder") is True:
        return False
    if not re.search(r"add\s+to\s+cart", str(cart.get("text") or ""), re.I):
        return False
    return not unavailable_status_text(status_text) and not re.search(r"\b(?:backorder|read\s+more)\b", status_text, re.I)


def polandmet_listing(site: dict, product: dict, log: SourceLog) -> dict | None:
    title = html_to_text(product.get("name"))
    permalink = safe_http_url(site["base_url"], product.get("permalink")) or site["base_url"]
    category_names = polandmet_taxonomy_names(product, "categories")
    tag_names = polandmet_taxonomy_names(product, "tags")
    category_text = clean(", ".join(category_names))
    taxonomy_text = clean(" ".join([category_text, ", ".join(tag_names)]))
    if POLANDMET_NON_SPECIMEN_RE.search(f"{title} {taxonomy_text}") or NON_SPECIMEN_PRODUCT_RE.search(f"{title} {taxonomy_text}"):
        log.reject("polandmet_non_specimen")
        return None
    if not polandmet_available(product):
        log.reject("polandmet_unavailable")
        return None
    description = html_to_text(product.get("description"))
    short_description = html_to_text(product.get("short_description"))
    detail_text = clean(" ".join([taxonomy_text, short_description, description[:1800]]))
    if not (METEORITE_RE.search(f"{title} {detail_text}") or SUBTYPE_RE.search(f"{title} {detail_text}")):
        log.reject("polandmet_missing_meteorite_marker")
        return None
    if WEIGHT_RANGE_RE.search(title) or re.search(r"\b(?:collection|set|lot|specimens)\b", title, re.I):
        log.reject("polandmet_non_individual_title")
        return None
    weight = first_individual_weight_g(title, title_only=True)
    if weight is None or weight <= 0:
        log.reject("polandmet_missing_title_weight")
        return None
    price, currency = polandmet_price(product)
    if price is None or price <= 0:
        log.reject("polandmet_missing_price")
        return None
    images = polandmet_image_urls(product, permalink)
    item = make_listing(
        site,
        permalink,
        title,
        price=price,
        currency=currency or "USD",
        weight_g=weight,
        detail_text=detail_text,
        explicit_type=taxonomy_text or "meteorite",
        image_url=images[0] if images else None,
        image_urls=images,
        item_key=clean(str(product.get("id") or product.get("slug") or title)),
        parser="polandmet",
    )
    if not item:
        log.reject("make_listing_filtered")
        return None
    log.parsed_listing()
    return item


def scrape_polandmet(site: dict, log: SourceLog) -> list[dict]:
    listings = []
    seen_products = set()
    session = requests.Session()
    headers = polandmet_headers(site)
    api_base = urljoin(site["base_url"], "/wp-json/wc/store/v1/products")
    per_page = 100
    max_api_pages = site_int(site, "max_api_pages", 5, 30)
    max_products = site_int(site, "max_products", 350, 2000)
    cap_reached = False
    for page in range(1, max_api_pages + 1):
        if len(listings) >= max_products:
            if not cap_reached:
                log.reject_page("polandmet_product_cap_reached")
                cap_reached = True
            break
        api_url = f"{api_base}?per_page={per_page}&page={page}&stock_status=instock"
        log.index(api_url)
        products = fetch_json(api_url, log, "api", headers=headers, session=session, timeout=45)
        time.sleep(DELAY)
        if products is None:
            log.reject_page("polandmet_api_fetch_failed")
            break
        if not isinstance(products, list):
            log.reject_page("polandmet_api_not_list")
            break
        if not products:
            break
        for product in products:
            if not isinstance(product, dict):
                log.reject("polandmet_bad_product")
                continue
            key = str(product.get("id") or product.get("permalink") or "")
            if not key or key in seen_products:
                continue
            seen_products.add(key)
            item = polandmet_listing(site, product, log)
            if item:
                listings.append(item)
                if len(listings) >= max_products:
                    if not cap_reached:
                        log.reject_page("polandmet_product_cap_reached")
                        cap_reached = True
                    break
        if len(products) < per_page:
            break
    return listings


def kd_headers(site: dict) -> dict:
    return {
        "User-Agent": BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": urljoin(site["base_url"], "/"),
    }


def kd_path(url: str) -> str:
    return unquote(urlparse(url).path.rsplit("/", 1)[-1])


def kd_spaced_title(value: str | None) -> str:
    text = clean(unquote(str(value or "")))
    text = re.sub(r"\.html?$", "", text, flags=re.I)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([A-Za-z])([0-9])", r"\1 \2", text)
    text = re.sub(r"([0-9])([A-Za-z])", r"\1 \2", text)
    text = re.sub(r"\bK\s+D\b", "KD", text)
    return clean(text)


def kd_display_name(value: str | None) -> str | None:
    text = kd_spaced_title(value)
    if not text or KD_BAD_LABEL_RE.fullmatch(text):
        return None
    text = clean(re.sub(r"\b(?:CD|DH)\b$", "", text, flags=re.I))
    candidate = product_identity_from_title(text)
    if candidate and not KD_BAD_LABEL_RE.fullmatch(candidate):
        return candidate
    candidate = tidy_display_candidate(text)
    if candidate and not KD_BAD_LABEL_RE.fullmatch(candidate) and not DISPLAY_SUFFIX_ONLY_RE.fullmatch(candidate):
        return candidate
    return None


def kd_candidate_url(site: dict, page_url: str, href: str) -> str | None:
    url = urljoin(page_url, href).split("#", 1)[0]
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not same_domain(site["base_url"], url):
        return None
    path = kd_path(url)
    if not re.search(r"\.html?$", path, re.I):
        return None
    if path in KD_HUB_PATHS or KD_NON_SPECIMEN_URL_RE.search(path):
        return None
    return url


def kd_detail_urls(site: dict, log: SourceLog) -> list[str]:
    urls = {}
    headers = kd_headers(site)
    max_details = site_int(site, "max_detail_pages", 120, MAX_DETAIL_PAGES_PER_SITE)
    for inventory_url in site.get("inventory_urls", []):
        hub_url = urljoin(site["base_url"], inventory_url)
        log.index(hub_url)
        html = fetch(hub_url, log, "index", headers=headers)
        time.sleep(DELAY)
        if not html:
            log.reject_page("kd_hub_fetch_failed")
            continue
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            url = kd_candidate_url(site, hub_url, a.get("href") or "")
            if url:
                urls[url] = None
                log.detail(url)
                if len(urls) >= max_details:
                    break
        if len(urls) >= max_details:
            break
    return list(urls.keys())[:max_details]


def kd_page_heading(soup: BeautifulSoup, url: str) -> str:
    for value in [kd_path(url), title_for(soup)]:
        name = kd_display_name(value)
        if name:
            return name
    return kd_spaced_title(kd_path(url))


def kd_classification_context(page_text: str, source_url: str) -> str:
    snippets = []
    for pattern in [
        r"Meteorite\s+Type\s*:\s*([^\n]+)",
        r"Structural\s+Class\s*:?ification\s*:\s*([^\n]+)",
        r"Classification\s*:\s*([^\n]+)",
        r"Class\s*:\s*([^\n]+)",
    ]:
        match = re.search(pattern, page_text, re.I)
        if match:
            snippets.append(clean(match.group(1)))
    path = kd_path(source_url)
    if re.search(r"Pallasite", path, re.I):
        snippets.append("pallasite")
    elif re.search(r"Iron|Agoudal|Campo|Mundrabilla|Odessa|Sikhote|Whitecourt|Huoyanshan|Glorieta", path, re.I):
        snippets.append("iron meteorite")
    elif re.search(r"Chondrite|AbaPanu|Bondoc|Franconia|GoldBasin|NWA|Tsarev|Wiluna|Winner", path, re.I):
        snippets.append("chondrite")
    return clean(", ".join(dict.fromkeys(snippets))) or "meteorite"


def kd_cell_images(cell, page_url: str) -> list[str]:
    return image_url_candidates(page_url, [img.get("src") for img in cell.find_all("img")])


def kd_cell_label(cell) -> str:
    bits = []
    for node in cell.find_all(["img", "a"]):
        for attr in ["alt", "title"]:
            value = clean(str(node.get(attr) or ""))
            if value and not KD_BAD_LABEL_RE.fullmatch(value):
                bits.append(value)
        if node.name == "a":
            text = clean(node.get_text(" ", strip=True))
            if text and not KD_BAD_LABEL_RE.fullmatch(text):
                bits.append(text)
    return clean(" ".join(bits))


def kd_exact_values(text: str, log: SourceLog) -> tuple[float, str | None, float] | None:
    prices = prices_in(text)
    if len(prices) != 1:
        log.reject("kd_missing_or_multiple_price")
        return None
    price_pos, price, currency = prices[0]
    if WEIGHT_RANGE_RE.search(text[:price_pos]):
        log.reject("kd_weight_range")
        return None
    weights = list(WEIGHT_RE.finditer(text[:price_pos]))
    if not weights:
        log.reject("kd_missing_weight")
        return None
    weight_match = weights[-1]
    weight_value = num(weight_match.group(1))
    if weight_value is None:
        log.reject("kd_missing_weight")
        return None
    weight = weight_to_g(weight_value, weight_match.group(2))
    if price <= 0 or weight <= 0:
        log.reject("kd_nonpositive_price_weight")
        return None
    return price, currency, weight


def kd_item_title(page_heading: str, label: str, text: str) -> str:
    for value in [page_heading, label]:
        candidate = kd_display_name(value)
        if candidate:
            return candidate
    before_price = PRICE_RE.split(text, maxsplit=1)[0]
    before_price = WEIGHT_RE.sub(" ", before_price)
    before_price = DIMENSION_RE.sub(" ", before_price)
    descriptor = clean(before_price.strip(" -,:;"))
    for value in [descriptor, f"{page_heading} {descriptor}"]:
        candidate = kd_display_name(value)
        if candidate:
            return candidate
    return page_heading


def kd_sale_scopes(soup: BeautifulSoup) -> list:
    scopes = []
    for table in soup.find_all("table"):
        if not PRICE_RE.search(clean(table.get_text(" ", strip=True))):
            continue
        if any(PRICE_RE.search(clean(nested.get_text(" ", strip=True))) for nested in table.find_all("table")):
            continue
        scopes.append(table)
    return scopes or [soup]


def kd_item_url(cell, page_url: str) -> str:
    for a in cell.find_all("a", href=True):
        href = urljoin(page_url, a.get("href") or "").split("#", 1)[0]
        if re.search(r"\.html?$", urlparse(href).path, re.I) and not KD_NON_SPECIMEN_URL_RE.search(kd_path(href)):
            return href
    return page_url


def kd_page_listings(site: dict, url: str, html: str, log: SourceLog) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    for bad in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        bad.decompose()
    lines = lines_from(soup)
    page_text = "\n".join(lines)
    if KD_NON_SPECIMEN_URL_RE.search(kd_path(url)):
        log.reject_page("kd_non_specimen_url")
        return []
    page_heading = kd_page_heading(soup, url)
    classification_context = kd_classification_context(page_text, url)
    listings = []
    seen_keys = set()
    previous_images_by_col: dict[int, list[str]] = {}
    previous_labels_by_col: dict[int, str] = {}
    tables = kd_sale_scopes(soup)
    for table in tables:
        rows = table.find_all("tr") if table.name == "table" else []
        if not rows:
            rows = [table]
        for row_index, row in enumerate(rows):
            cells = row.find_all(["td", "th"], recursive=False) or [row]
            for col_index, cell in enumerate(cells):
                images = kd_cell_images(cell, url)
                label = kd_cell_label(cell)
                if images:
                    previous_images_by_col[col_index] = images
                if label:
                    previous_labels_by_col[col_index] = label
                text = clean(cell.get_text(" ", strip=True))
                if not text or not PRICE_RE.search(text):
                    continue
                combined_text = clean(" ".join([label, text]))
                if unavailable_status_text(combined_text):
                    log.reject("kd_sold_row")
                    continue
                if KD_NON_SPECIMEN_TEXT_RE.search(combined_text) or NON_SPECIMEN_PRODUCT_RE.search(combined_text):
                    log.reject("kd_non_specimen_row")
                    continue
                values = kd_exact_values(combined_text, log)
                if not values:
                    continue
                price, currency, weight = values
                item_url = kd_item_url(cell, url)
                item_images = images or previous_images_by_col.get(col_index)
                if not item_images:
                    log.reject("kd_missing_image")
                    continue
                item_label = label or previous_labels_by_col.get(col_index, "")
                title = kd_item_title(page_heading, item_label, combined_text)
                key = (item_url, price, weight)
                if key in seen_keys:
                    log.reject("kd_duplicate_row")
                    continue
                seen_keys.add(key)
                item = make_listing(
                    site,
                    item_url,
                    title,
                    price=price,
                    currency=currency or "USD",
                    weight_g=weight,
                    detail_text=clean(f"{classification_context} {page_text[:1400]}"),
                    explicit_type=classification_context,
                    image_url=item_images[0],
                    image_urls=item_images,
                    item_key=f"{kd_path(item_url)}:{row_index}:{col_index}:{weight}:{price}",
                    parser="kd_meteorites",
                )
                if item:
                    listings.append(item)
                else:
                    log.reject("make_listing_filtered")
    return listings


def scrape_kd_meteorites(site: dict, log: SourceLog) -> list[dict]:
    listings = []
    seen_ids = set()
    headers = kd_headers(site)
    for url in kd_detail_urls(site, log):
        html = fetch(url, log, "detail", headers=headers)
        time.sleep(DELAY)
        if not html:
            log.reject_page("kd_detail_fetch_failed")
            continue
        for item in kd_page_listings(site, url, html, log):
            if item["id"] in seen_ids:
                log.reject("kd_duplicate_item")
                continue
            seen_ids.add(item["id"])
            listings.append(item)
            log.parsed_listing()
    return listings


def wwmeteorites_slug(url: str) -> str:
    return unquote(urlparse(url).path.strip("/")).strip()


def wwmeteorites_candidate_url(site: dict, page_url: str, href: str) -> str | None:
    url = urljoin(page_url, href).split("#", 1)[0]
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not same_domain(site["base_url"], url):
        return None
    if parsed.query:
        return None
    slug = wwmeteorites_slug(url)
    if "/" in slug or WWMETEORITES_BAD_PATH_RE.fullmatch(slug):
        return None
    return urlunparse((parsed.scheme, parsed.netloc, f"/{slug}", "", "", ""))


def wwmeteorites_detail_urls(site: dict, log: SourceLog) -> list[str]:
    urls: dict[str, None] = {}
    max_details = site_int(site, "max_detail_pages", 100, 120)
    for inventory_url in site.get("inventory_urls", []):
        index_url = urljoin(site["base_url"], inventory_url)
        log.index(index_url)
        html = fetch(index_url, log, "index")
        time.sleep(DELAY)
        if not html:
            log.reject_page("wwmeteorites_index_fetch_failed")
            continue
        soup = BeautifulSoup(html, "lxml")
        candidates = []
        for a in soup.find_all("a", href=True):
            candidates.append(a.get("href") or "")
        candidates.extend(f"/{m.group(1)}" for m in re.finditer(r'"pageUriSEO"\s*:\s*"([^"\\]+)"', html))
        for href in candidates:
            detail_url = wwmeteorites_candidate_url(site, index_url, href)
            if not detail_url or detail_url in urls:
                continue
            urls[detail_url] = None
            log.detail(detail_url)
            if len(urls) >= max_details:
                log.reject_page("wwmeteorites_detail_cap_reached")
                return list(urls.keys())
    return list(urls.keys())


def wwmeteorites_prices_in(text: str) -> list[tuple[int, int, float, str]]:
    prices = []
    for match in WWMETEORITES_PRICE_RE.finditer(text):
        symbol = match.group("symbol_before") or match.group("symbol_after") or "$"
        amount = match.group("amount_before") or match.group("amount_after")
        value = price_num(amount)
        if value is None:
            continue
        currency = "EUR" if symbol.upper() == "EUR" or symbol == "€" else "USD"
        prices.append((match.start(), match.end(), value, currency))
    return prices


def wwmeteorites_row_values(line: str) -> tuple[float, str, float, int] | None:
    prices = wwmeteorites_prices_in(line)
    if len(prices) != 1:
        return None
    price_start, _, price, currency = prices[0]
    before_price = line[:price_start]
    if WEIGHT_RANGE_RE.search(before_price):
        return None
    weights = list(WEIGHT_RE.finditer(before_price))
    if len(weights) != 1:
        return None
    weight_match = weights[0]
    weight_value = num(weight_match.group(1))
    if weight_value is None:
        return None
    weight = weight_to_g(weight_value, weight_match.group(2))
    if price <= 0 or weight <= 0:
        return None
    return price, currency, weight, price_start


def wwmeteorites_exact_row_values(line: str, log: SourceLog) -> tuple[float, str, float, int] | None:
    if unavailable_status_text(line):
        log.reject("wwmeteorites_sold_row")
        return None
    if EMAIL_PRICE_RE.search(line) or WWMETEORITES_AMBIGUOUS_ROW_RE.search(line):
        log.reject("wwmeteorites_ambiguous_row")
        return None
    values = wwmeteorites_row_values(line)
    if values is None:
        if len(wwmeteorites_prices_in(line)) != 1:
            log.reject("wwmeteorites_missing_or_multiple_price")
        elif WEIGHT_RANGE_RE.search(line):
            log.reject("wwmeteorites_weight_range")
        else:
            log.reject("wwmeteorites_missing_or_multiple_weight")
        return None
    price, currency, weight, price_start = values
    return price, currency, weight, price_start


def wwmeteorites_row_descriptor(line: str, price_start: int) -> str:
    descriptor = line[:price_start]
    descriptor = WEIGHT_RE.sub(" ", descriptor)
    descriptor = DIMENSION_RE.sub(" ", descriptor)
    descriptor = re.sub(r"\s*(?:-|\u2013|\u2014|:|;|,)+\s*", " ", descriptor)
    return clean(descriptor)


def wwmeteorites_row_signature(line: str) -> tuple[str, float, float, str] | None:
    values = wwmeteorites_row_values(line)
    if values is None:
        return None
    price, currency, weight, price_start = values
    descriptor = wwmeteorites_row_descriptor(line, price_start).lower()
    return descriptor, round(weight, 4), round(price, 2), currency


def wwmeteorites_spaced_name(value: str | None) -> str:
    text = clean(re.sub(r"[-_]+", " ", unquote(str(value or ""))))
    text = re.sub(r"\s*\|\s*WWMeteorites.*$", "", text, flags=re.I)

    def repl(match: re.Match) -> str:
        prefix = match.group(1).lower()
        label = {"nwa": "NWA", "nea": "NEA", "sau": "SaU", "ras": "RaS"}.get(prefix, match.group(1))
        return f"{label} {match.group(2)}"

    text = re.sub(r"\b(NWA|NEA|SaU|RaS)\s*(\d{2,6}[A-Za-z]?)\b", repl, text, flags=re.I)
    return clean(text)


def wwmeteorites_title_identity(soup: BeautifulSoup, url: str) -> str | None:
    title_node = soup.find("title")
    title_text = title_node.get_text(" ", strip=True) if title_node else ""
    for value in [title_text, wwmeteorites_slug(url)]:
        candidate = wwmeteorites_spaced_name(value)
        if not candidate or candidate.lower() in {"home", "for sale", "wwmeteorites specimen"}:
            continue
        identity = product_identity_from_title(candidate)
        if identity:
            return identity
        if re.search(r"\b(?:SaU|RaS|NEA)\s*\d{2,6}[A-Za-z]?\b", candidate, re.I):
            return display_case_name(candidate)
    return None


def wwmeteorites_page_identity(lines: list[str], soup: BeautifulSoup, url: str) -> tuple[str, str | None]:
    label_re = re.compile(r"^(?:weathering\s+grade|type\s+spec\s+mass|main\s+mass|classification\s+status|tkw)\b", re.I)
    title_identity = wwmeteorites_title_identity(soup, url)
    for line in lines:
        if ":" not in line or label_re.search(line):
            continue
        before, after = line.split(":", 1)
        before = clean(before.strip(" -"))
        after = clean(after.strip(" -"))
        if not before or not after:
            continue
        if re.search(r"\bmeteorite\s+impact\s+glass\b", before, re.I):
            return after, before
        if wwmeteorites_has_meteorite_context(f"{before} {after}"):
            if title_identity and normalize_name_key(title_identity) != normalize_name_key(before):
                return title_identity, labeled_value(lines, "Class") or after
            return before, after
    fallback = clean(re.sub(r"\s*\|\s*WWMeteorites.*$", "", title_for(soup), flags=re.I))
    return title_identity or fallback or "WWMeteorites specimen", labeled_value(lines, "Class")


def wwmeteorites_has_meteorite_context(text: str) -> bool:
    return bool(
        METEORITE_RE.search(text)
        or SUBTYPE_RE.search(text)
        or CATALOG_NAME_RE.search(text)
        or NUMBERED_OFFICIAL_NAME_RE.search(text)
        or KNOWN_DISPLAY_NAME_RE.search(text)
        or re.search(r"\b(?:impact\s+glass|pica\s+glass)\b", text, re.I)
    )


def wwmeteorites_image_urls(soup: BeautifulSoup, page_url: str) -> list[str]:
    values = []
    values.extend(meta.get("content") for meta in soup.find_all("meta", property="og:image"))
    for img in soup.find_all("img"):
        src = img.get("src")
        alt = clean(str(img.get("alt") or ""))
        if WWMETEORITES_BAD_IMAGE_RE.search(f"{src or ''} {alt}"):
            continue
        values.append(src)
    return [url for url in image_url_candidates(page_url, values) if not WWMETEORITES_BAD_IMAGE_RE.search(url)]


def wwmeteorites_page_listings(site: dict, url: str, html: str, log: SourceLog) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    for bad in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        bad.decompose()
    lines = lines_from(soup)
    page_text = "\n".join(lines)
    page_name, explicit_type = wwmeteorites_page_identity(lines, soup, url)
    context = clean(f"{page_name} {explicit_type or ''} {page_text[:1600]}")
    if WWMETEORITES_NON_SPECIMEN_RE.search(f"{wwmeteorites_slug(url)} {context}"):
        log.reject_page("wwmeteorites_non_specimen_page")
        return []
    if not wwmeteorites_has_meteorite_context(context):
        log.reject_page("wwmeteorites_no_meteorite_context")
        return []
    images = wwmeteorites_image_urls(soup, url)
    listings = []
    unavailable_signatures = {signature for line in lines if unavailable_status_text(line) for signature in [wwmeteorites_row_signature(line)] if signature}
    seen_keys = set()
    for line_index, line in enumerate(lines):
        if not WWMETEORITES_PRICE_RE.search(line) and "$" not in line and "€" not in line:
            continue
        values = wwmeteorites_exact_row_values(line, log)
        if not values:
            continue
        price, currency, weight, price_start = values
        descriptor = wwmeteorites_row_descriptor(line, price_start)
        row_context = clean(f"{page_name} {explicit_type or ''} {descriptor} {line}")
        if WWMETEORITES_NON_SPECIMEN_RE.search(row_context) or NON_SPECIMEN_PRODUCT_RE.search(row_context):
            log.reject("wwmeteorites_non_specimen_row")
            continue
        title = page_name if not descriptor else f"{page_name} - {descriptor}"
        signature = (descriptor.lower(), round(weight, 4), round(price, 2), currency)
        if signature in unavailable_signatures:
            log.reject("wwmeteorites_unavailable_duplicate_row")
            continue
        key = (url, signature)
        if key in seen_keys:
            log.reject("wwmeteorites_duplicate_row")
            continue
        seen_keys.add(key)
        item = make_listing(
            site,
            url,
            title,
            price=price,
            currency=currency,
            weight_g=weight,
            detail_text=context,
            explicit_type=explicit_type or page_name,
            image_url=images[0] if images else None,
            image_urls=images,
            item_key=f"{wwmeteorites_slug(url)}:{descriptor}:{weight}:{price}",
            parser="wwmeteorites",
        )
        if item:
            listings.append(item)
        else:
            log.reject("make_listing_filtered")
    return listings


def scrape_wwmeteorites(site: dict, log: SourceLog) -> list[dict]:
    listings = []
    seen_ids = set()
    for url in wwmeteorites_detail_urls(site, log):
        html = fetch(url, log, "detail")
        time.sleep(DELAY)
        if not html:
            log.reject_page("wwmeteorites_detail_fetch_failed")
            continue
        for item in wwmeteorites_page_listings(site, url, html, log):
            if item["id"] in seen_ids:
                log.reject("wwmeteorites_duplicate_item")
                continue
            seen_ids.add(item["id"])
            listings.append(item)
            log.parsed_listing()
    return listings


METEORITE_RECON_PRICE_RE = re.compile(r"(?<![A-Za-z])(USD|EUR|US\$|\$|€)\s*([0-9][0-9.,]*)", re.I)
METEORITE_RECON_OFFER_PRICE_RE = re.compile(r"\b(?:make|maker|offer|request|contact|inquire|please)\b", re.I)
METEORITE_RECON_SPECIMEN_WEIGHT_RE = re.compile(
    r"\b(?:individual|fragment|end\s*cut|endcut|half\s+(?:slice|individual|slab)|slice|slab|specimen)\b",
    re.I,
)
METEORITE_RECON_SKIP_TITLE_RE = re.compile(r"^(?:meteorites?\s+for\s+sale|stones?|irons?|books?)$", re.I)


def meteorite_recon_headers(site: dict) -> dict:
    return {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": urljoin(site["base_url"], "/"),
    }


def meteorite_recon_parse_price_amount(raw: str) -> float | None:
    value = clean(raw).replace(" ", "").replace("\xa0", "").strip(".,")
    if not value:
        return None
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        parts = value.split(",")
        if len(parts[-1]) == 3 and all(part.isdigit() for part in parts):
            value = "".join(parts)
        else:
            value = value.replace(",", ".")
    elif "." in value:
        parts = value.split(".")
        if len(parts[-1]) == 3 and all(part.isdigit() for part in parts):
            value = "".join(parts)
    try:
        return float(value)
    except ValueError:
        return None


def meteorite_recon_exact_price(lines: list[str], log: SourceLog) -> tuple[float, str] | None:
    price_label_indexes = [idx for idx, line in enumerate(lines) if re.fullmatch(r"Price\s*/\s*Trade\s+value", line, re.I)]
    if not price_label_indexes:
        log.reject("meteorite_recon_missing_price_label")
        return None
    price_lines = lines[price_label_indexes[-1] + 1:price_label_indexes[-1] + 4]
    for line in price_lines:
        matches = list(METEORITE_RECON_PRICE_RE.finditer(line))
        if len(matches) > 1:
            log.reject("meteorite_recon_multiple_prices")
            return None
        if not matches:
            if METEORITE_RECON_OFFER_PRICE_RE.search(line):
                log.reject("meteorite_recon_offer_price")
                return None
            continue
        match = matches[0]
        price = meteorite_recon_parse_price_amount(match.group(2))
        currency = currency_code(match.group(1)) or "USD"
        if price is None or price <= 0:
            log.reject("meteorite_recon_nonpositive_price")
            return None
        return price, currency
    log.reject("meteorite_recon_missing_exact_price")
    return None


def meteorite_recon_specimen_weight(lines: list[str], log: SourceLog) -> float | None:
    for line in lines:
        if not METEORITE_RECON_SPECIMEN_WEIGHT_RE.search(line) or NON_INDIVIDUAL_WEIGHT_CONTEXT_RE.search(line):
            continue
        weight = first_weight_g(line)
        if weight is not None and weight > 0:
            return weight
    weight = first_individual_weight_g("", "\n".join(lines))
    if weight is None or weight <= 0:
        log.reject("meteorite_recon_missing_specimen_weight")
        return None
    return weight


def meteorite_recon_image_urls(row, page_url: str) -> list[str]:
    values = []
    for a in row.find_all("a", href=True):
        href = a.get("href")
        if href and re.search(r"\.(?:jpe?g|png|webp)(?:[?#].*)?$", href, re.I):
            values.append(href)
    for img in row.find_all("img"):
        values.extend(img.get(attr) for attr in ["data-src", "data-lazy-src", "src"])
    return image_url_candidates(page_url, values)


def meteorite_recon_lines(row) -> list[str]:
    return [clean(line) for line in row.get_text("\n", strip=True).splitlines() if clean(line)]


def meteorite_recon_listing(site: dict, page_url: str, row, title: str, row_index: int, log: SourceLog) -> dict | None:
    lines = meteorite_recon_lines(row)
    detail_text = clean(" ".join(lines))
    if unavailable_status_text(detail_text):
        log.reject("meteorite_recon_sold_row")
        return None
    if NON_SPECIMEN_PRODUCT_RE.search(title):
        log.reject("meteorite_recon_non_specimen_title")
        return None
    price_values = meteorite_recon_exact_price(lines, log)
    if not price_values:
        return None
    price, currency = price_values
    weight = meteorite_recon_specimen_weight(lines, log)
    if weight is None:
        return None
    images = meteorite_recon_image_urls(row, page_url)
    if not images:
        log.reject("meteorite_recon_missing_image")
        return None
    explicit_type = clean(
        " ".join(
            line
            for line in lines[1:6]
            if re.search(r"\b(?:stone|iron|chondrite|achondrite|octahedrite|pallasite|diogenite|eucrite|IAB|IIIAB|HED|H5|L4)\b", line, re.I)
        )
    )
    item = make_listing(
        site,
        page_url,
        title,
        price=price,
        currency=currency,
        weight_g=weight,
        detail_text=detail_text[:2200],
        explicit_type=explicit_type or "meteorite",
        image_url=images[0],
        image_urls=images,
        item_key=f"{row_index}:{title}:{weight}:{price}",
        parser="meteorite_recon",
    )
    if not item:
        log.reject("make_listing_filtered")
        return None
    log.parsed_listing()
    log.detail(page_url)
    return item


def scrape_meteorite_recon(site: dict, log: SourceLog) -> list[dict]:
    listings = []
    seen_keys = set()
    headers = meteorite_recon_headers(site)
    for url in site.get("inventory_urls", []):
        page_url = urljoin(site["base_url"], url)
        log.index(page_url)
        html = fetch(page_url, log, "index", headers=headers)
        time.sleep(DELAY)
        if not html:
            log.reject_page("meteorite_recon_page_fetch_failed")
            continue
        soup = BeautifulSoup(html, "lxml")
        root = soup.select_one(".wpb-content-wrapper") or soup.select_one(".full_width_inner") or soup
        page_items = []
        for row_index, heading in enumerate(root.find_all("h3")):
            title = clean(heading.get_text(" ", strip=True))
            if not title or METEORITE_RECON_SKIP_TITLE_RE.fullmatch(title):
                continue
            row = heading.find_parent(class_=lambda classes: classes and "vc_row" in classes.split())
            if row is None:
                log.reject("meteorite_recon_missing_row_scope")
                continue
            item = meteorite_recon_listing(site, page_url, row, title, row_index, log)
            if not item:
                continue
            key = (item.get("url"), item.get("title"), item.get("weight_g"), item.get("price"))
            if key in seen_keys:
                log.reject("meteorite_recon_duplicate_row")
                continue
            seen_keys.add(key)
            page_items.append(item)
        if not page_items:
            log.reject_page("meteorite_recon_no_exact_rows")
        listings.extend(page_items)
    return listings


def ebay_credentials() -> tuple[str | None, str | None]:
    return clean(os.environ.get("EBAY_CLIENT_ID")), clean(os.environ.get("EBAY_CLIENT_SECRET"))


def ebay_access_token(log: SourceLog) -> str | None:
    client_id, client_secret = ebay_credentials()
    if not client_id or not client_secret:
        log.reject_page("ebay_credentials_missing")
        return None
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    token_url = "https://api.ebay.com/identity/v1/oauth2/token"
    try:
        response = polite_request(
            "POST",
            token_url,
            log=log,
            kind="ebay_oauth",
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": UA,
            },
            data={
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            },
            timeout=30,
        )
        if response is None:
            return None
        if response.status_code >= 400:
            log.failed(token_url, f"oauth HTTP {response.status_code}")
            return None
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        log.failed(token_url, f"oauth failed: {exc}")
        return None
    token = clean(str(data.get("access_token") or "")) if isinstance(data, dict) else ""
    if not token:
        log.reject_page("ebay_token_missing")
        return None
    return token


def ebay_search_url(query: str, seller: str, marketplace_id: str, limit: int, offset: int) -> str:
    params = {
        "q": query,
        "fieldgroups": "EXTENDED",
        "limit": str(limit),
        "offset": str(offset),
        "filter": f"buyingOptions:{{FIXED_PRICE}},sellers:{{{seller}}}",
        "sort": "newlyListed",
    }
    return f"https://api.ebay.com/buy/browse/v1/item_summary/search?{urlencode(params)}"


def ebay_item_listing(site: dict, item: dict, seller: str, log: SourceLog) -> dict | None:
    title = clean(str(item.get("title") or ""))
    buying_options = [str(option or "").upper() for option in item.get("buyingOptions") or []]
    seller_data = item.get("seller") if isinstance(item.get("seller"), dict) else {}
    seller_name = clean(str(seller_data.get("username") or ""))
    if seller_name.lower() != seller.lower():
        log.reject("ebay_wrong_seller")
        return None
    if "FIXED_PRICE" not in buying_options or "AUCTION" in buying_options or "CLASSIFIED_AD" in buying_options:
        log.reject("ebay_non_fixed_price")
        return None
    price_data = item.get("price") if isinstance(item.get("price"), dict) else {}
    currency = currency_code(str(price_data.get("currency") or ""))
    price = price_num(str(price_data.get("value") or ""))
    if currency != "USD" or price is None or price <= 0:
        log.reject("ebay_missing_usd_price")
        return None
    short_description = clean(str(item.get("shortDescription") or ""))
    category_names = " ".join(clean(str(cat.get("categoryName") or "")) for cat in item.get("categories") or [] if isinstance(cat, dict))
    detail_text = clean(" ".join([title, short_description, category_names, seller_name]))
    if not METEORITE_RE.search(detail_text):
        log.reject("ebay_missing_meteorite_marker")
        return None
    if NON_SPECIMEN_PRODUCT_RE.search(detail_text) or re.search(r"\b(?:choose|lot|set|bulk|wholesale|assorted|random|replica|fake)\b", detail_text, re.I):
        log.reject("ebay_non_specimen")
        return None
    weight = first_individual_weight_g(title, short_description)
    if weight is None or weight <= 0:
        log.reject("ebay_missing_weight")
        return None
    url = safe_http_url(site["base_url"], item.get("itemWebUrl") or item.get("itemAffiliateWebUrl"))
    if not url:
        log.reject("ebay_missing_url")
        return None
    image_data = item.get("image") if isinstance(item.get("image"), dict) else {}
    image_urls = image_url_candidates(url, [image_data.get("imageUrl")])
    listing = make_listing(
        site,
        url,
        title,
        price=price,
        currency=currency,
        weight_g=weight,
        detail_text=detail_text,
        explicit_type="meteorite",
        image_url=image_urls[0] if image_urls else None,
        image_urls=image_urls,
        item_key=clean(str(item.get("itemId") or item.get("legacyItemId") or title)),
        parser="ebay_browse",
    )
    if not listing:
        log.reject("make_listing_filtered")
        return None
    listing["seller"] = seller_name
    listing["buying_options"] = buying_options
    if item.get("itemEndDate"):
        listing["item_end_date"] = item.get("itemEndDate")
    log.parsed_listing()
    return listing


def scrape_ebay_browse(site: dict, log: SourceLog) -> list[dict]:
    seller = clean(str(site.get("ebay_seller_username") or ""))
    if not seller:
        log.reject_page("ebay_seller_missing")
        return []
    token = ebay_access_token(log)
    if not token:
        return []
    marketplace_id = clean(str(site.get("marketplace_id") or "EBAY_US")) or "EBAY_US"
    queries = [clean(str(query)) for query in site.get("search_queries") or ["meteorite"] if clean(str(query))]
    try:
        limit = min(max(int(site.get("limit") or 100), 1), 200)
    except (TypeError, ValueError):
        limit = 100
    try:
        max_pages = min(max(int(site.get("max_pages") or 2), 1), 20)
    except (TypeError, ValueError):
        max_pages = 2
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": UA,
        "X-EBAY-C-MARKETPLACE-ID": marketplace_id,
        "Accept-Language": "en-US",
    }
    listings = []
    seen_items = set()
    session = requests.Session()
    for query in queries:
        for page in range(max_pages):
            api_url = ebay_search_url(query, seller, marketplace_id, limit, page * limit)
            log.index(api_url)
            data = fetch_json(api_url, log, "api", headers=headers, session=session, timeout=45)
            time.sleep(DELAY)
            if not isinstance(data, dict):
                log.reject_page("ebay_api_fetch_failed")
                break
            summaries = data.get("itemSummaries") if isinstance(data.get("itemSummaries"), list) else []
            if not summaries:
                break
            for item in summaries:
                item_id = clean(str(item.get("itemId") or item.get("legacyItemId") or ""))
                if not item_id or item_id in seen_items:
                    continue
                seen_items.add(item_id)
                listing = ebay_item_listing(site, item, seller, log)
                if listing:
                    listings.append(listing)
            if len(summaries) < limit:
                break
    return listings


def scrape_collector_secret(site: dict, log: SourceLog) -> list[dict]:
    log.reject_page("ebay_affiliate_aggregator_not_scraped")
    return []


def scrape_the_space_shop(site: dict, log: SourceLog) -> list[dict]:
    log.reject_page("generic_souvenir_lot_source_not_scraped")
    return []


def scrape_disabled_backlog(site: dict, log: SourceLog) -> list[dict]:
    log.reject_page("disabled_backlog_not_scraped")
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
    if parser == "astro_west":
        return scrape_astro_west(site, log)
    if parser == "prehistoric_fossils":
        return scrape_prehistoric_fossils(site, log)
    if parser == "meteolovers":
        return scrape_meteolovers(site, log)
    if parser == "galactic_stone":
        return scrape_galactic_stone(site, log)
    if parser == "galactic_stone_ecrater":
        return scrape_galactic_stone_ecrater(site, log)
    if parser == "fossil_realm":
        return scrape_fossil_realm(site, log)
    if parser == "top_meteorite":
        return scrape_top_meteorite(site, log)
    if parser == "buy_meteorite":
        return scrape_buy_meteorite(site, log)
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
    if parser == "polandmet":
        return scrape_polandmet(site, log)
    if parser == "kd_meteorites":
        return scrape_kd_meteorites(site, log)
    if parser == "wwmeteorites":
        return scrape_wwmeteorites(site, log)
    if parser == "collecting_meteorites":
        return scrape_collecting_meteorites(site, log)
    if parser == "meteor_center":
        return scrape_meteor_center(site, log)
    if parser == "meteorite_recon":
        return scrape_meteorite_recon(site, log)
    if parser == "ebay_browse":
        return scrape_ebay_browse(site, log)
    if parser == "collector_secret":
        return scrape_collector_secret(site, log)
    if parser == "the_space_shop":
        return scrape_the_space_shop(site, log)
    if parser == "disabled_backlog":
        return scrape_disabled_backlog(site, log)
    if parser == "generic":
        return scrape_generic(site, log)
    log.reject_page("unknown_parser_not_scraped")
    return []


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
    parser.add_argument(
        "--normalize-existing",
        action="store_true",
        help="Normalize the existing listings file and refresh USD conversion metadata without scraping sources.",
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
            x.get("price_per_g_usd") if x.get("price_per_g_usd") is not None else 10**9,
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


def apply_usd_conversion(item: dict, fx_metadata: dict) -> None:
    rates_to_usd = fx_metadata.get("rates_to_usd") if isinstance(fx_metadata, dict) else {}
    if not isinstance(rates_to_usd, dict):
        rates_to_usd = {}
    price = numeric_value(item.get("price"))
    weight = numeric_value(item.get("weight_g"))
    currency = currency_code(item.get("currency"))
    if currency:
        item["currency"] = currency

    rate = numeric_value(rates_to_usd.get(currency)) if price is not None and currency else None
    if price is not None and rate and rate > 0:
        price_usd = round(price * rate, 2)
        item["price_usd"] = price_usd
        item["fx_rate_to_usd"] = round_rate(rate)
        item["fx_rate_date"] = clean(str(fx_metadata.get("date") or "")) or None
        item["price_per_g_usd"] = round(price_usd / weight, 4) if weight and weight > 0 else None
    else:
        item["price_usd"] = None
        item["price_per_g_usd"] = None
        item["fx_rate_to_usd"] = None
        item["fx_rate_date"] = None


def normalize_listing_item(item: dict, fx_metadata: dict) -> dict:
    normalized = dict(item)
    parser = str(normalized.get("parser") or "generic")
    title = display_title(str(normalized.get("title") or ""), parser, str(normalized.get("url") or ""))
    canonical = None
    stale_detail_text_canonical = (
        normalized.get("canonical_name_source") == "detail_text"
        and not re.search(r"\d", clean(str(normalized.get("canonical_name_display") or "")))
    )
    if (
        normalized.get("canonical_name_status") in {"metbull_verified", "parsed_high"}
        and clean(str(normalized.get("canonical_name") or ""))
        and clean(str(normalized.get("canonical_name_display") or ""))
        and clean(str(normalized.get("canonical_name_source") or ""))
        and not stale_detail_text_canonical
    ):
        canonical = {key: normalized.get(key) for key in ["canonical_name", "canonical_name_display", "canonical_name_status", "canonical_name_source"]}
        for key in ["metbull_code", "metbull_status", "metbull_type"]:
            if normalized.get(key):
                canonical[key] = normalized[key]
    if canonical is None:
        canonical = canonical_name_info(
            str(normalized.get("title") or ""),
            title,
            " ".join(str(normalized.get(key) or "") for key in ["classification_text", "subtype", "meteorite_type", "url"]),
            str(normalized.get("url") or ""),
        )
    if canonical.get("canonical_name_display") and canonical.get("canonical_name_status") in {"metbull_verified", "parsed_high"}:
        title = canonical["canonical_name_display"]
    normalized["title"] = title
    normalized["canonical_name"] = canonical.get("canonical_name")
    normalized["canonical_name_display"] = canonical.get("canonical_name_display")
    normalized["canonical_name_status"] = canonical.get("canonical_name_status")
    normalized["canonical_name_source"] = canonical.get("canonical_name_source")
    for key in ["metbull_code", "metbull_status", "metbull_type"]:
        if canonical.get(key):
            normalized[key] = canonical[key]
        else:
            normalized.pop(key, None)
    mtype, subtype, ctext = normalized_classification(
        str(normalized.get("meteorite_type") or "unknown"),
        normalized.get("subtype"),
        normalized.get("classification_text"),
    )
    mtype, subtype, ctext = classification_title_variants(
        normalized["title"],
        str(normalized.get("url") or ""),
        mtype,
        subtype,
        ctext,
    )
    mtype, subtype, ctext = source_specific_classification(
        parser,
        normalized["title"],
        str(normalized.get("url") or ""),
        str(normalized.get("classification_text") or ""),
        mtype,
        subtype,
        ctext,
    )
    mtype, subtype, ctext = apply_metbull_classification(canonical, mtype, subtype, ctext)
    normalized["meteorite_type"] = mtype
    normalized["subtype"] = subtype
    normalized["classification_text"] = ctext
    if mtype == "tektite/impactite":
        normalized.pop("metbull_type", None)
    price = numeric_value(normalized.get("price"))
    weight = numeric_value(normalized.get("weight_g"))
    normalized["price_per_g"] = round(price / weight, 4) if price is not None and weight and weight > 0 else None
    apply_usd_conversion(normalized, fx_metadata)
    return normalized


def normalize_existing_listings(existing_data: dict, enabled_sources: set[str], fx_metadata: dict) -> tuple[list[dict], set[str]]:
    listings = []
    preserved_sources = set()
    for item in existing_data.get("listings", []):
        source = item.get("source")
        if source not in enabled_sources or not item.get("id"):
            continue
        listings.append(normalize_listing_item(item, fx_metadata))
        preserved_sources.add(source)
    return listings, preserved_sources


def merge_listings(
    existing_data: dict,
    refreshed_by_id: dict[str, dict],
    scraped_counts: dict[str, int],
    scraped_sources: set[str],
    enabled_sources: set[str],
    fx_metadata: dict,
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
        merged_by_id[str(item_id)] = normalize_listing_item(item, fx_metadata)

    merged_by_id.update({item_id: normalize_listing_item(item, fx_metadata) for item_id, item in refreshed_by_id.items()})
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
    fx_metadata: dict,
    scrape_mode: str | None = None,
) -> dict:
    scraped_sources = [site["name"] for site in selected_sites]
    mode = scrape_mode or ("rotation" if rotation_info else "selected" if len(selected_sites) != len(enabled_sites) else "full")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_count": len(enabled_sites),
        "listing_count": len(listings),
        "scrape_mode": mode,
        "preserve_existing": preserve_existing,
        "scraped_sources": scraped_sources,
        "preserved_sources": source_ordered_names(preserved_sources, enabled_sites),
        "exchange_rates": fx_metadata,
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
    existing_data = load_existing_data()
    enabled_sources = {site["name"] for site in enabled_sites}

    if args.normalize_existing:
        if args.rotate or requested_site_tokens(args):
            raise SystemExit("--normalize-existing cannot be combined with --rotate, --site, or --sites")
        fx_metadata = resolve_fx_metadata(existing_data)
        listings, preserved_sources = normalize_existing_listings(existing_data, enabled_sources, fx_metadata)
        listings = sort_listings(listings)
        payload = output_payload(
            listings=listings,
            enabled_sites=enabled_sites,
            selected_sites=[],
            preserved_sources=preserved_sources,
            empty_refresh_preserved_sources=set(),
            rotation_info={},
            preserve_existing=True,
            fx_metadata=fx_metadata,
            scrape_mode="normalize",
        )
        OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {OUT} with {len(listings)} listings")
        print("Scraped sources: none")
        if payload["preserved_sources"]:
            print(f"Preserved sources: {', '.join(payload['preserved_sources'])}")
        return

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
    fx_metadata = resolve_fx_metadata(existing_data)
    scraped_sources = {site["name"] for site in selected_sites}

    listings, preserved_sources, empty_refresh_preserved_sources = merge_listings(
        existing_data,
        refreshed_by_id,
        scraped_counts,
        scraped_sources,
        enabled_sources,
        fx_metadata,
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
        fx_metadata=fx_metadata,
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

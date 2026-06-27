#!/usr/bin/env python3
"""Discover candidate meteorite inventory sources for manual review.

This script intentionally does not modify scraper configuration or inventory data.
It searches with official search APIs when credentials are available, probes a
small number of likely direct dealer pages, and writes review-only artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
UA = "MeteoriteMetaSearchBot/0.3 (+https://github.com/rayborg/meteorite-meta-search)"
DEFAULT_QUERIES = [
    "meteorites for sale dealer",
    "meteorite specimens for sale",
    "lunar martian meteorite dealer",
    "NWA meteorite specimens shop",
    "pallasite chondrite meteorites for sale",
]
POLICY_BLOCKED_DOMAINS = {
    "ebay.com",
    "etsy.com",
    "facebook.com",
    "instagram.com",
    "pinterest.com",
    "amazon.com",
    "aliexpress.com",
    "shopgoodwill.com",
    "craigslist.org",
}
POLICY_BLOCKED_BRANDS = {domain.split(".", 1)[0] for domain in POLICY_BLOCKED_DOMAINS}
NON_SOURCE_DOMAINS = {
    "wikipedia.org",
    "wikimedia.org",
    "youtube.com",
    "youtu.be",
    "reddit.com",
    "metbull.org",
    "lpi.usra.edu",
    "nasa.gov",
    "google.com",
    "bing.com",
}
ROBOTS_CACHE: dict[str, RobotFileParser | bool | None] = {}
MAX_HTML_BYTES = 300_000
MAX_REDIRECTS = 5
METEORITE_RE = re.compile(
    r"\b(?:meteorites?|chondrite|achondrite|pallasite|mesosiderite|lunar|martian|tektite|impactite|NWA\s*\d+)\b",
    re.I,
)
PRICE_RE = re.compile(r"(?:US\$|\$|USD|EUR|€|CAD)\s*[0-9][0-9,.]*|[0-9][0-9,.]*\s*(?:USD|EUR|€|CAD)", re.I)
WEIGHT_RE = re.compile(r"\b[0-9][0-9,.]*\s*(?:kg|kilograms?|g|grams?|gm|gms|mg|oz|ounces?)\b", re.I)
SHOP_RE = re.compile(r"\b(?:shop|store|cart|add\s+to\s+cart|product|products|for\s+sale|inventory)\b", re.I)
NON_INVENTORY_RE = re.compile(r"\b(?:article|guide|how\s+to|museum|education|identification|blog|forum|research)\b", re.I)


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalized_domain(value: str | None) -> str:
    parsed = urlparse(value or "")
    host = (parsed.netloc or parsed.path).lower().split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def parent_domain(domain: str) -> str:
    parts = domain.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return domain


def load_known_domains(sites_path: Path, backlog_path: Path | None) -> set[str]:
    known = set()
    with sites_path.open(encoding="utf-8") as handle:
        sites = json.load(handle)
    for site in sites:
        for value in [site.get("base_url"), *(site.get("inventory_urls") or [])]:
            domain = normalized_domain(value)
            if domain:
                known.add(domain)
                known.add(parent_domain(domain))
    if backlog_path and backlog_path.exists():
        text = backlog_path.read_text(encoding="utf-8")
        for match in re.finditer(r"https?://[^\s)\]|>]+", text):
            domain = normalized_domain(match.group(0))
            if domain:
                known.add(domain)
                known.add(parent_domain(domain))
    return known


def is_policy_blocked(domain: str) -> bool:
    root = parent_domain(domain)
    brand = domain.split(".", 1)[0]
    return (
        domain in POLICY_BLOCKED_DOMAINS
        or root in POLICY_BLOCKED_DOMAINS
        or any(domain.endswith(f".{blocked}") for blocked in POLICY_BLOCKED_DOMAINS)
        or brand in POLICY_BLOCKED_BRANDS
    )


def is_non_source_domain(domain: str) -> bool:
    root = parent_domain(domain)
    return domain in NON_SOURCE_DOMAINS or root in NON_SOURCE_DOMAINS or any(domain.endswith(f".{blocked}") for blocked in NON_SOURCE_DOMAINS)


def blocked_domain_reason(domain: str, known_domains: set[str]) -> str | None:
    root = parent_domain(domain)
    if domain in known_domains or root in known_domains:
        return "known_source"
    if is_policy_blocked(domain):
        return "policy_blocked_domain"
    if is_non_source_domain(domain):
        return "non_inventory_reference_domain"
    return None


def search_brave(query: str, count: int, api_key: str) -> list[dict]:
    response = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={"Accept": "application/json", "X-Subscription-Token": api_key, "User-Agent": UA},
        params={"q": query, "count": count, "search_lang": "en"},
        timeout=25,
    )
    response.raise_for_status()
    data = response.json()
    return [
        {"title": item.get("title"), "url": item.get("url"), "snippet": item.get("description")}
        for item in (data.get("web") or {}).get("results") or []
    ]


def search_bing(query: str, count: int, api_key: str) -> list[dict]:
    response = requests.get(
        "https://api.bing.microsoft.com/v7.0/search",
        headers={"Ocp-Apim-Subscription-Key": api_key, "User-Agent": UA},
        params={"q": query, "count": count, "responseFilter": "Webpages"},
        timeout=25,
    )
    response.raise_for_status()
    data = response.json()
    return [
        {"title": item.get("name"), "url": item.get("url"), "snippet": item.get("snippet")}
        for item in (data.get("webPages") or {}).get("value") or []
    ]


def search_results(queries: list[str], max_results: int) -> tuple[str | None, list[dict], list[str]]:
    brave_key = os.environ.get("BRAVE_SEARCH_API_KEY")
    bing_key = os.environ.get("BING_SEARCH_API_KEY")
    provider = "brave" if brave_key else "bing" if bing_key else None
    warnings = []
    if provider is None:
        return None, [], ["No supported search API credential configured; discovery skipped."]
    results = []
    for query in queries:
        try:
            found = search_brave(query, max_results, brave_key) if provider == "brave" else search_bing(query, max_results, bing_key)
        except requests.RequestException as exc:
            warnings.append(f"Search failed for query {query!r}: {exc}")
            continue
        for item in found:
            item["query"] = query
            results.append(item)
        time.sleep(1.0)
    return provider, results, warnings


def safe_url(value: str | None) -> str | None:
    parsed = urlparse(value or "")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value.split("#", 1)[0]


def robots_allows(url: str) -> bool:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    base = f"{parsed.scheme}://{parsed.netloc}"
    if base not in ROBOTS_CACHE:
        robot_parser = RobotFileParser()
        try:
            response = requests.get(f"{base}/robots.txt", headers={"User-Agent": UA}, timeout=10)
            if response.status_code in {404, 410}:
                ROBOTS_CACHE[base] = None
            elif response.status_code >= 400:
                ROBOTS_CACHE[base] = False
            else:
                robot_parser.parse(response.text.splitlines())
                ROBOTS_CACHE[base] = robot_parser
        except requests.RequestException:
            ROBOTS_CACHE[base] = False
    robot_parser = ROBOTS_CACHE[base]
    if robot_parser is False:
        return False
    return True if robot_parser is None else robot_parser.can_fetch(UA, url)


def fetch_page(url: str, known_domains: set[str]) -> tuple[str | None, str | None, str]:
    current_url = url
    for _ in range(MAX_REDIRECTS + 1):
        if not robots_allows(current_url):
            return None, "robots_disallowed", current_url
        try:
            response = requests.get(
                current_url,
                headers={"User-Agent": UA, "Accept": "text/html"},
                timeout=25,
                stream=True,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            return None, f"fetch_failed: {exc}", current_url
        with response:
            final_url = safe_url(response.url) or current_url
            if 300 <= response.status_code < 400 and response.headers.get("location"):
                redirected_url = safe_url(urljoin(final_url, response.headers["location"]))
                if not redirected_url:
                    return None, "invalid_redirect", final_url
                redirected_domain = normalized_domain(redirected_url)
                reason = blocked_domain_reason(redirected_domain, known_domains)
                if reason:
                    return None, f"redirected_to_{reason}", redirected_url
                current_url = redirected_url
                continue
            if response.status_code >= 400:
                return None, f"http_{response.status_code}", final_url
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                return None, f"not_html: {content_type}", final_url
            content = bytearray()
            for chunk in response.iter_content(chunk_size=16_384):
                if not chunk:
                    continue
                content.extend(chunk)
                if len(content) >= MAX_HTML_BYTES:
                    del content[MAX_HTML_BYTES:]
                    break
            return content.decode(response.encoding or "utf-8", errors="replace"), None, final_url
    return None, "too_many_redirects", current_url


def parser_style_guess(html: str, url: str) -> str:
    text = html.lower()
    if "cdn.shopify.com" in text or "/products.json" in text:
        return "shopify"
    if "woocommerce" in text or "add_to_cart_button" in text or "/wp-json/wc/store" in text:
        return "woocommerce"
    if "bigcommerce" in text or "stencil" in text:
        return "bigcommerce"
    if "wixstatic" in text or "wix-code" in text:
        return "wix/static"
    if "/product/" in urlparse(url).path.lower() or re.search(r"/shop|/store|/catalog", url, re.I):
        return "static/shop"
    return "unknown"


def score_candidate(url: str, title: str, snippet: str, html: str | None) -> tuple[int, list[str], list[str], str]:
    evidence = []
    cautions = []
    text = clean(" ".join([title, snippet, BeautifulSoup(html or "", "lxml").get_text(" ", strip=True)[:6000]]))
    score = 0
    if METEORITE_RE.search(text):
        score += 25
        evidence.append("meteorite/classification terms found")
    if PRICE_RE.search(text):
        score += 20
        evidence.append("price-like text found")
    if WEIGHT_RE.search(text):
        score += 20
        evidence.append("weight-like text found")
    if SHOP_RE.search(text):
        score += 15
        evidence.append("shop/product/inventory language found")
    if re.search(r"\b(?:NWA\s*\d+|lunar|martian|pallasite|eucrite|shergottite|carbonaceous)\b", text, re.I):
        score += 10
        evidence.append("specific meteorite class/name evidence found")
    if NON_INVENTORY_RE.search(text):
        score -= 15
        cautions.append("educational/reference wording found; manual review required")
    style = parser_style_guess(html or "", url)
    if style != "unknown":
        score += 10
        evidence.append(f"parser style guess: {style}")
    if not html:
        score -= 20
        cautions.append("page probe failed or was not HTML")
    score = max(0, min(100, score))
    return score, evidence, cautions, style


def discover(args: argparse.Namespace) -> dict:
    sites_path = Path(args.sites)
    backlog_path = Path(args.backlog) if args.backlog else None
    known_domains = load_known_domains(sites_path, backlog_path)
    queries = args.query or DEFAULT_QUERIES
    provider, found, warnings = search_results(queries, args.max_results)
    rejected = []
    candidates_by_domain = {}
    probed_domains = set()

    for item in found:
        url = safe_url(item.get("url"))
        if not url:
            continue
        domain = normalized_domain(url)
        root = parent_domain(domain)
        if not domain:
            continue
        if domain in known_domains or root in known_domains:
            rejected.append({"url": url, "domain": domain, "reason": "already_known_duplicate"})
            continue
        if is_policy_blocked(domain):
            rejected.append({"url": url, "domain": domain, "reason": "policy_blocked_marketplace_or_social"})
            continue
        if is_non_source_domain(domain):
            rejected.append({"url": url, "domain": domain, "reason": "non_inventory_reference_domain"})
            continue
        if domain in candidates_by_domain or domain in probed_domains:
            continue
        if len(candidates_by_domain) >= args.max_candidates:
            break
        probed_domains.add(domain)
        html, fetch_error, final_url = fetch_page(url, known_domains)
        time.sleep(args.probe_delay)
        final_domain = normalized_domain(final_url)
        final_root = parent_domain(final_domain)
        if final_domain != domain:
            if final_domain in known_domains or final_root in known_domains:
                rejected.append({"url": url, "final_url": final_url, "domain": final_domain, "reason": "redirected_to_known_source"})
                continue
            if is_policy_blocked(final_domain):
                rejected.append({"url": url, "final_url": final_url, "domain": final_domain, "reason": "redirected_to_policy_blocked_domain"})
                continue
            if is_non_source_domain(final_domain):
                rejected.append({"url": url, "final_url": final_url, "domain": final_domain, "reason": "redirected_to_non_inventory_reference_domain"})
                continue
            if final_domain in candidates_by_domain or final_domain in probed_domains:
                continue
            probed_domains.add(final_domain)
        title = clean(item.get("title"))
        snippet = clean(item.get("snippet"))
        score, evidence, cautions, style = score_candidate(final_url, title, snippet, html)
        if fetch_error:
            cautions.append(fetch_error)
        if score < args.min_score:
            rejected.append({"url": final_url, "domain": final_domain, "reason": "low_inventory_signal", "score": score})
            continue
        candidates_by_domain[final_domain] = {
            "name": title or final_domain,
            "url": final_url,
            "domain": final_domain,
            "score": score,
            "status": "direct_candidate",
            "parser_style_guess": style,
            "evidence": evidence,
            "cautions": cautions or ["manual bounded review required before parser work"],
            "recommended_next_step": "Manual bounded review; add a disabled backlog entry only if individual priced/weighted inventory is confirmed.",
            "discovered_by_query": item.get("query"),
        }

    candidates = sorted(candidates_by_domain.values(), key=lambda row: row["score"], reverse=True)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if provider else "skipped_no_search_credential",
        "search_provider": provider,
        "known_source_domain_count": len(known_domains),
        "queries": queries,
        "input_sha256": hashlib.sha256("\n".join(queries).encode()).hexdigest(),
        "warnings": warnings,
        "candidates": candidates,
        "rejected": rejected[:200],
    }


def write_markdown(report: dict, path: Path) -> None:
    lines = [
        "# Source Discovery Report",
        "",
        f"Generated: {report.get('generated_at')}",
        f"Status: `{report.get('status')}`",
        f"Search provider: `{report.get('search_provider') or 'none'}`",
        f"Candidate count: {len(report.get('candidates') or [])}",
        "",
    ]
    if report.get("warnings"):
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report["warnings"])
        lines.append("")
    lines.extend(["## Candidates", "", "| Score | Candidate | URL | Parser Guess | Evidence | Cautions |", "| --- | --- | --- | --- | --- | --- |"])
    for row in report.get("candidates") or []:
        evidence = "; ".join(row.get("evidence") or [])
        cautions = "; ".join(row.get("cautions") or [])
        lines.append(f"| {row.get('score')} | {row.get('name')} | {row.get('url')} | {row.get('parser_style_guess')} | {evidence} | {cautions} |")
    if not report.get("candidates"):
        lines.append("| - | No candidates found | - | - | - | - |")
    lines.extend(["", "## Rejected Summary", ""])
    rejected_counts = {}
    for row in report.get("rejected") or []:
        rejected_counts[row.get("reason", "unknown")] = rejected_counts.get(row.get("reason", "unknown"), 0) + 1
    if rejected_counts:
        lines.extend(f"- `{reason}`: {count}" for reason, count in sorted(rejected_counts.items()))
    else:
        lines.append("- None")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites", default=str(ROOT / "data" / "sites.json"))
    parser.add_argument("--backlog", default=str(ROOT / "docs" / "parser-backlog.md"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown", required=True)
    parser.add_argument("--query", action="append", help="Search query. May be supplied multiple times.")
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--max-candidates", type=int, default=20)
    parser.add_argument("--min-score", type=int, default=45)
    parser.add_argument("--probe-delay", type=float, default=1.0)
    args = parser.parse_args()

    report = discover(args)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(report, Path(args.markdown))
    print(f"Wrote {output_path}")
    print(f"Wrote {args.markdown}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Validate source-discovery review artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
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
SECRET_HINT_RE = re.compile(r"(?:API[_-]?KEY|ACCESS[_-]?TOKEN|CLIENT[_-]?SECRET|SUBSCRIPTION[_-]?KEY)", re.I)


def normalized_domain(value: str | None) -> str:
    parsed = urlparse(value or "")
    host = (parsed.netloc or parsed.path).lower().split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def parent_domain(domain: str) -> str:
    parts = domain.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else domain


def is_policy_blocked(domain: str) -> bool:
    root = parent_domain(domain)
    brand = domain.split(".", 1)[0]
    return (
        domain in POLICY_BLOCKED_DOMAINS
        or root in POLICY_BLOCKED_DOMAINS
        or any(domain.endswith(f".{blocked}") for blocked in POLICY_BLOCKED_DOMAINS)
        or brand in POLICY_BLOCKED_BRANDS
    )


def known_domains(sites_path: Path) -> set[str]:
    with sites_path.open(encoding="utf-8") as handle:
        sites = json.load(handle)
    domains = set()
    for site in sites:
        for value in [site.get("base_url"), *(site.get("inventory_urls") or [])]:
            domain = normalized_domain(value)
            if domain:
                domains.add(domain)
                domains.add(parent_domain(domain))
    return domains


def walk_values(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from walk_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_values(item)
    elif value is not None:
        yield str(value)


def validate(report: dict, sites_path: Path) -> list[str]:
    errors = []
    for key in ["generated_at", "status", "known_source_domain_count", "queries", "candidates", "rejected"]:
        if key not in report:
            errors.append(f"missing top-level key: {key}")
    if not isinstance(report.get("candidates"), list):
        errors.append("candidates must be a list")
        return errors
    known = known_domains(sites_path)
    for idx, candidate in enumerate(report.get("candidates") or []):
        prefix = f"candidate {idx}"
        if not isinstance(candidate, dict):
            errors.append(f"{prefix}: must be object")
            continue
        for key in ["name", "url", "domain", "score", "evidence", "recommended_next_step"]:
            if key not in candidate:
                errors.append(f"{prefix}: missing {key}")
        url = candidate.get("url")
        parsed = urlparse(str(url or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append(f"{prefix}: invalid url")
        url_domain = normalized_domain(url)
        domain = normalized_domain(candidate.get("domain") or url)
        if domain != url_domain:
            errors.append(f"{prefix}: domain {domain} does not match URL domain {url_domain}")
        domain = url_domain
        if domain in known or parent_domain(domain) in known:
            errors.append(f"{prefix}: candidate duplicates configured source domain {domain}")
        if is_policy_blocked(domain):
            errors.append(f"{prefix}: policy-blocked domain {domain} must not be a candidate")
        score = candidate.get("score")
        if not isinstance(score, int) or not 0 <= score <= 100:
            errors.append(f"{prefix}: score must be integer 0-100")
        if not isinstance(candidate.get("evidence"), list) or not candidate.get("evidence"):
            errors.append(f"{prefix}: evidence must be a non-empty list")
        if candidate.get("enabled") is True:
            errors.append(f"{prefix}: discovery output must not enable sources")
    serialized_values = "\n".join(walk_values(report))
    if SECRET_HINT_RE.search(serialized_values):
        errors.append("report appears to contain secret/key/token field text")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report")
    parser.add_argument("--sites", default=str(ROOT / "data" / "sites.json"))
    args = parser.parse_args()
    with Path(args.report).open(encoding="utf-8") as handle:
        report = json.load(handle)
    errors = validate(report, Path(args.sites))
    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"source discovery report ok: {len(report.get('candidates') or [])} candidates")


if __name__ == "__main__":
    main()

"""Scrape Meralco's public registered net-metering aggregate counts.

This is a best-effort scraper with a manual-fallback prompt. If Meralco's page
layout changes, the script will not silently zero out the count; it will exit
non-zero and ask the operator to update meralco_aggregates.json by hand.

Run:
    python scrape_meralco.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PIPELINE_DIR = Path(__file__).parent
AGG_PATH = PIPELINE_DIR / "meralco_aggregates.json"

CANDIDATE_URLS = [
    "https://company.meralco.com.ph/advocacies/solar-net-metering/why-is-net-metering-limited-to-100kw",
    "https://www.meralco.com.ph/residential/electric-service/solar-net-metering",
]

USER_AGENT = "solar-map-ph/1.0 (+https://github.com/xmpuspus/solar-map-ph)"


def fetch(url: str, timeout: int = 15) -> str | None:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        print(f"fetch failed for {url}: {exc}", file=sys.stderr)
        return None


def extract_numbers(text: str) -> dict[str, int | float | None]:
    soup = BeautifulSoup(text, "html.parser")
    body = soup.get_text(" ", strip=True)
    out: dict[str, int | float | None] = {
        "registered_installations": None,
        "registered_capacity_mw_aggregate": None,
    }
    install_match = re.search(
        r"(\d{1,3}(?:[,]\d{3})*|\d+)\s*(?:net[- ]metering)?\s*installations?",
        body,
        flags=re.IGNORECASE,
    )
    if install_match:
        try:
            out["registered_installations"] = int(install_match.group(1).replace(",", ""))
        except ValueError:
            pass
    mw_match = re.search(
        r"(\d{1,4}(?:\.\d+)?)\s*(?:MW|megawatts?)",
        body,
        flags=re.IGNORECASE,
    )
    if mw_match:
        try:
            out["registered_capacity_mw_aggregate"] = float(mw_match.group(1))
        except ValueError:
            pass
    return out


def manual_fallback() -> None:
    print(
        "\nScraper could not extract numbers automatically.\n"
        "Action required:\n"
        "  1. Visit one of the source URLs in meralco_aggregates.json\n"
        "  2. Find the latest 'X net-metering installations totaling Y MW' figure\n"
        "  3. Edit meralco_aggregates.json by hand:\n"
        "       registered_installations\n"
        "       registered_capacity_mw_aggregate\n"
        "       as_of\n"
        "       source_urls (append the new article)\n"
        "  4. Re-run validate.py\n",
        file=sys.stderr,
    )


def main() -> int:
    extracted: dict[str, int | float | None] | None = None
    used_url: str | None = None
    partial: dict[str, int | float | None] | None = None
    for url in CANDIDATE_URLS:
        text = fetch(url)
        if text is None:
            continue
        result = extract_numbers(text)
        installs = result.get("registered_installations")
        mw = result.get("registered_capacity_mw_aggregate")
        if installs and mw:
            extracted = result
            used_url = url
            break
        # Record the best partial match seen so far so we can persist whichever
        # field did come through. A partial match is more useful than no match
        # plus it lets the human reviewer fill in the missing value.
        if installs or mw:
            if partial is None or sum(1 for v in result.values() if v) > sum(
                1 for v in partial.values() if v
            ):
                partial = result
                used_url = url

    if extracted is None:
        if partial is not None:
            print(
                "WARN: partial extraction. One of the two fields could not be parsed. "
                "Persisting what we have; review and fill the missing field by hand.",
                file=sys.stderr,
            )
            extracted = partial
        else:
            manual_fallback()
            return 2

    with AGG_PATH.open() as f:
        agg = json.load(f)
    agg["registered_installations"] = extracted["registered_installations"]
    agg["registered_capacity_mw_aggregate"] = extracted["registered_capacity_mw_aggregate"]
    agg["as_of"] = date.today().isoformat()
    if used_url and used_url not in agg.get("source_urls", []):
        agg.setdefault("source_urls", []).append(used_url)

    with AGG_PATH.open("w") as f:
        json.dump(agg, f, indent=2)
    print(
        f"Updated meralco_aggregates.json: {extracted['registered_installations']} installations, "
        f"{extracted['registered_capacity_mw_aggregate']} MW (source: {used_url})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

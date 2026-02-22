#!/usr/bin/env python3
"""Extract player Transactions sections from downloaded Baseball-Reference HTML files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from html import unescape


DATE_RE = re.compile(
    r"^\s*(January|February|March|April|May|June|July|August|September|October|November|December) "
    r"\d{1,2}, \d{4}\s*$"
)
TRANSACTIONS_DIV_RE = re.compile(
    r"<div[^>]*id=[\"']div_transactions_other[\"'][^>]*>(.*?)</div>",
    re.DOTALL | re.IGNORECASE,
)
P_TAG_RE = re.compile(r"<p\b[^>]*>(.*?)</p>", re.DOTALL | re.IGNORECASE)
STRONG_RE = re.compile(r"<strong>(.*?)</strong>", re.DOTALL | re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


def clean_text(html_fragment: str) -> str:
    text = TAG_RE.sub("", html_fragment)
    text = unescape(text)
    return " ".join(text.split())


def infer_transaction_type(text_after_date: str) -> str:
    lowered = text_after_date.lower()
    if lowered.startswith("traded "):
        return "Traded"
    if lowered.startswith("drafted "):
        return "Drafted"
    if lowered.startswith("signed "):
        return "Signed"
    if lowered.startswith("granted free agency"):
        return "Granted Free Agency"
    if lowered.startswith("released "):
        return "Released"
    if lowered.startswith("purchased "):
        return "Purchased"
    if lowered.startswith("selected "):
        return "Selected"
    if lowered.startswith("designated "):
        return "Designated"

    # Fallback: first sentence/action phrase.
    if "." in text_after_date:
        return text_after_date.split(".", 1)[0].strip()
    return text_after_date.strip()


def extract_transactions_from_html(html_text: str, player_id: str) -> List[Dict[str, str]]:
    match = TRANSACTIONS_DIV_RE.search(html_text)
    if not match:
        return []

    section_html = match.group(1)
    records: List[Dict[str, str]] = []

    for p_html in P_TAG_RE.findall(section_html):
        strong_match = STRONG_RE.search(p_html)
        if not strong_match:
            continue

        strong_text = clean_text(strong_match.group(1)).rstrip(":").strip()
        if not DATE_RE.match(strong_text):
            continue

        # Remove only the first <strong>...</strong> (date label) and parse remaining text.
        body_html = STRONG_RE.sub("", p_html, count=1)
        body_text = clean_text(body_html)
        if not body_text:
            continue

        records.append(
            {
                "date": strong_text,
                "transaction_type": infer_transaction_type(body_text),
                "player_id": player_id,
            }
        )

    return records


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract transaction records from downloaded player HTML pages."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("players"),
        help="Directory containing downloaded player HTML files (default: players)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("player_transactions.json"),
        help="Output JSON file path (default: player_transactions.json)",
    )
    args = parser.parse_args()

    html_files = sorted(args.input_dir.glob("*.html"))
    if not html_files:
        raise ValueError(f"No .html files found in {args.input_dir}")

    all_records: List[Dict[str, str]] = []
    for html_file in html_files:
        player_id = html_file.stem
        html_text = html_file.read_text(encoding="utf-8", errors="replace")
        all_records.extend(extract_transactions_from_html(html_text, player_id))

    args.output.write_text(json.dumps(all_records, indent=2), encoding="utf-8")
    print(
        f"Wrote {len(all_records)} transaction records for {len(html_files)} players "
        f"to {args.output}"
    )


if __name__ == "__main__":
    main()



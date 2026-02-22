#!/usr/bin/env python3
"""Extract MLB trade transactions from a Baseball-Reference season HTML file.

This script intentionally uses only Python standard-library modules.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse


FORBIDDEN_PHRASES = (
    "player to be named later",
    "players to be named later",
    "cash",
)

TEAM_HREF_RE = re.compile(r"^/teams/([A-Z]{2,3})/\d{4}\.shtml$")
PLAYER_HREF_RE = re.compile(r"^/players/[a-z]/([a-z0-9.\-]+)\.shtml$")


def normalize_space(text: str) -> str:
    return " ".join(text.split())


class ParagraphParser(HTMLParser):
    """Collect rendered text plus link spans for an HTML paragraph fragment."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.links: List[Dict[str, object]] = []
        self.cursor = 0
        self.in_anchor = False
        self.anchor_href: Optional[str] = None
        self.anchor_start = 0
        self.anchor_text_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag != "a":
            return
        self.in_anchor = True
        attrs_dict = dict(attrs)
        self.anchor_href = attrs_dict.get("href")
        self.anchor_start = self.cursor
        self.anchor_text_parts = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)
        self.cursor += len(data)
        if self.in_anchor:
            self.anchor_text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self.in_anchor:
            return
        self.links.append(
            {
                "href": self.anchor_href,
                "text": "".join(self.anchor_text_parts),
                "start": self.anchor_start,
                "end": self.cursor,
            }
        )
        self.in_anchor = False
        self.anchor_href = None
        self.anchor_text_parts = []

    def result(self) -> Tuple[str, List[Dict[str, object]]]:
        return "".join(self.parts), self.links


def linearize_paragraph(paragraph_html: str) -> Tuple[str, List[Dict[str, object]]]:
    parser = ParagraphParser()
    parser.feed(paragraph_html)
    return parser.result()


def extract_team_code(href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    match = TEAM_HREF_RE.match(href)
    if not match:
        return None
    return match.group(1)


def extract_player_id(href: Optional[str]) -> Optional[str]:
    if not href:
        return None

    players_match = PLAYER_HREF_RE.match(href)
    if players_match:
        return players_match.group(1)

    if href.startswith("/register/player.fcgi"):
        parsed = urlparse(href)
        query = parse_qs(parsed.query)
        player_id = query.get("id", [None])[0]
        return player_id

    return None


def is_players_only_side(
    raw_text: str,
    links: List[Dict[str, object]],
    side_start: int,
    side_end: int,
) -> bool:
    """True when a trade side contains only player links plus simple separators."""
    side_player_links: List[Dict[str, object]] = []
    for link in links:
        href = link["href"]
        start = int(link["start"])
        if not (side_start <= start < side_end):
            continue
        if extract_player_id(href if isinstance(href, str) else None):
            side_player_links.append(link)

    if not side_player_links:
        return False

    chars = list(raw_text[side_start:side_end])
    for link in side_player_links:
        rel_start = int(link["start"]) - side_start
        rel_end = int(link["end"]) - side_start
        for idx in range(max(0, rel_start), min(len(chars), rel_end)):
            chars[idx] = " "

    leftover = "".join(chars).lower()
    leftover = re.sub(r"\(minors\)", " ", leftover)
    leftover = re.sub(r"\band\b", " ", leftover)
    leftover = re.sub(r"[,\.;\(\)\-]", " ", leftover)
    leftover = normalize_space(leftover)
    return leftover == ""


def parse_trade_from_paragraph(paragraph_html: str, trade_date: str) -> Optional[Dict[str, object]]:
    raw_text, links = linearize_paragraph(paragraph_html)
    lowered = raw_text.lower()
    normalized = normalize_space(lowered)

    if " traded " not in lowered or " to the " not in lowered or " for " not in lowered:
        return None

    if any(phrase in normalized for phrase in FORBIDDEN_PHRASES):
        return None

    traded_idx = lowered.find(" traded ")
    to_idx = lowered.find(" to the ", traded_idx + 1)
    for_idx = lowered.find(" for ", to_idx + 1)
    if traded_idx == -1 or to_idx == -1 or for_idx == -1:
        return None

    from_team_code = None
    to_team_code = None
    from_player_ids: List[str] = []
    to_player_ids: List[str] = []

    for link in links:
        href = link["href"]
        start = int(link["start"])
        team_code = extract_team_code(href if isinstance(href, str) else None)
        player_id = extract_player_id(href if isinstance(href, str) else None)

        if team_code:
            if start < traded_idx:
                from_team_code = team_code
            elif to_idx <= start < for_idx and to_team_code is None:
                to_team_code = team_code
            continue

        if player_id:
            if traded_idx < start < to_idx:
                from_player_ids.append(player_id)
            elif start > for_idx:
                to_player_ids.append(player_id)

    if not from_team_code or not to_team_code:
        return None

    from_assets_start = traded_idx + len(" traded ")
    from_assets_end = to_idx
    to_assets_start = for_idx + len(" for ")
    to_assets_end = len(raw_text)

    if not is_players_only_side(raw_text, links, from_assets_start, from_assets_end):
        return None
    if not is_players_only_side(raw_text, links, to_assets_start, to_assets_end):
        return None

    return {
        "date": trade_date,
        "from_team": from_team_code,
        "to_team": to_team_code,
        "from_player_ids": from_player_ids,
        "to_player_ids": to_player_ids,
    }


LI_BLOCK_RE = re.compile(
    r"<li>\s*<span>([A-Za-z]+ \d{1,2}, \d{4})</span>\s*<div>(.*?)</div>\s*</li>",
    re.DOTALL,
)
PARAGRAPH_RE = re.compile(r"<p>(.*?)</p>", re.DOTALL)


def extract_trades(html_path: Path) -> List[Dict[str, object]]:
    html_text = html_path.read_text(encoding="utf-8")
    trades: List[Dict[str, object]] = []
    for date_text, day_html in LI_BLOCK_RE.findall(html_text):
        trade_date = normalize_space(date_text)
        for paragraph_html in PARAGRAPH_RE.findall(day_html):
            trade = parse_trade_from_paragraph(paragraph_html, trade_date)
            if trade:
                trades.append(trade)

    return trades


def list_year_html_files(input_dir: Path) -> List[Path]:
    return sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file() and re.fullmatch(r"\d{4}\.html", path.name)
    )


def dedupe_trades(trades: List[Dict[str, object]]) -> List[Dict[str, object]]:
    deduped: List[Dict[str, object]] = []
    seen = set()
    for trade in trades:
        key = (
            trade["date"],
            trade["from_team"],
            trade["to_team"],
            tuple(trade["from_player_ids"]),
            tuple(trade["to_player_ids"]),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(trade)
    return deduped


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract trades from all Baseball-Reference year HTML files."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("."),
        help="Directory containing year HTML files named YYYY.html (default: current directory)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("trades.json"),
        help="Output JSON file path (default: trades.json)",
    )
    args = parser.parse_args()

    year_files = list_year_html_files(args.input_dir)
    if not year_files:
        raise ValueError(f"No YYYY.html files found in {args.input_dir}")

    all_trades: List[Dict[str, object]] = []
    for html_file in year_files:
        all_trades.extend(extract_trades(html_file))

    trades = dedupe_trades(all_trades)
    args.output.write_text(json.dumps(trades, indent=2), encoding="utf-8")
    print(
        f"Wrote {len(trades)} unique trades to {args.output} "
        f"from {len(year_files)} files"
    )


if __name__ == "__main__":
    main()


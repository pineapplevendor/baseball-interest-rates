#!/usr/bin/env python3
"""Extract per-season WAR rows from downloaded player pages."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from html import unescape


TABLE_ID_RE = re.compile(
    r'<table[^>]*id=["\'](players_standard_(?:batting|pitching))["\'][^>]*>',
    re.IGNORECASE,
)
ROW_RE = re.compile(r"<tr\b([^>]*)>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
CELL_RE = re.compile(r"<(td|th)\b([^>]*)>(.*?)</\1>", re.DOTALL | re.IGNORECASE)
DATA_STAT_RE = re.compile(r'data-stat=["\']([^"\']+)["\']', re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
YEAR_RE = re.compile(r"^\d{4}$")


def clean_html_text(value: str) -> str:
    return " ".join(unescape(TAG_RE.sub("", value)).split())


def extract_first_standard_table(html_text: str) -> Optional[str]:
    match = TABLE_ID_RE.search(html_text)
    if not match:
        return None

    table_start = match.start()
    table_open_end = html_text.find(">", table_start)
    if table_open_end == -1:
        return None

    table_end = html_text.find("</table>", table_open_end)
    if table_end == -1:
        return None

    return html_text[table_start : table_end + len("</table>")]


def parse_war_value(raw_war: str) -> Optional[float]:
    value = raw_war.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def is_aggregate_team(team: str) -> bool:
    token = team.strip().upper()
    return token == "TOT" or token.endswith("TM")


def extract_rows_from_table(table_html: str, player_id: str) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []

    for tr_attrs, tr_inner in ROW_RE.findall(table_html):
        attrs_lower = tr_attrs.lower()
        if 'class="thead"' in attrs_lower or "spacer" in attrs_lower:
            continue

        cells_by_stat: Dict[str, str] = {}
        for _tag, cell_attrs, cell_inner in CELL_RE.findall(tr_inner):
            stat_match = DATA_STAT_RE.search(cell_attrs)
            if not stat_match:
                continue
            stat_name = stat_match.group(1).strip().lower()
            cells_by_stat[stat_name] = clean_html_text(cell_inner)

        year = cells_by_stat.get("year_id", "")
        team = cells_by_stat.get("team_name_abbr", "")
        war_raw = (
            cells_by_stat.get("b_war", "")
            or cells_by_stat.get("p_war", "")
            or cells_by_stat.get("war", "")
        )

        if not YEAR_RE.match(year):
            continue
        if not team or is_aggregate_team(team):
            continue

        war_value = parse_war_value(war_raw)
        if war_value is None:
            continue

        rows.append(
            {
                "player_id": player_id,
                "team": team,
                "year": int(year),
                "WAR": war_value,
            }
        )

    return rows


def extract_player_war(html_text: str, player_id: str) -> List[Dict[str, object]]:
    table_html = extract_first_standard_table(html_text)
    if table_html is None:
        return []
    return extract_rows_from_table(table_html, player_id)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Extract player WAR by season/team from the first standard table "
            "(batting or pitching) in each downloaded player HTML."
        )
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
        default=Path("player_war.json"),
        help="Output JSON file path (default: player_war.json)",
    )
    args = parser.parse_args()

    html_files = sorted(args.input_dir.glob("*.html"))
    if not html_files:
        raise ValueError(f"No .html files found in {args.input_dir}")

    all_rows: List[Dict[str, object]] = []
    for html_file in html_files:
        player_id = html_file.stem
        html_text = html_file.read_text(encoding="utf-8", errors="replace")
        all_rows.extend(extract_player_war(html_text, player_id))

    args.output.write_text(json.dumps(all_rows, indent=2), encoding="utf-8")
    print(
        f"Wrote {len(all_rows)} WAR rows for {len(html_files)} players "
        f"to {args.output}"
    )


if __name__ == "__main__":
    main()


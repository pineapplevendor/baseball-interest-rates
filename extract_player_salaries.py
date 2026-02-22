#!/usr/bin/env python3
"""Extract per-season salary rows from the div_br-salaries table in each player HTML."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import List, Optional
from html import unescape


DIV_SALARIES_RE = re.compile(
    r'<div[^>]*id=["\']div_br-salaries["\'][^>]*>(.*?)</div>\s*<div[^>]*id=["\']tfooter_br-salaries',
    re.DOTALL | re.IGNORECASE,
)
ROW_RE = re.compile(r"<tr\b([^>]*)>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
CELL_RE = re.compile(r"<(td|th)\b([^>]*)>(.*?)</\1>", re.DOTALL | re.IGNORECASE)
DATA_STAT_RE = re.compile(r'data-stat=["\']([^"\']+)["\']', re.IGNORECASE)
DATA_AMOUNT_RE = re.compile(r'data-amount=["\']([^"\']+)["\']', re.IGNORECASE)
YEAR_RE = re.compile(r"^\d{4}$")
TAG_RE = re.compile(r"<[^>]+>")


def clean_html_text(value: str) -> str:
    return " ".join(unescape(TAG_RE.sub("", value)).split())


def extract_salaries_table(html_text: str) -> Optional[str]:
    """Extract the table HTML from within div_br-salaries (may be inside comments)."""
    match = DIV_SALARIES_RE.search(html_text)
    if not match:
        return None
    return match.group(1)


def parse_salary_amount(raw: str) -> Optional[float]:
    """Parse salary from display text like '$300,000' or numeric string."""
    s = raw.strip().replace("$", "").replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def extract_rows_from_salaries_table(table_html: str, player_id: str) -> List[dict]:
    rows: List[dict] = []

    for tr_attrs, tr_inner in ROW_RE.findall(table_html):
        attrs_lower = tr_attrs.lower()
        if 'class="thead"' in attrs_lower or "spacer" in attrs_lower:
            continue

        cells_by_stat: dict[str, str] = {}
        data_amount: Optional[str] = None
        for _tag, cell_attrs, cell_inner in CELL_RE.findall(tr_inner):
            stat_match = DATA_STAT_RE.search(cell_attrs)
            if stat_match:
                stat_name = stat_match.group(1).strip().lower()
                cells_by_stat[stat_name] = clean_html_text(cell_inner)
            if "data-stat=\"Salary\"" in cell_attrs or 'data-stat="Salary"' in cell_attrs:
                amt_match = DATA_AMOUNT_RE.search(cell_attrs)
                if amt_match:
                    data_amount = amt_match.group(1).strip()

        year_str = cells_by_stat.get("year_id", "")
        if not YEAR_RE.match(year_str):
            continue

        if "total_head" in cells_by_stat or "salary_total" in cells_by_stat:
            continue

        team = cells_by_stat.get("team_name", "").strip()
        if not team:
            continue

        salary_val: Optional[float] = None
        if data_amount:
            try:
                salary_val = float(data_amount)
            except ValueError:
                pass
        if salary_val is None:
            salary_raw = cells_by_stat.get("salary", "")
            salary_val = parse_salary_amount(salary_raw)

        if salary_val is None:
            continue

        rows.append(
            {
                "player_id": player_id,
                "year": int(year_str),
                "team": team,
                "salary": round(salary_val, 2),
            }
        )

    return rows


def extract_player_salaries(html_text: str, player_id: str) -> List[dict]:
    table_html = extract_salaries_table(html_text)
    if table_html is None:
        return []
    return extract_rows_from_salaries_table(table_html, player_id)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Extract player salaries by season/team from the div_br-salaries table "
            "in each downloaded player HTML."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("players"),
        help="Directory containing player HTML files (default: players)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("player_salaries.json"),
        help="Output JSON file path (default: player_salaries.json)",
    )
    args = parser.parse_args()

    html_files = sorted(args.input_dir.glob("*.html"))
    if not html_files:
        raise ValueError(f"No .html files found in {args.input_dir}")

    all_rows: List[dict] = []
    for html_file in html_files:
        player_id = html_file.stem
        html_text = html_file.read_text(encoding="utf-8", errors="replace")
        all_rows.extend(extract_player_salaries(html_text, player_id))

    args.output.write_text(json.dumps(all_rows, indent=2), encoding="utf-8")
    print(
        f"Wrote {len(all_rows)} salary rows for {len(html_files)} players "
        f"to {args.output}"
    )


if __name__ == "__main__":
    main()

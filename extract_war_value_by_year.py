#!/usr/bin/env python3
"""Combine player WAR and salaries by player-year, with WAR per million dollars."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Dict, List


def load_war_by_player_year(path: Path) -> Dict[str, Dict[int, float]]:
    """Returns player_id -> {year -> total WAR} (sums across teams)."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    by_player_year: DefaultDict[str, DefaultDict[int, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    for row in rows:
        player_id = row.get("player_id")
        year = row.get("year")
        war = row.get("WAR")
        if not isinstance(player_id, str):
            continue
        if not isinstance(year, int):
            continue
        if not isinstance(war, (int, float)):
            continue
        by_player_year[player_id][year] += float(war)
    return {pid: dict(sorted(years.items())) for pid, years in by_player_year.items()}


def load_salary_by_player_year(path: Path) -> Dict[str, Dict[int, float]]:
    """Returns player_id -> {year -> total salary} (sums across teams if traded)."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    by_player_year: DefaultDict[str, DefaultDict[int, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    for row in rows:
        player_id = row.get("player_id")
        year = row.get("year")
        salary = row.get("salary")
        if not isinstance(player_id, str):
            continue
        if not isinstance(year, int):
            continue
        if not isinstance(salary, (int, float)):
            continue
        by_player_year[player_id][year] += float(salary)
    return {pid: dict(sorted(years.items())) for pid, years in by_player_year.items()}


def build_war_value_rows(
    war_by_player_year: Dict[str, Dict[int, float]],
    salary_by_player_year: Dict[str, Dict[int, float]],
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for player_id, years_war in war_by_player_year.items():
        years_salary = salary_by_player_year.get(player_id, {})
        for year, war in years_war.items():
            salary = years_salary.get(year)
            if salary is None or salary <= 0:
                continue
            war_per_million = war / (salary / 1_000_000)
            rows.append(
                {
                    "player_id": player_id,
                    "year": year,
                    "war": round(war, 2),
                    "salary": round(salary, 2),
                    "war_per_million": round(war_per_million, 4),
                }
            )
    return sorted(rows, key=lambda r: (r["player_id"], r["year"]))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Combine player WAR and salaries by player-year with WAR per million."
    )
    parser.add_argument(
        "--player-war",
        type=Path,
        default=Path("player_war.json"),
        help="Path to player WAR JSON",
    )
    parser.add_argument(
        "--player-salaries",
        type=Path,
        default=Path("player_salaries.json"),
        help="Path to player salaries JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("war_value_by_year.json"),
        help="Output JSON file path",
    )
    args = parser.parse_args()

    war_by_player_year = load_war_by_player_year(args.player_war)
    salary_by_player_year = load_salary_by_player_year(args.player_salaries)
    rows = build_war_value_rows(war_by_player_year, salary_by_player_year)

    args.output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} player-year rows to {args.output}")


if __name__ == "__main__":
    main()

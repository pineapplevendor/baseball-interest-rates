#!/usr/bin/env python3
"""Build intermediate JSON: each trade with WAR-by-year and salary-adjusted value for each player until retirement or free agency."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import DefaultDict, Dict, List, Optional, Tuple


DATE_FMT = "%B %d, %Y"
FREE_AGENCY_TYPE = "Granted Free Agency"


def parse_trade_date(date_text: str) -> datetime:
    return datetime.strptime(date_text, DATE_FMT)


def season_start_year(trade_dt: datetime) -> int:
    """Trades in Nov/Dec are treated as affecting the next season."""
    if trade_dt.month >= 11:
        return trade_dt.year + 1
    return trade_dt.year


def load_trades(path: Path) -> List[Dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_player_war(path: Path) -> Dict[str, Dict[int, float]]:
    """Returns player_id -> {year -> total WAR} (sums across teams when player has multiple teams in a year)."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    war_by_player_year: DefaultDict[str, DefaultDict[int, float]] = defaultdict(
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
        war_by_player_year[player_id][year] += float(war)
    result: Dict[str, Dict[int, float]] = {}
    for player_id, years in war_by_player_year.items():
        result[player_id] = dict(sorted(years.items()))
    return result


def load_war_value_by_year(path: Path) -> Dict[str, Dict[int, float]]:
    """Returns player_id -> {year -> war_per_million} from war_value_by_year.json."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    by_player_year: DefaultDict[str, DefaultDict[int, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    for row in rows:
        player_id = row.get("player_id")
        year = row.get("year")
        war_per_million = row.get("war_per_million")
        if not isinstance(player_id, str):
            continue
        if not isinstance(year, int):
            continue
        if not isinstance(war_per_million, (int, float)):
            continue
        by_player_year[player_id][year] += float(war_per_million)
    return {pid: dict(sorted(years.items())) for pid, years in by_player_year.items()}


def load_free_agency_dates(path: Path) -> Dict[str, List[datetime]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    by_player: DefaultDict[str, List[datetime]] = defaultdict(list)
    for row in rows:
        player_id = row.get("player_id")
        transaction_type = row.get("transaction_type")
        date_text = row.get("date")
        if not isinstance(player_id, str):
            continue
        if transaction_type != FREE_AGENCY_TYPE:
            continue
        if not isinstance(date_text, str):
            continue
        try:
            dt = parse_trade_date(date_text)
        except ValueError:
            continue
        by_player[player_id].append(dt)
    for dates in by_player.values():
        dates.sort()
    return dict(by_player)


def first_free_agency_year_after(
    trade_dt: datetime,
    free_agency_dates: List[datetime],
) -> Optional[int]:
    """Year of first post-trade 'Granted Free Agency' (WAR through that season is included)."""
    for dt in free_agency_dates:
        if dt > trade_dt:
            return dt.year
    return None


def get_player_cutoff_year(
    player_id: str,
    trade_dt: datetime,
    start_year: int,
    war_by_player: Dict[str, Dict[int, float]],
    free_agency_by_player: Dict[str, List[datetime]],
) -> Tuple[int, str]:
    """
    Returns (cutoff_year, cutoff_reason).
    cutoff_year is the last year to include (inclusive).
    cutoff_reason is 'free_agency' or 'retirement'.
    """
    fa_year = first_free_agency_year_after(
        trade_dt, free_agency_by_player.get(player_id, [])
    )
    player_years = war_by_player.get(player_id, {})
    last_war_year = max(player_years.keys()) if player_years else start_year - 1

    if fa_year is not None and last_war_year is not None:
        cutoff = min(fa_year, last_war_year)
        reason = "free_agency" if fa_year <= last_war_year else "retirement"
    elif fa_year is not None:
        cutoff = fa_year
        reason = "free_agency"
    elif last_war_year is not None:
        cutoff = last_war_year
        reason = "retirement"
    else:
        cutoff = start_year - 1
        reason = "no_data"
    return cutoff, reason


def build_player_war_by_year(
    player_id: str,
    start_year: int,
    cutoff_year: int,
    war_by_player: Dict[str, Dict[int, float]],
) -> Dict[str, float]:
    """Returns {year_str: war} for years from start_year through cutoff_year."""
    result: Dict[str, float] = {}
    player_war = war_by_player.get(player_id, {})
    for year in range(start_year, cutoff_year + 1):
        war = player_war.get(year, 0.0)
        result[str(year)] = war
    return result


def compute_interest_rate(
    sent_value: float,
    received_value: float,
    sent_weighted_avg_year: Optional[float],
    received_weighted_avg_year: Optional[float],
) -> Optional[float]:
    """
    r = (A / P) ^ (1/T) - 1, symmetric across both sides of the trade.
    Positive when less value (sooner) is exchanged for more value (later).
    Negative when more value (sooner) is exchanged for less value (later).
    Returns None if not computable.
    """
    if sent_weighted_avg_year is None or received_weighted_avg_year is None:
        return None
    smaller_val = min(sent_value, received_value)
    larger_val = max(sent_value, received_value)
    if sent_value < received_value:
        year_of_smaller = sent_weighted_avg_year
        year_of_larger = received_weighted_avg_year
    elif sent_value > received_value:
        year_of_smaller = received_weighted_avg_year
        year_of_larger = sent_weighted_avg_year
    else:
        year_of_smaller = sent_weighted_avg_year
        year_of_larger = received_weighted_avg_year
    T = abs(year_of_larger - year_of_smaller)
    if smaller_val <= 0 or T <= 0:
        return None
    if larger_val <= 0:
        return None
    if year_of_smaller < year_of_larger:
        ratio = larger_val / smaller_val
    else:
        ratio = smaller_val / larger_val
    if ratio <= 0:
        return None
    return round((ratio ** (1 / T)) - 1, 4)


def compute_side_totals(
    players_side: Dict[str, Dict[str, object]],
) -> Tuple[float, Optional[float]]:
    """
    Returns (total_war, weighted_avg_year).
    total_war sums all WAR (including negative).
    weighted_avg_year = sum(year * war) / sum(war) for seasons with positive WAR only;
    None if no positive WAR.
    """
    total_war = 0.0
    positive_weighted_sum = 0.0
    positive_war_total = 0.0
    for player_data in players_side.values():
        war_by_year = player_data.get("war_by_year", {})
        if not isinstance(war_by_year, dict):
            continue
        for year_str, war in war_by_year.items():
            if not isinstance(war, (int, float)):
                continue
            try:
                year = int(year_str)
            except (ValueError, TypeError):
                continue
            total_war += war
            if war > 0:
                positive_weighted_sum += year * war
                positive_war_total += war
    if positive_war_total == 0:
        return total_war, None
    return total_war, round(positive_weighted_sum / positive_war_total, 2)


def compute_side_totals_per_million(
    players_side: Dict[str, Dict[str, object]],
    war_per_million_by_player_year: Dict[str, Dict[int, float]],
) -> Tuple[float, Optional[float], Dict[str, Dict[str, float]]]:
    """
    Returns (total_value_per_million, weighted_avg_year, value_per_million_by_player).
    Uses pre-computed war_per_million from war_value_by_year.json.
    Player-years without salary data contribute 0.
    weighted_avg_year uses positive value_per_million as weights.
    """
    total_value = 0.0
    positive_weighted_sum = 0.0
    positive_value_total = 0.0
    value_per_million_by_player: Dict[str, Dict[str, float]] = {}

    for player_id, player_data in players_side.items():
        war_by_year = player_data.get("war_by_year", {})
        if not isinstance(war_by_year, dict):
            continue
        player_war_per_million = war_per_million_by_player_year.get(player_id, {})
        player_values: Dict[str, float] = {}
        for year_str, _war in war_by_year.items():
            try:
                year = int(year_str)
            except (ValueError, TypeError):
                continue
            value = player_war_per_million.get(year, 0.0)
            player_values[year_str] = round(value, 4)
            total_value += value
            if value > 0:
                positive_weighted_sum += year * value
                positive_value_total += value
        value_per_million_by_player[player_id] = player_values

    if positive_value_total == 0:
        return total_value, None, value_per_million_by_player
    weighted_avg = round(positive_weighted_sum / positive_value_total, 2)
    return total_value, weighted_avg, value_per_million_by_player


def build_trade_war_rows(
    trades: List[Dict[str, object]],
    war_by_player: Dict[str, Dict[int, float]],
    war_per_million_by_player_year: Dict[str, Dict[int, float]],
    free_agency_by_player: Dict[str, List[datetime]],
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for trade in trades:
        date_text = str(trade.get("date", ""))
        from_team = str(trade.get("from_team", ""))
        to_team = str(trade.get("to_team", ""))
        from_players = [p for p in trade.get("from_player_ids", []) if isinstance(p, str)]
        to_players = [p for p in trade.get("to_player_ids", []) if isinstance(p, str)]

        try:
            trade_dt = parse_trade_date(date_text)
        except ValueError:
            continue
        start_year = season_start_year(trade_dt)

        def build_side(player_ids: List[str]) -> Dict[str, object]:
            side: Dict[str, object] = {}
            for player_id in player_ids:
                cutoff_year, cutoff_reason = get_player_cutoff_year(
                    player_id,
                    trade_dt,
                    start_year,
                    war_by_player,
                    free_agency_by_player,
                )
                war_by_year = build_player_war_by_year(
                    player_id, start_year, cutoff_year, war_by_player
                )
                side[player_id] = {
                    "war_by_year": war_by_year,
                    "cutoff_year": cutoff_year,
                    "cutoff_reason": cutoff_reason,
                }
            return side

        players_sent = build_side(from_players)
        players_received = build_side(to_players)

        sent_value, sent_weighted_avg_year = compute_side_totals(players_sent)
        received_value, received_weighted_avg_year = compute_side_totals(
            players_received
        )

        (
            sent_value_per_million,
            sent_weighted_avg_year_per_million,
            sent_value_by_player,
        ) = compute_side_totals_per_million(
            players_sent, war_per_million_by_player_year
        )
        (
            received_value_per_million,
            received_weighted_avg_year_per_million,
            received_value_by_player,
        ) = compute_side_totals_per_million(
            players_received, war_per_million_by_player_year
        )

        # Round weighted avg years to nearest full year
        if sent_weighted_avg_year is not None:
            sent_weighted_avg_year = round(sent_weighted_avg_year)
        if received_weighted_avg_year is not None:
            received_weighted_avg_year = round(received_weighted_avg_year)
        if sent_weighted_avg_year_per_million is not None:
            sent_weighted_avg_year_per_million = round(
                sent_weighted_avg_year_per_million
            )
        if received_weighted_avg_year_per_million is not None:
            received_weighted_avg_year_per_million = round(
                received_weighted_avg_year_per_million
            )

        interest_rate = compute_interest_rate(
            sent_value,
            received_value,
            sent_weighted_avg_year,
            received_weighted_avg_year,
        )
        interest_rate_salary_adjusted = compute_interest_rate(
            sent_value_per_million,
            received_value_per_million,
            sent_weighted_avg_year_per_million,
            received_weighted_avg_year_per_million,
        )

        for pid, vals in sent_value_by_player.items():
            players_sent[pid]["value_per_million_by_year"] = vals
        for pid, vals in received_value_by_player.items():
            players_received[pid]["value_per_million_by_year"] = vals

        rows.append(
            {
                "date": date_text,
                "from_team": from_team,
                "to_team": to_team,
                "from_player_ids": from_players,
                "to_player_ids": to_players,
                "valuation_start_year": start_year,
                "players_sent": players_sent,
                "players_received": players_received,
                "sent_value": round(sent_value, 2),
                "received_value": round(received_value, 2),
                "sent_weighted_avg_year": sent_weighted_avg_year,
                "received_weighted_avg_year": received_weighted_avg_year,
                "interest_rate": interest_rate,
                "sent_value_per_million": round(sent_value_per_million, 4),
                "received_value_per_million": round(
                    received_value_per_million, 4
                ),
                "sent_weighted_avg_year_per_million": sent_weighted_avg_year_per_million,
                "received_weighted_avg_year_per_million": received_weighted_avg_year_per_million,
                "interest_rate_salary_adjusted": interest_rate_salary_adjusted,
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build intermediate JSON: trade WAR by year (raw and salary-adjusted) for each player until retirement or FA."
    )
    parser.add_argument(
        "--trades",
        type=Path,
        default=Path("trades.json"),
        help="Path to trades JSON",
    )
    parser.add_argument(
        "--player-war",
        type=Path,
        default=Path("player_war.json"),
        help="Path to player WAR JSON",
    )
    parser.add_argument(
        "--war-value-by-year",
        type=Path,
        default=Path("war_value_by_year.json"),
        help="Path to war_value_by_year.json (output of extract_war_value_by_year)",
    )
    parser.add_argument(
        "--player-transactions",
        type=Path,
        default=Path("player_transactions.json"),
        help="Path to player transactions JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("trade_war_by_year.json"),
        help="Output JSON file path",
    )
    args = parser.parse_args()

    trades = load_trades(args.trades)
    war_by_player = load_player_war(args.player_war)
    war_per_million_by_player_year = load_war_value_by_year(args.war_value_by_year)
    free_agency_by_player = load_free_agency_dates(args.player_transactions)
    rows = build_trade_war_rows(
        trades,
        war_by_player,
        war_per_million_by_player_year,
        free_agency_by_player,
    )

    args.output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} trade WAR-by-year rows to {args.output}")


if __name__ == "__main__":
    main()

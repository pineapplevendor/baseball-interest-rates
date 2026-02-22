#!/usr/bin/env python3
"""Download Baseball-Reference player pages for all players in trades.json."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, List, Set


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def load_unique_player_ids(trades_file: Path) -> List[str]:
    data = json.loads(trades_file.read_text(encoding="utf-8"))
    unique_ids: Set[str] = set()

    for trade in data:
        unique_ids.update(trade.get("from_player_ids", []))
        unique_ids.update(trade.get("to_player_ids", []))

    # Keep deterministic ordering for stable runs/logging.
    return sorted(pid for pid in unique_ids if isinstance(pid, str) and pid)


def player_url(player_id: str) -> str:
    first_letter = player_id[0].lower()
    return f"https://www.baseball-reference.com/players/{first_letter}/{player_id}.shtml"


def fetch_with_retries(url: str, timeout: int, retries: int) -> bytes:
    last_error: Exception | None = None
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as err:
            last_error = err
            if attempt < retries:
                time.sleep(1.5 * attempt)

    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def download_pages(
    player_ids: Iterable[str],
    output_dir: Path,
    overwrite: bool,
    timeout: int,
    retries: int,
    delay: float,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    skipped = 0
    failed = 0

    for idx, player_id in enumerate(player_ids, start=1):
        url = player_url(player_id)
        output_file = output_dir / f"{player_id}.html"

        if output_file.exists() and not overwrite:
            skipped += 1
            print(f"[{idx}] SKIP  {player_id} (already exists)")
            continue

        try:
            content = fetch_with_retries(url, timeout=timeout, retries=retries)
            output_file.write_bytes(content)
            downloaded += 1
            print(f"[{idx}] OK    {player_id} -> {output_file}")
        except Exception as err:  # noqa: BLE001 - keep run alive per player
            failed += 1
            print(f"[{idx}] FAIL  {player_id}: {err}")

        if delay > 0:
            time.sleep(delay)

    print(
        f"\nDone. Downloaded: {downloaded}, Skipped: {skipped}, "
        f"Failed: {failed}, Total: {downloaded + skipped + failed}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download Baseball-Reference player pages for players in trades.json."
    )
    parser.add_argument(
        "--trades",
        type=Path,
        default=Path("trades.json"),
        help="Path to trades JSON file (default: trades.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("players"),
        help="Directory where player HTML files are stored (default: players)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download pages even if output file already exists",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=25,
        help="HTTP timeout in seconds (default: 25)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Number of retries per player (default: 3)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=10,
        help="Delay in seconds between requests (default: 10)",
    )
    args = parser.parse_args()

    player_ids = load_unique_player_ids(args.trades)
    print(f"Found {len(player_ids)} unique players in {args.trades}")
    download_pages(
        player_ids=player_ids,
        output_dir=args.output_dir,
        overwrite=args.overwrite,
        timeout=args.timeout,
        retries=args.retries,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()



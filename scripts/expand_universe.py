#!/usr/bin/env python3
"""Add TSE listings to universe.json from 4-digit tickers. Not CI. No public/data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from providers.errors import FetchError  # noqa: E402
from providers.tse import listing_row, merge_listings, parse_tse_ticker  # noqa: E402

UNIVERSE_PATH = ROOT / "scripts" / "providers" / "universe.json"
TOPIX_CORE30_PATH = ROOT / "scripts" / "providers" / "topix_core30.json"
SOURCE_FILES = {
    "topix-core30": TOPIX_CORE30_PATH,
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def stocks_from_source_file(path: Path) -> list[dict[str, str]]:
    payload = load_json(path)
    rows = payload.get("stocks") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise FetchError(f"source list is empty: {path}")
    listings: list[dict[str, str]] = []
    for item in rows:
        if not isinstance(item, dict):
            raise FetchError(f"source row is invalid in {path}")
        listings.append(listing_row(str(item.get("ticker") or ""), str(item.get("companyName") or "")))
    return listings


def stocks_from_tickers(tickers: list[str], names: list[str]) -> list[dict[str, str]]:
    wanted = [parse_tse_ticker(raw) for raw in tickers if raw.strip()]
    if not wanted:
        return []
    name_by_ticker: dict[str, str] = {}
    for raw in names:
        if "=" not in raw:
            raise FetchError("pass names as --name 7974=Nintendo")
        ticker, name = raw.split("=", 1)
        name_by_ticker[parse_tse_ticker(ticker)] = name.strip()
    listings: list[dict[str, str]] = []
    missing: list[str] = []
    for ticker in wanted:
        name = name_by_ticker.get(ticker)
        if not name:
            missing.append(ticker)
            continue
        listings.append(listing_row(ticker, name))
    if missing:
        raise FetchError("company name missing for " + ", ".join(missing) + " (use --name TICKER=Name)")
    return listings


def expand_universe(
    universe: dict[str, Any],
    incoming: list[dict[str, str]],
    *,
    keep_existing: bool = True,
) -> tuple[dict[str, Any], list[str]]:
    stocks, added = merge_listings(
        list(universe.get("stocks") or []),
        incoming,
        keep_existing=keep_existing,
    )
    updated = dict(universe)
    updated["stocks"] = stocks
    return updated, added


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Add TSE names to universe.json from 4-digit tickers or a recorded list. "
            "Derives Yahoo / J-Quants / EDINET codes. Does not fetch. Does not write public/data."
        )
    )
    parser.add_argument(
        "--from",
        dest="source",
        choices=sorted(SOURCE_FILES),
        help="Recorded constituent list. Not a live index crawl.",
    )
    parser.add_argument(
        "--from-file",
        type=Path,
        help="JSON with stocks[].ticker and stocks[].companyName",
    )
    parser.add_argument(
        "--ticker",
        action="append",
        default=[],
        metavar="XXXX",
        help="4-digit TSE ticker. Repeat. Requires --name TICKER=Name",
    )
    parser.add_argument(
        "--name",
        action="append",
        default=[],
        metavar="XXXX=Name",
        help="Company name for a --ticker. Repeat.",
    )
    parser.add_argument("--universe", default=str(UNIVERSE_PATH))
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        default=True,
        help="Do not overwrite names already in universe.json (default)",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Overwrite existing universe rows for the same ticker",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    keep_existing = not args.replace_existing

    incoming: list[dict[str, str]] = []
    try:
        if args.source:
            incoming.extend(stocks_from_source_file(SOURCE_FILES[args.source]))
        if args.from_file:
            incoming.extend(stocks_from_source_file(args.from_file))
        incoming.extend(stocks_from_tickers(args.ticker, args.name))
        if not incoming:
            raise FetchError("pass --from topix-core30, --from-file, or --ticker")
        universe_path = Path(args.universe)
        universe = load_json(universe_path)
        updated, added = expand_universe(universe, incoming, keep_existing=keep_existing)
    except (OSError, json.JSONDecodeError, KeyError, FetchError) as exc:
        print(f"FAIL {exc}")
        return 1

    print(f"universe names {len(universe.get('stocks') or [])} -> {len(updated['stocks'])}")
    if added:
        print("added " + ", ".join(added))
    else:
        print("added none")
    if args.dry_run:
        print("dry-run; not writing universe.json or public/data")
        return 0
    universe_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {universe_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

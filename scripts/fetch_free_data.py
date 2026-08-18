#!/usr/bin/env python3
"""Download free Yahoo chart + fundamentals JSON. Not used by CI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from providers.errors import FetchError  # noqa: E402
from providers.http import (  # noqa: E402
    cache_filename,
    fetch_yahoo_chart_json,
    fetch_yahoo_fundamentals_json,
)
from providers.loader import load_universe  # noqa: E402


def _log_path(prefix: str, path: Path) -> None:
    try:
        print(f"{prefix} {path.relative_to(ROOT)}")
    except ValueError:
        print(f"{prefix} {path}")


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    _log_path("wrote", path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch free Yahoo chart and fundamentals JSON.")
    parser.add_argument("--out", default=str(ROOT / "data" / "raw" / "yahoo"))
    parser.add_argument(
        "--fundamentals-out",
        default=str(ROOT / "data" / "raw" / "yahoo_fundamentals"),
    )
    parser.add_argument("--universe", default=str(ROOT / "scripts" / "providers" / "universe.json"))
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip symbols that already have a cache file. Does not invent missing names.",
    )
    args = parser.parse_args()

    universe = load_universe(Path(args.universe))
    chart_dir = Path(args.out)
    fund_dir = Path(args.fundamentals_out)
    range_ = str(universe.get("range", "1y"))
    chart_symbols = [universe["marketSymbol"]] + [item["yahooSymbol"] for item in universe["stocks"]]
    fund_symbols = [item["yahooSymbol"] for item in universe["stocks"]]

    failed = 0
    for symbol in chart_symbols:
        path = chart_dir / cache_filename(str(symbol))
        if args.skip_existing and path.exists():
            _log_path("skip", path)
            continue
        try:
            payload = fetch_yahoo_chart_json(str(symbol), range_=range_)
        except FetchError as exc:
            print(f"FAIL chart {symbol}: {exc}")
            failed += 1
            continue
        _write(path, payload)

    for symbol in fund_symbols:
        path = fund_dir / cache_filename(str(symbol))
        if args.skip_existing and path.exists():
            _log_path("skip", path)
            continue
        try:
            payload = fetch_yahoo_fundamentals_json(str(symbol))
        except FetchError as exc:
            print(f"FAIL fundamentals {symbol}: {exc}")
            failed += 1
            continue
        _write(path, payload)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

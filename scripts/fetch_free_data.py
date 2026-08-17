#!/usr/bin/env python3
"""Download free Yahoo chart JSON into data/raw/yahoo. Not used by CI."""

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
from providers.http import cache_filename, fetch_yahoo_chart_json  # noqa: E402
from providers.loader import load_universe  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch free Yahoo chart JSON (no API key).")
    parser.add_argument("--out", default=str(ROOT / "data" / "raw" / "yahoo"))
    parser.add_argument("--universe", default=str(ROOT / "scripts" / "providers" / "universe.json"))
    args = parser.parse_args()

    universe = load_universe(Path(args.universe))
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    range_ = str(universe.get("range", "1y"))
    symbols = [universe["marketSymbol"]] + [item["yahooSymbol"] for item in universe["stocks"]]

    failed = 0
    for symbol in symbols:
        path = out_dir / cache_filename(str(symbol))
        try:
            payload = fetch_yahoo_chart_json(str(symbol), range_=range_)
        except FetchError as exc:
            print(f"FAIL {symbol}: {exc}")
            failed += 1
            continue
        path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

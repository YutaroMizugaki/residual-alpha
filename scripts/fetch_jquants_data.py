#!/usr/bin/env python3
"""Download J-Quants FY summaries and daily bars. Needs JQUANTS_API_KEY. Not CI."""

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
    fetch_jquants_bars_json,
    fetch_jquants_summary_json,
    jquants_bars_window,
)
from providers.loader import jquants_code, load_universe  # noqa: E402


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        print(f"wrote {path.relative_to(ROOT)}")
    except ValueError:
        print(f"wrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch J-Quants v2 /fins/summary and /equities/bars/daily JSON."
    )
    parser.add_argument("--out", default=str(ROOT / "data" / "raw" / "jquants"))
    parser.add_argument("--bars-out", default=str(ROOT / "data" / "raw" / "jquants_bars"))
    parser.add_argument("--universe", default=str(ROOT / "scripts" / "providers" / "universe.json"))
    args = parser.parse_args()

    universe = load_universe(Path(args.universe))
    out_dir = Path(args.out)
    bars_dir = Path(args.bars_out)
    from_, to = jquants_bars_window(str(universe.get("range", "1y")))
    failed = 0
    for item in universe["stocks"]:
        code = jquants_code(item)
        try:
            payload = fetch_jquants_summary_json(code)
        except FetchError as exc:
            print(f"FAIL summary {code}: {exc}")
            failed += 1
        else:
            _write(out_dir / cache_filename(code), payload)
        try:
            bars = fetch_jquants_bars_json(code, from_=from_, to=to)
        except FetchError as exc:
            print(f"FAIL bars {code}: {exc}")
            failed += 1
        else:
            _write(bars_dir / cache_filename(code), bars)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

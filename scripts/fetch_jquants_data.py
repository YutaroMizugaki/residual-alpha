#!/usr/bin/env python3
"""Download J-Quants FY summaries. Needs JQUANTS_API_KEY. Not used by CI."""

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
from providers.http import cache_filename, fetch_jquants_summary_json  # noqa: E402
from providers.loader import jquants_code, load_universe  # noqa: E402


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        print(f"wrote {path.relative_to(ROOT)}")
    except ValueError:
        print(f"wrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch J-Quants v2 /fins/summary JSON.")
    parser.add_argument("--out", default=str(ROOT / "data" / "raw" / "jquants"))
    parser.add_argument("--universe", default=str(ROOT / "scripts" / "providers" / "universe.json"))
    args = parser.parse_args()

    universe = load_universe(Path(args.universe))
    out_dir = Path(args.out)
    failed = 0
    for item in universe["stocks"]:
        code = jquants_code(item)
        try:
            payload = fetch_jquants_summary_json(code)
        except FetchError as exc:
            print(f"FAIL {code}: {exc}")
            failed += 1
            continue
        _write(out_dir / cache_filename(code), payload)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

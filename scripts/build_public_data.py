#!/usr/bin/env python3
"""Build deterministic static JSON for the Next.js UI. Computation lives only here."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from models.pipeline import detail_row, evaluate_universe, ranking_row  # noqa: E402
from providers.loader import load_fixture_snapshot, load_free_snapshot  # noqa: E402

PUBLIC_DATA = ROOT / "public" / "data"
RANKINGS_PATH = PUBLIC_DATA / "rankings.json"
STOCKS_DIR = PUBLIC_DATA / "stocks"
META_PATH = PUBLIC_DATA / "meta.json"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=("fixture", "free"), default="fixture")
    parser.add_argument("--raw-dir", default=str(ROOT / "data" / "raw" / "yahoo"))
    parser.add_argument(
        "--fundamentals-dir",
        default=str(ROOT / "data" / "raw" / "yahoo_fundamentals"),
    )
    parser.add_argument("--fetch", action="store_true", help="free source only: download Yahoo JSON")
    args = parser.parse_args()

    if args.source == "fixture":
        snapshot = load_fixture_snapshot()
    else:
        snapshot = load_free_snapshot(
            raw_dir=Path(args.raw_dir),
            fundamentals_dir=Path(args.fundamentals_dir),
            fetch=args.fetch,
        )

    computed = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    rankings = [ranking_row(row) for row in computed]
    rankings.sort(
        key=lambda row: (
            row["rank"] is None,
            row["rank"] if row["rank"] is not None else 10**9,
            row["ticker"],
        )
    )
    write_json(RANKINGS_PATH, rankings)
    write_json(META_PATH, snapshot.meta())

    STOCKS_DIR.mkdir(parents=True, exist_ok=True)
    for path in STOCKS_DIR.glob("*.json"):
        path.unlink()
    for row in computed:
        write_json(STOCKS_DIR / f"{row['ticker']}.json", detail_row(row))

    print(f"source={snapshot.source}")
    print(f"wrote {RANKINGS_PATH.relative_to(ROOT)}")
    print(f"wrote {META_PATH.relative_to(ROOT)}")
    print(f"wrote {len(computed)} stock JSON files under {STOCKS_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

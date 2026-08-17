#!/usr/bin/env python3
"""Download EDINET v2 document lists. Needs EDINET_API_KEY. Not used by CI."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from providers.errors import FetchError  # noqa: E402
from providers.http import Fetcher, fetch_edinet_documents_json  # noqa: E402


def unique_dates(dates: list[str]) -> list[str]:
    seen: list[str] = []
    for raw in dates:
        day = raw.strip()
        if not day or day in seen:
            continue
        seen.append(day)
    return seen


def parse_filing_date(raw: str) -> str:
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise FetchError(f"EDINET filing date is invalid: {raw}") from exc


def fetch_edinet_lists(
    dates: list[str],
    out_dir: Path,
    *,
    fetcher: Fetcher | None = None,
) -> int:
    """Fetch operator-supplied filing dates only. Does not crawl a range."""
    wanted = unique_dates(dates)
    if not wanted:
        print("FAIL no EDINET filing dates")
        return 1
    failed = 0
    out_dir.mkdir(parents=True, exist_ok=True)
    for raw in wanted:
        try:
            day = parse_filing_date(raw)
            payload = fetch_edinet_documents_json(day, fetcher=fetcher)
        except FetchError as exc:
            print(f"FAIL {raw}: {exc}")
            failed += 1
            continue
        path = out_dir / f"{day}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            print(f"wrote {path.relative_to(ROOT)}")
        except ValueError:
            print(f"wrote {path}")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch EDINET v2 documents.json for operator-supplied filing dates. Not a range crawl."
    )
    parser.add_argument(
        "--date",
        required=True,
        action="append",
        metavar="YYYY-MM-DD",
        help="Filing date. Repeat for multiple days. Does not crawl a range.",
    )
    parser.add_argument("--out", default=str(ROOT / "data" / "raw" / "edinet"))
    args = parser.parse_args()
    return fetch_edinet_lists(args.date, Path(args.out))


if __name__ == "__main__":
    raise SystemExit(main())

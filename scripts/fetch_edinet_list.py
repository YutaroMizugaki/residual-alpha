#!/usr/bin/env python3
"""Download EDINET v2 document lists. Needs EDINET_API_KEY. Not used by CI."""

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
from providers.http import fetch_edinet_documents_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch EDINET v2 documents.json for one date.")
    parser.add_argument("--date", required=True, help="Filing date YYYY-MM-DD")
    parser.add_argument("--out", default=str(ROOT / "data" / "raw" / "edinet"))
    args = parser.parse_args()

    try:
        payload = fetch_edinet_documents_json(args.date)
    except FetchError as exc:
        print(f"FAIL {args.date}: {exc}")
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.date}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

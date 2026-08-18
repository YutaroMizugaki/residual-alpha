#!/usr/bin/env python3
"""Download EDINET yuho XBRL zips. Needs EDINET_API_KEY. Not used by CI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from providers.edinet import parse_edinet_documents, yuho_history  # noqa: E402
from providers.errors import FetchError  # noqa: E402
from providers.http import fetch_edinet_xbrl_zip  # noqa: E402
from providers.loader import edinet_code, edinet_sec_code, load_universe  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch EDINET type=1 XBRL zips for yuho filings.")
    parser.add_argument("--out", default=str(ROOT / "data" / "raw" / "edinet_xbrl"))
    parser.add_argument("--list-dir", default=str(ROOT / "data" / "raw" / "edinet"))
    parser.add_argument("--universe", default=str(ROOT / "scripts" / "providers" / "universe.json"))
    parser.add_argument("--doc-id", help="Download one document id")
    parser.add_argument("--sec-code", help="Required with --doc-id")
    args = parser.parse_args()

    out_root = Path(args.out)
    failed = 0

    if args.doc_id:
        if not args.sec_code:
            print("FAIL --sec-code is required with --doc-id")
            return 1
        try:
            payload = fetch_edinet_xbrl_zip(args.doc_id)
        except FetchError as exc:
            print(f"FAIL {args.doc_id}: {exc}")
            return 1
        dest = out_root / args.sec_code
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"{args.doc_id}.zip"
        path.write_bytes(payload)
        print(f"wrote {path.relative_to(ROOT)}")
        return 0

    universe = load_universe(Path(args.universe))
    list_dir = Path(args.list_dir)
    documents = []
    if list_dir.exists():
        for path in sorted(list_dir.glob("*.json")):
            try:
                documents.extend(parse_edinet_documents(json.loads(path.read_text(encoding="utf-8"))))
            except FetchError as exc:
                print(f"FAIL list {path.name}: {exc}")
                failed += 1

    if not documents:
        print("FAIL no EDINET document lists found; run fetch_edinet_list.py first")
        return 1

    for item in sorted(universe["stocks"], key=lambda row: edinet_sec_code(row)):
        code = edinet_sec_code(item)
        for doc in yuho_history(documents, code, edinet_code=edinet_code(item)):
            dest = out_root / code
            dest.mkdir(parents=True, exist_ok=True)
            path = dest / f"{doc.doc_id}.zip"
            if path.exists():
                print(f"skip {path.relative_to(ROOT)}")
                continue
            try:
                payload = fetch_edinet_xbrl_zip(doc.doc_id)
            except FetchError as exc:
                print(f"FAIL {doc.doc_id}: {exc}")
                failed += 1
                continue
            path.write_bytes(payload)
            print(f"wrote {path.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

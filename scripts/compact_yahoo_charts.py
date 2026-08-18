#!/usr/bin/env python3
"""Compact Yahoo chart JSON into recorded-test form. Not used by CI. No fetch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from providers.errors import ProviderError  # noqa: E402
from providers.http import cache_filename  # noqa: E402
from providers.loader import load_universe  # noqa: E402
from providers.yahoo_chart import compact_yahoo_charts  # noqa: E402


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    try:
        print(f"wrote {path.relative_to(ROOT)}")
    except ValueError:
        print(f"wrote {path}")


def chart_symbols(universe: dict) -> list[str]:
    market = str(universe["marketSymbol"])
    return [market] + [str(item["yahooSymbol"]) for item in universe["stocks"]]


def compact_chart_dir(
    src: Path,
    dst: Path,
    *,
    universe: dict,
    align: bool = False,
    dry_run: bool = False,
    existing_only: bool = False,
    keep_existing: bool = False,
) -> int:
    """Compact universe charts only. Does not touch public/data or live fetch."""
    payloads: dict[str, dict] = {}
    failed = 0
    skipped_existing = 0
    for symbol in chart_symbols(universe):
        name = cache_filename(symbol)
        out = dst / name
        if keep_existing and out.exists():
            print(f"SKIP existing {name}")
            skipped_existing += 1
            continue
        path = src / name
        if not path.exists():
            if existing_only:
                print(f"SKIP missing {path}")
                continue
            print(f"FAIL missing {path}")
            failed += 1
            continue
        try:
            payloads[name] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"FAIL {name}: {exc}")
            failed += 1
    if failed:
        return 1
    if not payloads:
        if skipped_existing:
            print("OK destination caches already exist")
            return 0
        print("FAIL no universe Yahoo charts to compact")
        return 1
    try:
        compacted = compact_yahoo_charts(payloads, align=align)
    except ProviderError as exc:
        print(f"FAIL compact: {exc}")
        return 1
    for name, payload in compacted.items():
        out = dst / name
        if dry_run:
            n = len(payload["chart"]["result"][0]["timestamp"])
            print(f"would write {out} ({n} closes)")
            continue
        _write(out, payload)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compact Yahoo chart JSON (timestamp + close). Not CI. No network."
    )
    parser.add_argument("--src", default=str(ROOT / "data" / "raw" / "yahoo"))
    parser.add_argument(
        "--dst",
        default=None,
        help="Output directory (default: same as --src). Does not write public/data.",
    )
    parser.add_argument("--universe", default=str(ROOT / "scripts" / "providers" / "universe.json"))
    parser.add_argument(
        "--align",
        action="store_true",
        help="Inner-join valid timestamps across market + universe names. Do not fill 0.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--existing-only",
        action="store_true",
        help="Skip universe names with no cache instead of failing. Does not invent missing names.",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Do not overwrite destination chart JSON that already exists.",
    )
    args = parser.parse_args()
    try:
        universe = load_universe(Path(args.universe))
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"FAIL universe: {exc}")
        return 1
    dst = Path(args.dst) if args.dst else Path(args.src)
    return compact_chart_dir(
        Path(args.src),
        dst,
        universe=universe,
        align=args.align,
        dry_run=args.dry_run,
        existing_only=args.existing_only,
        keep_existing=args.keep_existing,
    )


if __name__ == "__main__":
    raise SystemExit(main())

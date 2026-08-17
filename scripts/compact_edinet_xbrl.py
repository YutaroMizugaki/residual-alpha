#!/usr/bin/env python3
"""Compact EDINET yuho XBRL into recorded-test instance XML. Not used by CI. No fetch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from providers.edinet_xbrl import compact_edinet_xbrl_dir, parse_edinet_instance_xml  # noqa: E402
from providers.errors import ProviderError  # noqa: E402
from providers.loader import edinet_sec_code, load_universe  # noqa: E402


def _write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    try:
        print(f"wrote {path.relative_to(ROOT)}")
    except ValueError:
        print(f"wrote {path}")


def universe_codes(universe: dict) -> list[str]:
    return [edinet_sec_code(item) for item in universe["stocks"]]


def dest_instance(path: Path) -> Path:
    return path / "instance.xbrl"


def compact_edinet_universe(
    src: Path,
    dst: Path,
    *,
    universe: dict,
    dry_run: bool = False,
    existing_only: bool = False,
    keep_existing: bool = False,
) -> int:
    """Compact universe EDINET caches only. Does not touch public/data or live fetch."""
    pending: list[tuple[str, str]] = []
    failed = 0
    skipped_existing = 0
    for code in universe_codes(universe):
        out = dest_instance(dst / code)
        if keep_existing and out.exists():
            print(f"SKIP existing {code}/instance.xbrl")
            skipped_existing += 1
            continue
        source = src / code
        if not source.exists():
            if existing_only:
                print(f"SKIP missing {source}")
                continue
            print(f"FAIL missing {source}")
            failed += 1
            continue
        try:
            xml = compact_edinet_xbrl_dir(source)
            parse_edinet_instance_xml(xml)
        except ProviderError as exc:
            print(f"FAIL {code}: {exc}")
            failed += 1
            continue
        pending.append((code, xml))
    if failed:
        return 1
    if not pending:
        if skipped_existing:
            print("OK destination caches already exist")
            return 0
        print("FAIL no universe EDINET caches to compact")
        return 1
    for code, xml in pending:
        out = dest_instance(dst / code)
        if dry_run:
            print(f"would write {out} ({len(xml.splitlines())} lines)")
            continue
        _write(out, xml)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compact EDINET yuho XBRL to instance facts. Not CI. No network."
    )
    parser.add_argument("--src", default=str(ROOT / "data" / "raw" / "edinet_xbrl"))
    parser.add_argument(
        "--dst",
        default=None,
        help="Output directory (default: same as --src). Not public/data.",
    )
    parser.add_argument("--universe", default=str(ROOT / "scripts" / "providers" / "universe.json"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--existing-only",
        action="store_true",
        help="Skip universe names with no cache instead of failing. Does not invent missing names.",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help=(
            "Do not overwrite destination instance.xbrl files that already exist. "
            "Keeps recorded 7203/6758/9984 fixtures when adding other universe names."
        ),
    )
    args = parser.parse_args()
    try:
        universe = load_universe(Path(args.universe))
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"FAIL universe: {exc}")
        return 1
    src = Path(args.src)
    dst = Path(args.dst) if args.dst else src
    return compact_edinet_universe(
        src,
        dst,
        universe=universe,
        dry_run=args.dry_run,
        existing_only=args.existing_only,
        keep_existing=args.keep_existing,
    )


if __name__ == "__main__":
    raise SystemExit(main())

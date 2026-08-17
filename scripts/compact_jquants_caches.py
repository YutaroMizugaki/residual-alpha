#!/usr/bin/env python3
"""Compact J-Quants FY + AdjC JSON into recorded-test form. Not used by CI. No fetch."""

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
from providers.jquants_bars import compact_jquants_bars  # noqa: E402
from providers.jquants_summary import compact_jquants_summary  # noqa: E402
from providers.loader import jquants_code, load_universe  # noqa: E402


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


def universe_codes(universe: dict) -> list[str]:
    return [jquants_code(item) for item in universe["stocks"]]


def compact_jquants_dir(
    summaries_src: Path,
    bars_src: Path,
    summaries_dst: Path,
    bars_dst: Path,
    *,
    universe: dict,
    dry_run: bool = False,
) -> int:
    """Compact universe J-Quants caches only. Does not touch public/data or live fetch."""
    pending: list[tuple[str, dict, dict]] = []
    failed = 0
    for code in universe_codes(universe):
        name = cache_filename(code)
        summary_path = summaries_src / name
        bars_path = bars_src / name
        if not summary_path.exists():
            print(f"FAIL missing {summary_path}")
            failed += 1
            continue
        if not bars_path.exists():
            print(f"FAIL missing {bars_path}")
            failed += 1
            continue
        try:
            summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
            bars_payload = json.loads(bars_path.read_text(encoding="utf-8"))
            summary = compact_jquants_summary(summary_payload, expected_code=code)
            bars = compact_jquants_bars(bars_payload, expected_code=code)
        except (json.JSONDecodeError, ProviderError) as exc:
            print(f"FAIL {name}: {exc}")
            failed += 1
            continue
        pending.append((name, summary, bars))
    if failed:
        return 1
    for name, summary, bars in pending:
        summary_out = summaries_dst / name
        bars_out = bars_dst / name
        if dry_run:
            print(
                f"would write {summary_out} ({len(summary['data'])} FY rows) "
                f"and {bars_out} ({len(bars['data'])} AdjC)"
            )
            continue
        _write(summary_out, summary)
        _write(bars_out, bars)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compact J-Quants FY summaries and AdjC bars. Not CI. No network."
    )
    parser.add_argument(
        "--src-summaries",
        default=str(ROOT / "data" / "raw" / "jquants"),
    )
    parser.add_argument(
        "--src-bars",
        default=str(ROOT / "data" / "raw" / "jquants_bars"),
    )
    parser.add_argument(
        "--dst-summaries",
        default=None,
        help="Summary output directory (default: same as --src-summaries). Not public/data.",
    )
    parser.add_argument(
        "--dst-bars",
        default=None,
        help="Bars output directory (default: same as --src-bars). Not public/data.",
    )
    parser.add_argument("--universe", default=str(ROOT / "scripts" / "providers" / "universe.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        universe = load_universe(Path(args.universe))
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"FAIL universe: {exc}")
        return 1
    summaries_src = Path(args.src_summaries)
    bars_src = Path(args.src_bars)
    summaries_dst = Path(args.dst_summaries) if args.dst_summaries else summaries_src
    bars_dst = Path(args.dst_bars) if args.dst_bars else bars_src
    return compact_jquants_dir(
        summaries_src,
        bars_src,
        summaries_dst,
        bars_dst,
        universe=universe,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())

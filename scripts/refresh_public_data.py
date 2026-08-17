#!/usr/bin/env python3
"""Operator refresh: fetch caches then rebuild public JSON. Not used by CI. No cron."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def fetch_plan(env: dict[str, str] | None = None, *, source: str = "auto") -> list[str]:
    """Yahoo prices always. Keyed scripts only for sources that use them, and only with keys."""
    environ = env if env is not None else os.environ
    plan = ["fetch_free_data.py"]
    if source in {"auto", "jquants"} and (environ.get("JQUANTS_API_KEY") or "").strip():
        plan.append("fetch_jquants_data.py")
    if source in {"auto", "edinet"} and (environ.get("EDINET_API_KEY") or "").strip():
        plan.append("fetch_edinet_xbrl.py")
    return plan


def _run(script: str, extra: list[str]) -> int:
    command = [sys.executable, str(SCRIPTS / script), *extra]
    print("+", " ".join(command))
    return subprocess.call(command)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch optional provider caches and rebuild public/data. Not CI."
    )
    parser.add_argument("--source", default="auto", choices=("auto", "free", "jquants", "edinet"))
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    plan = [] if args.skip_fetch else fetch_plan(source=args.source)
    if args.dry_run:
        for script in plan:
            print(f"would run {script}")
        if not args.skip_build:
            print(f"would run build_public_data.py --source {args.source}")
        return 0

    failed = 0
    for script in plan:
        code = _run(script, [])
        if code != 0:
            print(f"WARN {script} exited {code}")
            failed += 1
    if not args.skip_build:
        build_code = _run("build_public_data.py", ["--source", args.source])
        if build_code != 0:
            return build_code
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

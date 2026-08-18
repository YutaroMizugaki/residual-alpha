"""Committed site JSON is recorded --source auto, not a live fetch."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from build_public_data import recorded_cache_dirs
from models.pipeline import detail_row, evaluate_universe, ranking_row
from providers.loader import load_auto_snapshot, load_universe

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts" / "build_public_data.py"
RANKINGS_PATH = ROOT / "public" / "data" / "rankings.json"
STOCKS_DIR = ROOT / "public" / "data" / "stocks"
META_PATH = ROOT / "public" / "data" / "meta.json"
UNIVERSE_PATH = ROOT / "scripts" / "providers" / "universe.json"
EDINET_TEN = {
    "7203",
    "6758",
    "9984",
    "6861",
    "6501",
    "8035",
    "4063",
    "8306",
    "9432",
    "6098",
}
EDINET_COMPLETE = EDINET_TEN | {
    "4568",
    "6503",
    "6857",
    "7267",
    "7974",
    "8001",
    "8058",
    "8316",
    "8766",
    "9434",
    "9983",
    "3382",
    "2914",
    "8729",
    "4502",
    "6367",
    "7011",
    "8031",
    "8411",
    "9433",
    "7741",
}


def _recorded_snapshot():
    return load_auto_snapshot(**recorded_cache_dirs())


def test_recorded_flag_rejects_fixture():
    result = subprocess.run(
        [sys.executable, str(BUILD), "--recorded"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "FAIL --recorded is not used with --source fixture" in result.stderr
    assert result.stdout == ""


def test_recorded_flag_does_not_fetch():
    result = subprocess.run(
        [sys.executable, str(BUILD), "--source", "auto", "--recorded", "--fetch"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "FAIL --recorded does not fetch" in result.stderr


def test_public_json_matches_recorded_auto_engine():
    snapshot = _recorded_snapshot()
    universe = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    expected = [ranking_row(row) for row in universe]
    expected.sort(
        key=lambda row: (
            row["rank"] is None,
            row["rank"] if row["rank"] is not None else 10**9,
            row["ticker"],
        )
    )
    public_rankings = json.loads(RANKINGS_PATH.read_text(encoding="utf-8"))
    assert public_rankings == expected
    listed = [str(item["ticker"]) for item in load_universe(UNIVERSE_PATH)["stocks"]]
    assert [row["ticker"] for row in public_rankings] == [row["ticker"] for row in expected]
    assert {row["ticker"] for row in public_rankings} == set(listed)
    assert EDINET_COMPLETE <= set(listed)
    assert "7974" in listed
    for row in public_rankings:
        assert row["ticker"] not in {"1001", "1002", "1003", "1004", "1005", "1006"}
        assert row["priceSource"] == "yahoo_chart"
        assert row["priceAsOf"] is not None
        assert row["fundamentalsAsOf"] is not None
        assert row["returnCount"] is not None
        assert row["eligible"] is True
        assert row["returnCount"] >= 199
        assert row["roeCount"] >= 3
        if row["ticker"] in EDINET_COMPLETE:
            assert row["fundamentalsSource"] == "edinet_xbrl"
        else:
            assert row["fundamentalsSource"] == "yahoo_timeseries"

    for row in universe:
        public_detail = json.loads((STOCKS_DIR / f"{row['ticker']}.json").read_text(encoding="utf-8"))
        assert public_detail == detail_row(row)
        assert public_detail["priceSource"] == "yahoo_chart"

    leftover = sorted(path.name for path in STOCKS_DIR.glob("*.json"))
    assert leftover == sorted(f"{ticker}.json" for ticker in listed)

    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    assert meta == snapshot.meta()
    assert meta["source"] == "auto"
    assert meta["priceSource"] == "yahoo_chart"
    assert meta["fundamentalsSource"] == "edinet_xbrl"
    assert meta["priceLagNote"] is None
    assert "Not investment advice" in meta["disclaimerEn"]

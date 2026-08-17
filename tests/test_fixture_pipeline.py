"""End-to-end checks against the committed fictional fixture."""

from __future__ import annotations

import json
from pathlib import Path

from models.pipeline import detail_row, evaluate_universe, ranking_row

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "scripts" / "fixtures" / "stocks.json"
RANKINGS_PATH = ROOT / "public" / "data" / "rankings.json"
STOCKS_DIR = ROOT / "public" / "data" / "stocks"

RANKING_FIELDS = [
    "rank",
    "ticker",
    "companyName",
    "price",
    "intrinsicPrice",
    "intrinsicUpside",
    "betaAdjusted",
    "costOfEquity",
    "normalizedRoe",
    "excessRoe",
    "valuationScore",
    "qualityScore",
    "riskScore",
    "totalScore",
]


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _universe() -> list[dict]:
    fixtures = _load_fixture()
    return evaluate_universe(fixtures["stocks"], fixtures["assumptions"])


def test_fixture_has_six_fictional_issuers():
    fixtures = _load_fixture()
    tickers = [stock["ticker"] for stock in fixtures["stocks"]]
    assert tickers == ["1001", "1002", "1003", "1004", "1005", "1006"]
    names = [stock["companyName"] for stock in fixtures["stocks"]]
    assert "Alpha Manufacturing" in names
    assert "Missing Data" in names


def test_fixture_year_10_roe_equals_cost_of_equity():
    for row in _universe():
        if not row["eligible"]:
            continue
        forecast = row["forecast"]
        assert len(forecast) == 10
        assert forecast[0]["year"] == 1
        assert forecast[9]["year"] == 10
        assert forecast[9]["roe"] == row["costOfEquity"]
        assert forecast[0]["discountFactor"] != 1.0


def test_fixture_missing_data_not_zero():
    by_ticker = {row["ticker"]: row for row in _universe()}
    missing = by_ticker["1006"]
    assert missing["eligible"] is False
    assert missing["bookValue"] is None
    assert missing["intrinsicEquityValue"] is None
    assert missing["betaRaw"] is None
    assert missing["normalizedRoe"] is None
    assert missing["totalScore"] is None
    assert "missing_book_value" in missing["exclusionReasons"]
    assert 0 not in (
        missing["bookValue"],
        missing["intrinsicEquityValue"],
        missing["betaRaw"],
        missing["normalizedRoe"],
        missing["totalScore"],
    )


def test_fixture_stable_industries_intrinsic_equals_book():
    by_ticker = {row["ticker"]: row for row in _universe()}
    stable = by_ticker["1002"]
    assert stable["bookValue"] == 100000
    assert stable["sharesOutstanding"] == 100
    assert stable["intrinsicEquityValue"] == stable["bookValue"]
    assert stable["intrinsicPrice"] == 1000
    assert stable["intrinsicUpside"] == 0
    for year in stable["forecast"]:
        assert year["residualIncome"] == 0


def test_fixture_high_beta_not_top_ranked():
    ranked = [row for row in _universe() if row["rank"] is not None]
    ranked.sort(key=lambda row: row["rank"])
    assert ranked[0]["ticker"] != "1004"
    high_beta = next(row for row in ranked if row["ticker"] == "1004")
    low_beta = next(row for row in ranked if row["ticker"] == "1001")
    assert high_beta["betaAdjusted"] > low_beta["betaAdjusted"]
    assert high_beta["riskScore"] < low_beta["riskScore"]
    assert high_beta["totalScore"] < low_beta["totalScore"]


def test_public_json_matches_engine_and_schema():
    universe = _universe()
    public_rankings = json.loads(RANKINGS_PATH.read_text(encoding="utf-8"))
    expected = [ranking_row(row) for row in universe]
    expected.sort(
        key=lambda row: (
            row["rank"] is None,
            row["rank"] if row["rank"] is not None else 10**9,
            row["ticker"],
        )
    )
    assert public_rankings == expected
    for row in public_rankings:
        for field in RANKING_FIELDS:
            assert field in row

    for row in universe:
        public_detail = json.loads((STOCKS_DIR / f"{row['ticker']}.json").read_text(encoding="utf-8"))
        assert public_detail == detail_row(row)
        assert "forecast" in public_detail

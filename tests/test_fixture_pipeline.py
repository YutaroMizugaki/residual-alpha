"""End-to-end checks against the committed fictional fixture."""

from __future__ import annotations

import json
from pathlib import Path

from models.pipeline import detail_row, evaluate_universe, ranking_row
from providers.loader import load_fixture_snapshot

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "scripts" / "fixtures" / "stocks.json"
RANKINGS_PATH = ROOT / "public" / "data" / "rankings.json"
STOCKS_DIR = ROOT / "public" / "data" / "stocks"

RANKING_FIELDS = [
    "rank",
    "ticker",
    "companyName",
    "price",
    "priceAsOf",
    "intrinsicPrice",
    "intrinsicUpside",
    "betaAdjusted",
    "returnCount",
    "costOfEquity",
    "normalizedRoe",
    "roeCount",
    "excessRoe",
    "valuationScore",
    "qualityScore",
    "riskScore",
    "totalScore",
    "priceSource",
    "fundamentalsAsOf",
    "fundamentalsSource",
]


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _universe() -> list[dict]:
    snapshot = load_fixture_snapshot()
    return evaluate_universe(snapshot.stocks, snapshot.assumptions)


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
    assert missing["returnCount"] is None
    assert missing["roeCount"] is None
    assert "missing_book_value" in missing["exclusionReasons"]
    assert 0 not in (
        missing["bookValue"],
        missing["intrinsicEquityValue"],
        missing["betaRaw"],
        missing["normalizedRoe"],
        missing["totalScore"],
        missing["returnCount"],
        missing["roeCount"],
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
        assert row["priceSource"] == "fixture"
        assert row["fundamentalsSource"] == "fixture"
        assert row["priceAsOf"] is None
        assert row["fundamentalsAsOf"] is None
        if row["ticker"] == "1006":
            assert row["returnCount"] is None
            assert row["roeCount"] is None
        else:
            assert row["returnCount"] == 24
            assert row["roeCount"] == 3

    for row in universe:
        public_detail = json.loads((STOCKS_DIR / f"{row['ticker']}.json").read_text(encoding="utf-8"))
        assert public_detail == detail_row(row)
        assert "forecast" in public_detail
        assert "priceAsOf" in public_detail
        assert "priceSource" in public_detail
        assert "fundamentalsAsOf" in public_detail
        assert "fundamentalsSource" in public_detail
        assert public_detail["priceSource"] == "fixture"
        assert public_detail["fundamentalsSource"] == "fixture"
        if row["ticker"] == "1006":
            assert public_detail["roeCount"] is None
        else:
            assert public_detail["roeCount"] == 3

    meta = json.loads((ROOT / "public" / "data" / "meta.json").read_text(encoding="utf-8"))
    assert meta["source"] == "fixture"
    assert meta["sourceLabel"] == "Fixture Data"


def test_evaluate_stock_passes_per_name_sources():
    fixtures = _load_fixture()
    stock = dict(fixtures["stocks"][0])
    stock["priceSource"] = "jquants_bars"
    stock["fundamentalsSource"] = "edinet_xbrl"
    stock["priceAsOf"] = "2026-08-17"
    stock["fundamentalsAsOf"] = "2026-03-31"
    row = evaluate_universe([stock], fixtures["assumptions"])[0]
    assert row["priceSource"] == "jquants_bars"
    assert row["fundamentalsSource"] == "edinet_xbrl"
    assert row["priceAsOf"] == "2026-08-17"
    assert row["fundamentalsAsOf"] == "2026-03-31"
    detail = detail_row(row)
    assert detail["priceSource"] == "jquants_bars"
    assert detail["fundamentalsSource"] == "edinet_xbrl"
    assert detail["priceAsOf"] == "2026-08-17"
    assert detail["fundamentalsAsOf"] == "2026-03-31"
    ranked = ranking_row(row)
    assert ranked["priceSource"] == "jquants_bars"
    assert ranked["fundamentalsSource"] == "edinet_xbrl"
    assert ranked["priceAsOf"] == "2026-08-17"
    assert ranked["fundamentalsAsOf"] == "2026-03-31"
    stock["priceSource"] = "  "
    stock["fundamentalsSource"] = ""
    stock["priceAsOf"] = "  "
    stock["fundamentalsAsOf"] = ""
    blank = evaluate_universe([stock], fixtures["assumptions"])[0]
    assert blank["priceSource"] is None
    assert blank["fundamentalsSource"] is None
    assert blank["priceAsOf"] is None
    assert blank["fundamentalsAsOf"] is None


def test_short_roe_history_count_is_not_padded():
    fixtures = _load_fixture()
    stock = dict(fixtures["stocks"][0])
    stock["roeHistory"] = [0.16, 0.18]
    row = evaluate_universe([stock], fixtures["assumptions"])[0]
    assert row["roeCount"] == 2
    assert row["normalizedRoe"] is None
    assert "insufficient_roe_history" in row["exclusionReasons"]
    detail = detail_row(row)
    ranked = ranking_row(row)
    assert detail["roeCount"] == 2
    assert ranked["roeCount"] == 2

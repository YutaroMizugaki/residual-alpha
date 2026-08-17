from __future__ import annotations

import json
from pathlib import Path

import pytest

from providers.errors import BotWallError, InvalidPriceDataError
from providers.http import cache_filename, fetch_yahoo_chart_json, fetch_yahoo_fundamentals_json
from providers.loader import load_fixture_snapshot, load_free_snapshot
from providers.series import aligned_simple_returns
from providers.stooq_csv import parse_stooq_csv
from providers.yahoo_chart import parse_yahoo_chart
from providers.yahoo_fundamentals import parse_yahoo_fundamentals
from models.pipeline import evaluate_universe

ROOT = Path(__file__).resolve().parents[1]
YAHOO_DIR = ROOT / "tests" / "data" / "yahoo"
FUND_DIR = ROOT / "tests" / "data" / "yahoo_fundamentals"
STOOQ_DIR = ROOT / "tests" / "data" / "stooq"


def test_yahoo_chart_parses_recorded_toyota():
    payload = json.loads((YAHOO_DIR / "7203.T.json").read_text(encoding="utf-8"))
    series = parse_yahoo_chart(payload, expected_symbol="7203.T")
    last = series.last()
    assert last is not None
    assert last[1] == pytest.approx(3013.0)
    assert series.currency == "JPY"
    assert all(price > 0 for _, price in series.points)


def test_yahoo_charts_cover_one_year_aligned_to_nikkei():
    market = json.loads((YAHOO_DIR / "_N225.json").read_text(encoding="utf-8"))
    market_ts = [int(x) for x in market["chart"]["result"][0]["timestamp"]]
    assert len(market_ts) >= 200
    symbols = [
        "7203.T",
        "6758.T",
        "9984.T",
        "6861.T",
        "6501.T",
        "8035.T",
        "4063.T",
        "8306.T",
        "9432.T",
        "6098.T",
    ]
    expected_last = {
        "7203.T": 3013.0,
        "6758.T": 3780.0,
        "9984.T": 5886.0,
        "6861.T": 86750.0,
        "6501.T": 5571.0,
        "8035.T": 60090.0,
        "4063.T": 6385.0,
        "8306.T": 3649.0,
        "9432.T": 161.5,
        "6098.T": 16380.0,
    }
    for symbol in symbols:
        payload = json.loads((YAHOO_DIR / f"{symbol}.json").read_text(encoding="utf-8"))
        result = payload["chart"]["result"][0]
        ts = [int(x) for x in result["timestamp"]]
        closes = result["indicators"]["quote"][0]["close"]
        assert ts == market_ts
        assert None not in closes
        assert 0 not in closes
        assert closes[-1] == pytest.approx(expected_last[symbol])
        series = parse_yahoo_chart(payload, expected_symbol=symbol)
        market_series = parse_yahoo_chart(market, expected_symbol="^N225")
        stock_returns, market_returns = aligned_simple_returns(series, market_series)
        assert len(stock_returns) >= 199
        assert len(stock_returns) == len(market_returns)


def test_yahoo_null_close_not_zero():
    payload = json.loads((YAHOO_DIR / "null_close.json").read_text(encoding="utf-8"))
    series = parse_yahoo_chart(payload)
    closes = [price for _, price in series.points]
    assert None not in closes
    assert 0 not in closes
    assert closes == pytest.approx([1000.0, 1100.0, 1089.0])


def test_yahoo_html_is_fetch_error():
    with pytest.raises(BotWallError):
        parse_yahoo_chart("<!DOCTYPE html><html>verify your browser</html>")


def test_stooq_csv_parse_and_returns():
    stock = parse_stooq_csv((STOOQ_DIR / "7203.jp.csv").read_text(encoding="utf-8"), symbol="7203.jp")
    market = parse_stooq_csv((STOOQ_DIR / "market.csv").read_text(encoding="utf-8"), symbol="^tpx")
    assert stock.last()[1] == pytest.approx(3000.0)
    stock_returns, market_returns = aligned_simple_returns(stock, market)
    assert len(stock_returns) == len(market_returns) == 3
    assert stock_returns[0] == pytest.approx(3040.0 / 3020.0 - 1.0)


def test_stooq_html_is_bot_wall():
    html = (STOOQ_DIR / "blocked.html").read_text(encoding="utf-8")
    with pytest.raises(BotWallError):
        parse_stooq_csv(html, symbol="7203.jp")


def test_stooq_zero_close_skipped():
    csv_text = (
        "Date,Open,High,Low,Close,Volume\n"
        "2026-01-05,10,10,10,10,1\n"
        "2026-01-06,10,10,10,0,1\n"
        "2026-01-07,11,11,11,11,1\n"
    )
    series = parse_stooq_csv(csv_text, symbol="ZERO.jp")
    assert [price for _, price in series.points] == pytest.approx([10.0, 11.0])


def test_fetch_yahoo_does_not_hit_network_when_injected():
    def fake_fetch(url: str) -> tuple[int, str, str]:
        assert "7203.T" in url
        return 200, "application/json", (YAHOO_DIR / "7203.T.json").read_text(encoding="utf-8")

    payload = fetch_yahoo_chart_json("7203.T", fetcher=fake_fetch)
    series = parse_yahoo_chart(payload)
    assert series.last()[1] == pytest.approx(3013.0)


def test_fetch_yahoo_html_status_is_error():
    def fake_fetch(url: str) -> tuple[int, str, str]:
        return 200, "text/html", "<html>verify</html>"

    with pytest.raises(BotWallError):
        fetch_yahoo_chart_json("7203.T", fetcher=fake_fetch)


def test_cache_filename_strips_caret():
    assert cache_filename("^N225") == "_N225.json"


def test_free_provider_prices_without_fundamentals_are_not_zero(tmp_path: Path):
    snapshot = load_free_snapshot(
        raw_dir=YAHOO_DIR,
        fundamentals_dir=tmp_path,
        fetch=False,
    )
    by_ticker = {row["ticker"]: row for row in snapshot.stocks}
    toyota = by_ticker["7203"]
    assert toyota["price"] == pytest.approx(3013.0)
    assert toyota["priceAsOf"] is not None
    assert toyota["bookValue"] is None
    assert toyota["latestRoe"] is None
    assert snapshot.fundamentals_source == "missing"
    assert toyota["priceSource"] == "yahoo_chart"
    assert toyota["fundamentalsSource"] is None
    assert toyota["stockReturns"]
    assert toyota["marketReturns"]
    assert len(toyota["stockReturns"]) == len(toyota["marketReturns"])
    assert len(toyota["stockReturns"]) >= 199

    computed = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    toyota_eval = next(row for row in computed if row["ticker"] == "7203")
    assert toyota_eval["eligible"] is False
    assert "missing_book_value" in toyota_eval["exclusionReasons"]
    assert toyota_eval["bookValue"] is None
    assert toyota_eval["intrinsicEquityValue"] is None
    assert toyota_eval["price"] == pytest.approx(3013.0)


def test_free_provider_with_fundamentals_can_value(tmp_path: Path):
    overlay = tmp_path / "fundamentals.json"
    overlay.write_text(
        json.dumps(
            {
                "stocks": {
                    "7203": {
                        "bookValue": 35000000,
                        "sharesOutstanding": 13000,
                        "latestRoe": 0.12,
                        "roeHistory": [0.10, 0.11, 0.12],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    snapshot = load_free_snapshot(
        raw_dir=YAHOO_DIR,
        fundamentals_dir=tmp_path / "empty-fund",
        fetch=False,
        fundamentals_path=overlay,
    )
    computed = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    toyota = next(row for row in computed if row["ticker"] == "7203")
    assert snapshot.fundamentals_source == "manual_overlay"
    assert toyota["fundamentalsSource"] == "manual_overlay"
    assert toyota["priceSource"] == "yahoo_chart"
    assert toyota["eligible"] is True
    assert toyota["intrinsicPrice"] is not None
    assert toyota["forecast"][9]["roe"] == toyota["costOfEquity"]
    sony = next(row for row in computed if row["ticker"] == "6758")
    assert sony["eligible"] is False
    assert sony["bookValue"] is None


def test_fixture_provider_still_default():
    snapshot = load_fixture_snapshot()
    assert snapshot.source == "fixture"
    assert snapshot.stocks[0]["ticker"] == "1001"
    assert snapshot.stocks[0]["priceSource"] == "fixture"
    assert snapshot.stocks[0]["fundamentalsSource"] == "fixture"


def test_non_jpy_rejected():
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {"currency": "USD", "symbol": "AAPL", "gmtoffset": 0},
                    "timestamp": [1, 2],
                    "indicators": {"quote": [{"close": [1.0, 1.1]}]},
                }
            ],
            "error": None,
        }
    }
    with pytest.raises(InvalidPriceDataError, match="JPY"):
        parse_yahoo_chart(payload)


def test_yahoo_fundamentals_toyota_units_and_beginning_roe():
    payload = json.loads((FUND_DIR / "7203.T.json").read_text(encoding="utf-8"))
    fundamentals = parse_yahoo_fundamentals(payload)
    assert fundamentals.book_value == pytest.approx(39_918_854.0)
    assert fundamentals.shares_outstanding == pytest.approx(13_033.384474)
    assert fundamentals.fiscal_year_end == "2026-03-31"
    assert fundamentals.roe_history is not None
    assert len(fundamentals.roe_history) == 3
    expected_latest = 3_848_098_000_000.0 / 35_924_826_000_000.0
    assert fundamentals.latest_roe == pytest.approx(expected_latest)
    assert fundamentals.roe_history[-1] == pytest.approx(expected_latest)


def test_yahoo_fundamentals_extra_universe_name_has_three_roes():
    payload = json.loads((FUND_DIR / "6861.T.json").read_text(encoding="utf-8"))
    fundamentals = parse_yahoo_fundamentals(payload)
    assert fundamentals.book_value is not None
    assert fundamentals.book_value != 0
    assert fundamentals.shares_outstanding is not None
    assert fundamentals.roe_history is not None
    assert len(fundamentals.roe_history) == 3
    assert fundamentals.fiscal_year_end == "2026-03-31"


def test_yahoo_fundamentals_missing_year_not_zero():
    payload = json.loads((FUND_DIR / "missing_year.json").read_text(encoding="utf-8"))
    fundamentals = parse_yahoo_fundamentals(payload)
    assert fundamentals.book_value == pytest.approx(1_300.0)
    assert fundamentals.roe_history is not None
    assert 0 not in fundamentals.roe_history
    assert None not in fundamentals.roe_history
    # 2025 is missing, so 2026 is not computed off 2024 equity.
    assert len(fundamentals.roe_history) == 1
    assert fundamentals.roe_history[0] == pytest.approx(0.12)


def test_yahoo_fundamentals_html_is_bot_wall():
    with pytest.raises(BotWallError):
        parse_yahoo_fundamentals("<html>verify your browser</html>")


def test_sony_negative_income_is_not_coerced_to_zero():
    payload = json.loads((FUND_DIR / "6758.T.json").read_text(encoding="utf-8"))
    fundamentals = parse_yahoo_fundamentals(payload)
    assert fundamentals.latest_roe is not None
    assert fundamentals.latest_roe < 0


def test_free_snapshot_with_recorded_fundamentals_ranks(tmp_path: Path):
    snapshot = load_free_snapshot(
        raw_dir=YAHOO_DIR,
        fundamentals_dir=FUND_DIR,
        fetch=False,
        fundamentals_path=tmp_path / "empty.json",
    )
    assert snapshot.fundamentals_source == "yahoo_timeseries"
    computed = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    by_ticker = {row["ticker"]: row for row in computed}
    toyota = by_ticker["7203"]
    assert toyota["eligible"] is True
    assert toyota["rank"] is not None
    assert toyota["bookValue"] == pytest.approx(39_918_854.0)
    assert toyota["forecast"][9]["roe"] == toyota["costOfEquity"]
    sony = by_ticker["6758"]
    assert sony["eligible"] is True
    assert sony["latestRoe"] < 0
    softbank = by_ticker["9984"]
    assert softbank["eligible"] is True
    ranked = [row["ticker"] for row in computed if row["rank"] is not None]
    assert set(ranked) == {
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
    assert toyota["fundamentalsAsOf"] == "2026-03-31"
    assert toyota["priceSource"] == "yahoo_chart"
    assert toyota["fundamentalsSource"] == "yahoo_timeseries"
    raw_toyota = next(row for row in snapshot.stocks if row["ticker"] == "7203")
    assert len(raw_toyota["stockReturns"]) >= 199
    assert toyota["returnCount"] >= 199
    assert by_ticker["6861"]["eligible"] is True
    assert by_ticker["6861"]["price"] == pytest.approx(86750.0)
    assert by_ticker["6861"]["priceSource"] == "yahoo_chart"
    assert by_ticker["6861"]["fundamentalsSource"] == "yahoo_timeseries"
    assert by_ticker["9432"]["price"] == pytest.approx(161.5)
    assert by_ticker["6861"]["bookValue"] != 0


def test_overlay_does_not_overwrite_yahoo_fundamentals(tmp_path: Path):
    overlay = tmp_path / "fundamentals.json"
    overlay.write_text(
        json.dumps(
            {
                "stocks": {
                    "7203": {
                        "bookValue": 1,
                        "sharesOutstanding": 1,
                        "latestRoe": 0.99,
                        "roeHistory": [0.99, 0.99, 0.99],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    snapshot = load_free_snapshot(
        raw_dir=YAHOO_DIR,
        fundamentals_dir=FUND_DIR,
        fetch=False,
        fundamentals_path=overlay,
    )
    toyota = next(row for row in snapshot.stocks if row["ticker"] == "7203")
    assert toyota["bookValue"] == pytest.approx(39_918_854.0)
    assert toyota["latestRoe"] != pytest.approx(0.99)
    assert toyota["fundamentalsSource"] == "yahoo_timeseries"
    assert snapshot.fundamentals_source == "yahoo_timeseries"


def test_fetch_yahoo_fundamentals_does_not_hit_network_when_injected():
    def fake_fetch(url: str) -> tuple[int, str, str]:
        assert "7203.T" in url
        assert "annualStockholdersEquity" in url
        return 200, "application/json", (FUND_DIR / "7203.T.json").read_text(encoding="utf-8")

    payload = fetch_yahoo_fundamentals_json("7203.T", fetcher=fake_fetch)
    fundamentals = parse_yahoo_fundamentals(payload)
    assert fundamentals.book_value == pytest.approx(39_918_854.0)


def test_fetch_yahoo_fundamentals_html_status_is_error():
    def fake_fetch(url: str) -> tuple[int, str, str]:
        return 200, "text/html", "<html>verify</html>"

    with pytest.raises(BotWallError):
        fetch_yahoo_fundamentals_json("7203.T", fetcher=fake_fetch)


def test_yahoo_fundamentals_non_jpy_equity_rejected():
    payload = {
        "timeseries": {
            "result": [
                {
                    "annualStockholdersEquity": [
                        {
                            "asOfDate": "2026-03-31",
                            "currencyCode": "USD",
                            "reportedValue": {"raw": 1.0},
                        }
                    ]
                }
            ]
        }
    }
    with pytest.raises(InvalidPriceDataError, match="JPY"):
        parse_yahoo_fundamentals(payload)

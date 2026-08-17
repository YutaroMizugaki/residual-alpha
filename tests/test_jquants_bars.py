from __future__ import annotations

import json
from pathlib import Path

import pytest

from models.pipeline import evaluate_universe
from providers.errors import BotWallError, FetchError, InvalidPriceDataError
from providers.http import fetch_jquants_bars_json, jquants_bars_url
from providers.jquants_bars import parse_jquants_bars
from providers.loader import load_auto_snapshot, load_jquants_snapshot

ROOT = Path(__file__).resolve().parents[1]
YAHOO_DIR = ROOT / "tests" / "data" / "yahoo"
JQUANTS_DIR = ROOT / "tests" / "data" / "jquants"
BARS_DIR = ROOT / "tests" / "data" / "jquants_bars"
FUND_DIR = ROOT / "tests" / "data" / "yahoo_fundamentals"
XBRL_DIR = ROOT / "tests" / "data" / "edinet_xbrl"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _mini_universe(path: Path) -> Path:
    _write_json(
        path,
        {
            "priceSource": "yahoo_chart",
            "marketSymbol": "^N225",
            "marketName": "Nikkei 225",
            "range": "1y",
            "riskFreeRate": 0.015,
            "equityRiskPremium": 0.05,
            "retentionRatio": 0.5,
            "stocks": [
                {
                    "ticker": "7203",
                    "yahooSymbol": "7203.T",
                    "stooqSymbol": "7203.jp",
                    "jquantsCode": "72030",
                    "edinetSecCode": "72030",
                    "companyName": "Toyota Motor",
                }
            ],
        },
    )
    return path


def _poison_yahoo_chart(path: Path) -> None:
    _write_json(
        path,
        {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "currency": "JPY",
                            "symbol": "7203.T",
                            "gmtoffset": 32400,
                        },
                        "timestamp": [1784246400, 1784592000, 1784678400],
                        "indicators": {"quote": [{"close": [1.0, 1.0, 1.0]}]},
                    }
                ],
                "error": None,
            }
        },
    )


def test_jquants_bars_toyota_adjc_matches_recorded_yahoo():
    payload = json.loads((BARS_DIR / "72030.json").read_text(encoding="utf-8"))
    series = parse_jquants_bars(payload, expected_code="72030")
    last = series.last()
    assert last is not None
    assert last[1] == pytest.approx(3013.0)
    assert series.currency == "JPY"


def test_jquants_bars_empty_adjc_is_missing_not_zero():
    payload = json.loads((BARS_DIR / "empty_adjc.json").read_text(encoding="utf-8"))
    series = parse_jquants_bars(payload, expected_code="72030")
    assert [point[1] for point in series.points] == [pytest.approx(3013.0)]
    assert 0 not in [point[1] for point in series.points]
    assert 100.0 not in [point[1] for point in series.points]


def test_jquants_bars_zero_adjc_is_invalid_not_price_zero():
    payload = json.loads((BARS_DIR / "zero_adjc.json").read_text(encoding="utf-8"))
    with pytest.raises(FetchError, match="no valid adjusted closes"):
        parse_jquants_bars(payload, expected_code="72030")


def test_jquants_bars_html_is_bot_wall():
    with pytest.raises(BotWallError):
        parse_jquants_bars("<html>verify</html>", expected_code="72030")


def test_jquants_bars_invalid_payload_shape():
    with pytest.raises(InvalidPriceDataError):
        parse_jquants_bars(["not", "an", "object"], expected_code="72030")


def test_jquants_bars_url_has_code_not_key():
    url = jquants_bars_url("72030", from_="2025-01-01", to="2026-01-01")
    assert "72030" in url
    assert "from=2025-01-01" in url
    assert "x-api-key" not in url


def test_fetch_jquants_bars_401_is_fetch_error():
    def fake_fetch(url: str) -> tuple[int, str, str]:
        return 401, "application/json", '{"message":"denied"}'

    with pytest.raises(FetchError, match="401"):
        fetch_jquants_bars_json("72030", fetcher=fake_fetch)


def test_fetch_jquants_bars_paginates(tmp_path: Path):
    pages = {
        None: {
            "data": [{"Date": "2026-01-05", "Code": "72030", "AdjC": 100.0}],
            "pagination_key": "page-2",
        },
        "page-2": {
            "data": [{"Date": "2026-01-06", "Code": "72030", "AdjC": 110.0}],
        },
    }

    def fake_fetch(url: str) -> tuple[int, str, str]:
        key = "page-2" if "pagination_key=page-2" in url else None
        return 200, "application/json", json.dumps(pages[key])

    payload = fetch_jquants_bars_json("72030", fetcher=fake_fetch)
    assert len(payload["data"]) == 2
    series = parse_jquants_bars(payload, expected_code="72030")
    assert series.last()[1] == pytest.approx(110.0)


def test_jquants_snapshot_prefers_bars_over_yahoo(tmp_path: Path):
    yahoo_dir = tmp_path / "yahoo"
    _write_json(yahoo_dir / "_N225.json", json.loads((YAHOO_DIR / "_N225.json").read_text()))
    _poison_yahoo_chart(yahoo_dir / "7203.T.json")
    snapshot = load_jquants_snapshot(
        universe_path=_mini_universe(tmp_path / "universe.json"),
        raw_dir=yahoo_dir,
        jquants_dir=JQUANTS_DIR,
        jquants_bars_dir=BARS_DIR,
        fetch=False,
        fundamentals_path=tmp_path / "empty.json",
    )
    toyota = next(row for row in snapshot.stocks if row["ticker"] == "7203")
    assert snapshot.price_source == "jquants_bars"
    assert toyota["price"] == pytest.approx(3013.0)
    assert toyota["price"] != pytest.approx(1.0)
    computed = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    ranked = next(row for row in computed if row["ticker"] == "7203")
    assert ranked["eligible"] is True


def test_jquants_snapshot_falls_back_to_yahoo_without_bars(tmp_path: Path):
    snapshot = load_jquants_snapshot(
        universe_path=_mini_universe(tmp_path / "universe.json"),
        raw_dir=YAHOO_DIR,
        jquants_dir=JQUANTS_DIR,
        jquants_bars_dir=tmp_path / "no-bars",
        fetch=False,
        fundamentals_path=tmp_path / "empty.json",
    )
    toyota = next(row for row in snapshot.stocks if row["ticker"] == "7203")
    assert snapshot.price_source == "yahoo_chart"
    assert toyota["price"] == pytest.approx(3013.0)


def test_partial_jquants_bars_do_not_block_yahoo(tmp_path: Path):
    bars_dir = tmp_path / "bars"
    _write_json(
        bars_dir / "72030.json",
        {
            "data": [
                {"Date": "2026-01-05", "Code": "72030", "AdjC": 50.0},
                {"Date": "2026-01-06", "Code": "72030", "AdjC": 51.0},
            ]
        },
    )
    snapshot = load_jquants_snapshot(
        universe_path=_mini_universe(tmp_path / "universe.json"),
        raw_dir=YAHOO_DIR,
        jquants_dir=JQUANTS_DIR,
        jquants_bars_dir=bars_dir,
        fetch=False,
        fundamentals_path=tmp_path / "empty.json",
    )
    toyota = next(row for row in snapshot.stocks if row["ticker"] == "7203")
    assert snapshot.price_source == "yahoo_chart"
    assert toyota["price"] == pytest.approx(3013.0)
    assert toyota["price"] != pytest.approx(51.0)


def test_auto_prefers_jquants_bars_then_yahoo(tmp_path: Path):
    yahoo_dir = tmp_path / "yahoo"
    _write_json(yahoo_dir / "_N225.json", json.loads((YAHOO_DIR / "_N225.json").read_text()))
    _poison_yahoo_chart(yahoo_dir / "7203.T.json")
    snapshot = load_auto_snapshot(
        universe_path=_mini_universe(tmp_path / "universe.json"),
        raw_dir=yahoo_dir,
        fundamentals_dir=FUND_DIR,
        jquants_dir=JQUANTS_DIR,
        jquants_bars_dir=BARS_DIR,
        edinet_dir=XBRL_DIR,
        fundamentals_path=tmp_path / "empty.json",
    )
    toyota = next(row for row in snapshot.stocks if row["ticker"] == "7203")
    assert snapshot.price_source == "jquants_bars"
    assert toyota["price"] == pytest.approx(3013.0)
    assert toyota["bookValue"] == pytest.approx(39_918_854.0)


def test_auto_mixed_price_sources_across_names(tmp_path: Path):
    universe = tmp_path / "universe.json"
    _write_json(
        universe,
        {
            "priceSource": "yahoo_chart",
            "marketSymbol": "^N225",
            "range": "1y",
            "riskFreeRate": 0.015,
            "equityRiskPremium": 0.05,
            "retentionRatio": 0.5,
            "stocks": [
                {
                    "ticker": "7203",
                    "yahooSymbol": "7203.T",
                    "jquantsCode": "72030",
                    "edinetSecCode": "72030",
                    "companyName": "Toyota Motor",
                },
                {
                    "ticker": "6758",
                    "yahooSymbol": "6758.T",
                    "jquantsCode": "67580",
                    "edinetSecCode": "67580",
                    "companyName": "Sony Group",
                },
            ],
        },
    )
    bars_dir = tmp_path / "bars"
    _write_json(bars_dir / "72030.json", json.loads((BARS_DIR / "72030.json").read_text()))
    snapshot = load_auto_snapshot(
        universe_path=universe,
        raw_dir=YAHOO_DIR,
        fundamentals_dir=FUND_DIR,
        jquants_dir=JQUANTS_DIR,
        jquants_bars_dir=bars_dir,
        edinet_dir=XBRL_DIR,
        fundamentals_path=tmp_path / "empty.json",
    )
    by_ticker = {row["ticker"]: row for row in snapshot.stocks}
    assert snapshot.price_source == "jquants_bars+yahoo_chart"
    assert by_ticker["7203"]["price"] == pytest.approx(3013.0)
    assert by_ticker["6758"]["price"] == pytest.approx(3780.0)

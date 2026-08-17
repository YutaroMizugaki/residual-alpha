from __future__ import annotations

import json
from pathlib import Path

import pytest

from models.pipeline import evaluate_universe
from providers.loader import load_auto_snapshot, load_universe
from refresh_public_data import fetch_plan

ROOT = Path(__file__).resolve().parents[1]
YAHOO_DIR = ROOT / "tests" / "data" / "yahoo"
FUND_DIR = ROOT / "tests" / "data" / "yahoo_fundamentals"
JQUANTS_DIR = ROOT / "tests" / "data" / "jquants"
XBRL_DIR = ROOT / "tests" / "data" / "edinet_xbrl"
UNIVERSE_PATH = ROOT / "scripts" / "providers" / "universe.json"

TOYOTA_BOOK = 39_918_854.0
CORE = {"7203", "6758", "9984"}
POISON_BOOK = 1.0


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _mini_universe(path: Path, tickers: list[tuple[str, str]]) -> Path:
    stocks = [
        {
            "ticker": ticker,
            "yahooSymbol": f"{ticker}.T",
            "stooqSymbol": f"{ticker}.jp",
            "jquantsCode": f"{ticker}0",
            "edinetSecCode": f"{ticker}0",
            "companyName": name,
        }
        for ticker, name in tickers
    ]
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
            "stocks": stocks,
        },
    )
    return path


def _copy_tree(src: Path, dest: Path) -> None:
    if src.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
        return
    dest.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        _copy_tree(child, dest / child.name)


def _poison_jquants(path: Path, code: str) -> None:
    _write_json(
        path,
        {
            "data": [
                {
                    "DiscDate": "2026-05-08",
                    "DiscNo": "1",
                    "Code": code,
                    "DocType": "FYFinancialStatements_Consolidated_IFRS",
                    "CurPerType": "FY",
                    "CurPerEn": "2026-03-31",
                    "NP": "1",
                    "Eq": "1000000",
                    "ShEq": "1000000",
                    "ShOutFY": "1000000",
                    "TrShFY": "0",
                }
            ]
        },
    )


def _poison_yahoo(path: Path) -> None:
    _write_json(
        path,
        {
            "timeseries": {
                "result": [
                    {
                        "annualStockholdersEquity": [
                            {
                                "asOfDate": "2026-03-31",
                                "currencyCode": "JPY",
                                "reportedValue": {"raw": 1_000_000.0},
                            }
                        ]
                    },
                    {
                        "annualNetIncomeCommonStockholders": [
                            {
                                "asOfDate": "2026-03-31",
                                "currencyCode": "JPY",
                                "reportedValue": {"raw": 100.0},
                            }
                        ]
                    },
                    {
                        "annualOrdinarySharesNumber": [
                            {
                                "asOfDate": "2026-03-31",
                                "reportedValue": {"raw": 1_000_000.0},
                            }
                        ]
                    },
                ],
                "error": None,
            }
        },
    )


def _toyota_universe(path: Path) -> Path:
    return _mini_universe(path, [("7203", "Toyota Motor")])


def test_fetch_plan_yahoo_always_keyed_optional():
    assert fetch_plan({}) == ["fetch_free_data.py"]
    assert fetch_plan({"JQUANTS_API_KEY": "  "}) == ["fetch_free_data.py"]
    assert fetch_plan({"JQUANTS_API_KEY": "jq"}) == [
        "fetch_free_data.py",
        "fetch_jquants_data.py",
    ]
    assert fetch_plan({"EDINET_API_KEY": "ed"}) == [
        "fetch_free_data.py",
        "fetch_edinet_xbrl.py",
    ]
    assert fetch_plan({"JQUANTS_API_KEY": "jq", "EDINET_API_KEY": "ed"}) == [
        "fetch_free_data.py",
        "fetch_jquants_data.py",
        "fetch_edinet_xbrl.py",
    ]


def test_auto_prefers_edinet_when_jquants_also_present(tmp_path: Path):
    jquants_dir = tmp_path / "jquants"
    yahoo_fund = tmp_path / "yahoo_fund"
    _poison_jquants(jquants_dir / "72030.json", "72030")
    _poison_yahoo(yahoo_fund / "7203.T.json")
    snapshot = load_auto_snapshot(
        universe_path=_toyota_universe(tmp_path / "universe.json"),
        raw_dir=YAHOO_DIR,
        fundamentals_dir=yahoo_fund,
        jquants_dir=jquants_dir,
        edinet_dir=XBRL_DIR,
        fundamentals_path=tmp_path / "empty.json",
    )
    toyota = next(row for row in snapshot.stocks if row["ticker"] == "7203")
    assert snapshot.fundamentals_source == "edinet_xbrl"
    assert toyota["bookValue"] == pytest.approx(TOYOTA_BOOK)
    assert toyota["bookValue"] != pytest.approx(POISON_BOOK)


def test_auto_uses_jquants_when_edinet_missing(tmp_path: Path):
    yahoo_fund = tmp_path / "yahoo_fund"
    _poison_yahoo(yahoo_fund / "7203.T.json")
    snapshot = load_auto_snapshot(
        universe_path=_toyota_universe(tmp_path / "universe.json"),
        raw_dir=YAHOO_DIR,
        fundamentals_dir=yahoo_fund,
        jquants_dir=JQUANTS_DIR,
        edinet_dir=tmp_path / "no-edinet",
        fundamentals_path=tmp_path / "empty.json",
    )
    toyota = next(row for row in snapshot.stocks if row["ticker"] == "7203")
    assert snapshot.fundamentals_source == "jquants_summary"
    assert toyota["bookValue"] == pytest.approx(TOYOTA_BOOK)
    assert toyota["bookValue"] != pytest.approx(POISON_BOOK)


def test_auto_uses_yahoo_when_keyed_caches_missing(tmp_path: Path):
    snapshot = load_auto_snapshot(
        universe_path=_toyota_universe(tmp_path / "universe.json"),
        raw_dir=YAHOO_DIR,
        fundamentals_dir=FUND_DIR,
        jquants_dir=tmp_path / "no-jquants",
        edinet_dir=tmp_path / "no-edinet",
        fundamentals_path=tmp_path / "empty.json",
    )
    toyota = next(row for row in snapshot.stocks if row["ticker"] == "7203")
    assert snapshot.fundamentals_source == "yahoo_timeseries"
    assert toyota["bookValue"] == pytest.approx(TOYOTA_BOOK)


def test_auto_mixed_sources_across_names(tmp_path: Path):
    universe = _mini_universe(
        tmp_path / "universe.json",
        [("7203", "Toyota Motor"), ("6758", "Sony Group"), ("9984", "SoftBank Group")],
    )
    edinet_dir = tmp_path / "edinet"
    jquants_dir = tmp_path / "jquants"
    yahoo_fund = tmp_path / "yahoo_fund"
    _copy_tree(XBRL_DIR / "72030", edinet_dir / "72030")
    _copy_tree(JQUANTS_DIR / "67580.json", jquants_dir / "67580.json")
    _copy_tree(FUND_DIR / "9984.T.json", yahoo_fund / "9984.T.json")
    snapshot = load_auto_snapshot(
        universe_path=universe,
        raw_dir=YAHOO_DIR,
        fundamentals_dir=yahoo_fund,
        jquants_dir=jquants_dir,
        edinet_dir=edinet_dir,
        fundamentals_path=tmp_path / "empty.json",
    )
    by_ticker = {row["ticker"]: row for row in snapshot.stocks}
    assert snapshot.fundamentals_source == "edinet_xbrl+jquants_summary+yahoo_timeseries"
    assert by_ticker["7203"]["bookValue"] == pytest.approx(TOYOTA_BOOK)
    assert by_ticker["6758"]["latestRoe"] < 0
    assert by_ticker["9984"]["bookValue"] is not None
    computed = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    ranked = [row["ticker"] for row in computed if row["rank"] is not None]
    assert set(ranked) == CORE


def test_auto_does_not_mix_sources_inside_one_name(tmp_path: Path):
    overlay = tmp_path / "overlay.json"
    _write_json(
        overlay,
        {
            "stocks": {
                "7203": {
                    "bookValue": POISON_BOOK,
                    "sharesOutstanding": 1,
                    "latestRoe": 0.99,
                    "roeHistory": [0.99, 0.99, 0.99],
                }
            }
        },
    )
    jquants_dir = tmp_path / "jquants"
    yahoo_fund = tmp_path / "yahoo_fund"
    _poison_jquants(jquants_dir / "72030.json", "72030")
    _poison_yahoo(yahoo_fund / "7203.T.json")
    snapshot = load_auto_snapshot(
        universe_path=_toyota_universe(tmp_path / "universe.json"),
        raw_dir=YAHOO_DIR,
        fundamentals_dir=yahoo_fund,
        jquants_dir=jquants_dir,
        edinet_dir=XBRL_DIR,
        fundamentals_path=overlay,
    )
    toyota = next(row for row in snapshot.stocks if row["ticker"] == "7203")
    assert toyota["bookValue"] == pytest.approx(TOYOTA_BOOK)
    assert toyota["latestRoe"] != pytest.approx(0.99)
    assert snapshot.fundamentals_source == "edinet_xbrl"


def test_expanded_universe_extra_names_stay_ineligible(tmp_path: Path):
    universe = load_universe(UNIVERSE_PATH)
    tickers = [str(item["ticker"]) for item in universe["stocks"]]
    assert tickers == [
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
    ]
    snapshot = load_auto_snapshot(
        raw_dir=YAHOO_DIR,
        fundamentals_dir=FUND_DIR,
        jquants_dir=JQUANTS_DIR,
        edinet_dir=XBRL_DIR,
        fundamentals_path=tmp_path / "empty.json",
    )
    assert snapshot.source == "auto"
    assert [row["ticker"] for row in snapshot.stocks] == tickers
    extras = [row for row in snapshot.stocks if row["ticker"] not in CORE]
    assert len(extras) == 7
    for stock in extras:
        assert stock["price"] is None
        assert stock["bookValue"] is None
        assert stock["sharesOutstanding"] is None
        assert stock["latestRoe"] is None
    computed = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    by_ticker = {row["ticker"]: row for row in computed}
    ranked = [row["ticker"] for row in computed if row["rank"] is not None]
    assert set(ranked) == CORE
    for ticker in tickers:
        if ticker in CORE:
            assert by_ticker[ticker]["eligible"] is True
            continue
        assert by_ticker[ticker]["eligible"] is False
        assert by_ticker[ticker]["bookValue"] is None
        assert by_ticker[ticker]["price"] is None
        assert "missing_book_value" in by_ticker[ticker]["exclusionReasons"]
        assert "missing_price" in by_ticker[ticker]["exclusionReasons"]

from __future__ import annotations

import json
from pathlib import Path

import pytest

from models.pipeline import evaluate_universe, ranking_row
from providers.loader import load_auto_snapshot, load_universe
from refresh_public_data import fetch_plan

ROOT = Path(__file__).resolve().parents[1]
YAHOO_DIR = ROOT / "tests" / "data" / "yahoo"
FUND_DIR = ROOT / "tests" / "data" / "yahoo_fundamentals"
JQUANTS_DIR = ROOT / "tests" / "data" / "jquants"
BARS_DIR = ROOT / "tests" / "data" / "jquants_bars"
XBRL_DIR = ROOT / "tests" / "data" / "edinet_xbrl"
UNIVERSE_PATH = ROOT / "scripts" / "providers" / "universe.json"

TOYOTA_BOOK = 39_918_854.0
CORE = {"7203", "6758", "9984"}
EDINET_TEN = [
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
EDINET_COMPLETE = set(EDINET_TEN) | {
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
}
TICKERS = EDINET_TEN
INCOMPLETE = {"8729"}
EXTRAS = [ticker for ticker in TICKERS if ticker not in CORE]
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


def _write_partial_edinet(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:jpigp="http://disclosure.edinet-fsa.go.jp/taxonomy/jpigp/2025-11-01/jpigp_cor">
  <xbrli:unit id="JPY"><xbrli:measure>iso4217:JPY</xbrli:measure></xbrli:unit>
  <xbrli:context id="CurrentYearInstant">
    <xbrli:entity><xbrli:identifier scheme="http://disclosure.edinet-fsa.go.jp">E00000</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2026-03-31</xbrli:instant></xbrli:period>
  </xbrli:context>
  <jpigp:EquityAttributableToOwnersOfParentIFRS contextRef="CurrentYearInstant" unitRef="JPY" decimals="-6">1000000</jpigp:EquityAttributableToOwnersOfParentIFRS>
</xbrli:xbrl>
""",
        encoding="utf-8",
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
    keys = {"JQUANTS_API_KEY": "jq", "EDINET_API_KEY": "ed"}
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
    assert fetch_plan(keys) == [
        "fetch_free_data.py",
        "fetch_jquants_data.py",
        "fetch_edinet_xbrl.py",
    ]
    assert fetch_plan(keys, source="free") == ["fetch_free_data.py"]
    assert fetch_plan(keys, source="jquants") == [
        "fetch_free_data.py",
        "fetch_jquants_data.py",
    ]
    assert fetch_plan(keys, source="edinet") == [
        "fetch_free_data.py",
        "fetch_edinet_xbrl.py",
    ]
    assert fetch_plan({"JQUANTS_API_KEY": "jq"}, source="edinet") == ["fetch_free_data.py"]


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
    assert by_ticker["7203"]["fundamentalsSource"] == "edinet_xbrl"
    assert by_ticker["6758"]["latestRoe"] < 0
    assert by_ticker["6758"]["fundamentalsSource"] == "jquants_summary"
    assert by_ticker["9984"]["bookValue"] is not None
    assert by_ticker["9984"]["fundamentalsSource"] == "yahoo_timeseries"
    computed = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    ranked = [row["ticker"] for row in computed if row["rank"] is not None]
    assert set(ranked) == CORE
    by_rank = {row["ticker"]: ranking_row(row) for row in computed}
    assert by_rank["7203"]["fundamentalsSource"] == "edinet_xbrl"
    assert by_rank["6758"]["fundamentalsSource"] == "jquants_summary"
    assert by_rank["9984"]["fundamentalsSource"] == "yahoo_timeseries"
    assert by_rank["7203"]["fundamentalsSource"] != snapshot.fundamentals_source
    assert by_rank["7203"]["fundamentalsAsOf"] == "2026-03-31"
    assert by_rank["6758"]["fundamentalsAsOf"] == "2026-03-31"
    assert by_rank["9984"]["fundamentalsAsOf"] == "2026-03-31"


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
    assert toyota["fundamentalsSource"] == "edinet_xbrl"
    assert snapshot.fundamentals_source == "edinet_xbrl"


def test_expanded_universe_recorded_caches_rank_complete_names(tmp_path: Path):
    universe = load_universe(UNIVERSE_PATH)
    tickers = [str(item["ticker"]) for item in universe["stocks"]]
    assert set(EDINET_TEN) <= set(tickers)
    assert "7974" in tickers
    snapshot = load_auto_snapshot(
        raw_dir=YAHOO_DIR,
        fundamentals_dir=FUND_DIR,
        jquants_dir=JQUANTS_DIR,
        jquants_bars_dir=BARS_DIR,
        edinet_dir=XBRL_DIR,
        fundamentals_path=tmp_path / "empty.json",
    )
    assert snapshot.price_source == "yahoo_chart"
    assert snapshot.meta()["priceLagNote"] is None
    assert [row["ticker"] for row in snapshot.stocks] == tickers
    extras = [row for row in snapshot.stocks if row["ticker"] not in CORE]
    assert len(extras) == len(tickers) - len(CORE)
    for stock in extras:
        assert stock["price"] is not None
        assert stock["price"] != 0
        assert stock["bookValue"] is not None
        assert stock["bookValue"] != 0
        assert stock["priceSource"] == "yahoo_chart"
        if stock["ticker"] in EDINET_COMPLETE:
            assert stock["latestRoe"] is not None
            assert stock["fundamentalsSource"] == "edinet_xbrl"
        elif stock["ticker"] in INCOMPLETE:
            assert stock["fundamentalsSource"] == "yahoo_timeseries"
        else:
            assert stock["latestRoe"] is not None
            assert stock["fundamentalsSource"] == "yahoo_timeseries"
    computed = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    by_ticker = {row["ticker"]: row for row in computed}
    ranked = [row["ticker"] for row in computed if row["rank"] is not None]
    assert EDINET_COMPLETE <= set(ranked)
    assert "8729" not in ranked
    for ticker in tickers:
        assert by_ticker[ticker]["price"] is not None
        assert by_ticker[ticker]["priceSource"] == "yahoo_chart"
        assert by_ticker[ticker]["priceAsOf"] is not None
        listed = ranking_row(by_ticker[ticker])
        assert listed["priceAsOf"] == by_ticker[ticker]["priceAsOf"]
        assert listed["fundamentalsAsOf"] == by_ticker[ticker]["fundamentalsAsOf"]
        if ticker in INCOMPLETE:
            assert by_ticker[ticker]["eligible"] is False
            assert by_ticker[ticker]["roeCount"] is None
            assert "missing_roe" in by_ticker[ticker]["exclusionReasons"]
            continue
        assert by_ticker[ticker]["eligible"] is True
        assert by_ticker[ticker]["bookValue"] is not None
        assert by_ticker[ticker]["returnCount"] >= 199
        assert by_ticker[ticker]["roeCount"] >= 3
        assert listed["roeCount"] == by_ticker[ticker]["roeCount"]
    for ticker in EDINET_COMPLETE:
        assert by_ticker[ticker]["fundamentalsSource"] == "edinet_xbrl"
    assert by_ticker["7974"]["fundamentalsSource"] == "edinet_xbrl"
    assert by_ticker["8766"]["fundamentalsSource"] == "edinet_xbrl"
    assert by_ticker["9983"]["fundamentalsSource"] == "edinet_xbrl"
    assert by_ticker["2914"]["fundamentalsSource"] == "yahoo_timeseries"
    assert by_ticker["6758"]["latestRoe"] < 0
    assert by_ticker["7267"]["latestRoe"] < 0
    assert by_ticker["7203"]["bookValue"] == pytest.approx(TOYOTA_BOOK)
    assert by_ticker["7203"]["priceAsOf"] == "2026-08-17"
    assert by_ticker["7203"]["fundamentalsAsOf"] == "2026-03-31"
    assert by_ticker["6861"]["fundamentalsAsOf"] == "2026-03-20"
    assert by_ticker["9432"]["price"] == pytest.approx(161.5)
    assert snapshot.fundamentals_source == "edinet_xbrl+yahoo_timeseries"


def test_names_without_cache_stay_ineligible_not_zero(tmp_path: Path):
    yahoo_dir = tmp_path / "yahoo"
    fund_dir = tmp_path / "fund"
    for name in ("_N225.json", "7203.T.json", "6758.T.json", "9984.T.json"):
        _copy_tree(YAHOO_DIR / name, yahoo_dir / name)
    for name in ("7203.T.json", "6758.T.json", "9984.T.json"):
        _copy_tree(FUND_DIR / name, fund_dir / name)
    snapshot = load_auto_snapshot(
        raw_dir=yahoo_dir,
        fundamentals_dir=fund_dir,
        jquants_dir=tmp_path / "no-jquants",
        jquants_bars_dir=tmp_path / "no-bars",
        edinet_dir=tmp_path / "no-edinet",
        fundamentals_path=tmp_path / "empty.json",
    )
    extras = [row for row in snapshot.stocks if row["ticker"] not in CORE]
    assert len(extras) == len(snapshot.stocks) - len(CORE)
    for stock in extras:
        assert stock["price"] is None
        assert stock["bookValue"] is None
        assert stock["priceSource"] is None
        assert stock["fundamentalsSource"] is None
        assert stock["sharesOutstanding"] is None
        assert stock["latestRoe"] is None
    computed = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    by_ticker = {row["ticker"]: row for row in computed}
    ranked = [row["ticker"] for row in computed if row["rank"] is not None]
    assert set(ranked) == CORE
    for ticker in EXTRAS:
        assert by_ticker[ticker]["eligible"] is False
        assert by_ticker[ticker]["bookValue"] is None
        assert by_ticker[ticker]["price"] is None
        listed = ranking_row(by_ticker[ticker])
        assert listed["priceSource"] is None
        assert listed["fundamentalsSource"] is None
        assert listed["returnCount"] is None
        assert listed["roeCount"] is None
        assert listed["priceAsOf"] is None
        assert listed["fundamentalsAsOf"] is None
        assert "missing_book_value" in by_ticker[ticker]["exclusionReasons"]
        assert "missing_price" in by_ticker[ticker]["exclusionReasons"]


def test_auto_skips_partial_edinet_for_complete_jquants(tmp_path: Path):
    edinet_dir = tmp_path / "edinet"
    yahoo_fund = tmp_path / "yahoo_fund"
    _write_partial_edinet(edinet_dir / "72030" / "instance.xbrl")
    _poison_yahoo(yahoo_fund / "7203.T.json")
    snapshot = load_auto_snapshot(
        universe_path=_toyota_universe(tmp_path / "universe.json"),
        raw_dir=YAHOO_DIR,
        fundamentals_dir=yahoo_fund,
        jquants_dir=JQUANTS_DIR,
        edinet_dir=edinet_dir,
        fundamentals_path=tmp_path / "empty.json",
    )
    toyota = next(row for row in snapshot.stocks if row["ticker"] == "7203")
    assert snapshot.fundamentals_source == "jquants_summary"
    assert toyota["bookValue"] == pytest.approx(TOYOTA_BOOK)
    assert toyota["bookValue"] != pytest.approx(POISON_BOOK)
    computed = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    ranked = next(row for row in computed if row["ticker"] == "7203")
    assert ranked["eligible"] is True


def test_auto_keeps_partial_when_no_complete_source(tmp_path: Path):
    edinet_dir = tmp_path / "edinet"
    _write_partial_edinet(edinet_dir / "72030" / "instance.xbrl")
    snapshot = load_auto_snapshot(
        universe_path=_toyota_universe(tmp_path / "universe.json"),
        raw_dir=YAHOO_DIR,
        fundamentals_dir=tmp_path / "no-yahoo",
        jquants_dir=tmp_path / "no-jquants",
        edinet_dir=edinet_dir,
        fundamentals_path=tmp_path / "empty.json",
    )
    toyota = next(row for row in snapshot.stocks if row["ticker"] == "7203")
    assert snapshot.fundamentals_source == "edinet_xbrl"
    assert toyota["bookValue"] == pytest.approx(POISON_BOOK)
    assert toyota["latestRoe"] is None
    assert toyota["sharesOutstanding"] is None
    computed = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    ranked = next(row for row in computed if row["ticker"] == "7203")
    assert ranked["eligible"] is False
    assert ranked["bookValue"] == pytest.approx(POISON_BOOK)
    assert "missing_shares_outstanding" in ranked["exclusionReasons"]
    assert "missing_roe" in ranked["exclusionReasons"]


def test_ineligible_extra_prices_do_not_change_core_scores(tmp_path: Path):
    overlay = tmp_path / "empty.json"
    fund_dir = tmp_path / "fund"
    for name in ("7203.T.json", "6758.T.json", "9984.T.json"):
        _copy_tree(FUND_DIR / name, fund_dir / name)
    jq_core = tmp_path / "jq_core"
    for name in ("72030.json", "67580.json", "99840.json"):
        _copy_tree(JQUANTS_DIR / name, jq_core / name)
    edinet_core = tmp_path / "edinet_core"
    for name in ("72030", "67580", "99840"):
        _copy_tree(XBRL_DIR / name, edinet_core / name)
    three = load_auto_snapshot(
        universe_path=_mini_universe(
            tmp_path / "universe.json",
            [("7203", "Toyota Motor"), ("6758", "Sony Group"), ("9984", "SoftBank Group")],
        ),
        raw_dir=YAHOO_DIR,
        fundamentals_dir=fund_dir,
        jquants_dir=jq_core,
        jquants_bars_dir=tmp_path / "no-bars",
        edinet_dir=edinet_core,
        fundamentals_path=overlay,
    )
    ten = load_auto_snapshot(
        raw_dir=YAHOO_DIR,
        fundamentals_dir=fund_dir,
        jquants_dir=jq_core,
        jquants_bars_dir=tmp_path / "no-bars",
        edinet_dir=edinet_core,
        fundamentals_path=overlay,
    )
    extras = [row for row in ten.stocks if row["ticker"] not in CORE]
    for stock in extras:
        assert stock["price"] is not None
        assert stock["price"] != 0
        assert stock["bookValue"] is None
        assert stock["priceSource"] == "yahoo_chart"
        assert stock["fundamentalsSource"] is None
    three_eval = {
        row["ticker"]: row for row in evaluate_universe(three.stocks, three.assumptions)
    }
    ten_eval = {row["ticker"]: row for row in evaluate_universe(ten.stocks, ten.assumptions)}
    for ticker in CORE:
        assert three_eval[ticker]["totalScore"] == pytest.approx(ten_eval[ticker]["totalScore"])
        assert three_eval[ticker]["rank"] == ten_eval[ticker]["rank"]
    ranked = [row["ticker"] for row in ten_eval.values() if row["rank"] is not None]
    assert set(ranked) == CORE

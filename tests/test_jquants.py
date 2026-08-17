from __future__ import annotations

import json
from pathlib import Path

import pytest

from models.pipeline import evaluate_universe
from providers.errors import BotWallError, FetchError, InvalidPriceDataError
from providers.http import fetch_jquants_summary_json, jquants_summary_url, redact_url
from providers.jquants_summary import parse_jquants_summary
from providers.loader import load_jquants_snapshot

ROOT = Path(__file__).resolve().parents[1]
YAHOO_DIR = ROOT / "tests" / "data" / "yahoo"
JQUANTS_DIR = ROOT / "tests" / "data" / "jquants"


def _fy(**fields):
    row = {
        "DiscDate": "2026-05-08",
        "DiscNo": "1",
        "Code": "72030",
        "DocType": "FYFinancialStatements_Consolidated_IFRS",
        "CurPerType": "FY",
        "CurPerEn": "2026-03-31",
        "NP": "100",
        "Eq": "1000",
        "ShEq": "1000",
        "ShOutFY": "100",
        "TrShFY": "0",
    }
    row.update(fields)
    return row


def test_jquants_toyota_units_and_beginning_roe():
    payload = json.loads((JQUANTS_DIR / "72030.json").read_text(encoding="utf-8"))
    fundamentals = parse_jquants_summary(payload, expected_code="72030")
    assert fundamentals.book_value == pytest.approx(39_918_854.0)
    assert fundamentals.shares_outstanding == pytest.approx(13_033.384474)
    assert fundamentals.fiscal_year_end == "2026-03-31"
    assert fundamentals.roe_history is not None
    assert len(fundamentals.roe_history) == 3
    expected_latest = 3_848_098_000_000.0 / 35_924_826_000_000.0
    assert fundamentals.latest_roe == pytest.approx(expected_latest)


def test_jquants_empty_profit_is_missing_not_zero():
    payload = {
        "data": [
            _fy(CurPerEn="2024-03-31", DiscDate="2024-05-01", NP="120", Eq="1000", ShEq="1000"),
            _fy(CurPerEn="2025-03-31", DiscDate="2025-05-01", NP="", Eq="1100", ShEq="1100"),
            _fy(CurPerEn="2026-03-31", DiscDate="2026-05-01", NP="150", Eq="1300", ShEq="1300"),
        ]
    }
    fundamentals = parse_jquants_summary(payload, expected_code="72030")
    assert fundamentals.book_value == pytest.approx(0.0013)
    assert fundamentals.roe_history is not None
    assert 0 not in fundamentals.roe_history
    # 2025 profit is missing, so that year is not a 0 ROE. 2026 still uses 2025 equity.
    assert len(fundamentals.roe_history) == 1
    assert fundamentals.roe_history[0] == pytest.approx(150 / 1100)


def test_jquants_missing_year_not_jumped():
    payload = {
        "data": [
            _fy(CurPerEn="2024-03-31", DiscDate="2024-05-01", NP="120", Eq="1000", ShEq="1000"),
            _fy(CurPerEn="2026-03-31", DiscDate="2026-05-01", NP="150", Eq="1300", ShEq="1300"),
        ]
    }
    fundamentals = parse_jquants_summary(payload, expected_code="72030")
    assert fundamentals.latest_roe is None
    assert fundamentals.roe_history is None


def test_jquants_quarterly_rows_ignored():
    payload = {
        "data": [
            _fy(CurPerType="3Q", CurPerEn="2025-12-31", NP="999", Eq="9999", ShEq="9999"),
            _fy(CurPerEn="2024-03-31", DiscDate="2024-05-01", NP="120", Eq="1000", ShEq="1000"),
            _fy(CurPerEn="2025-03-31", DiscDate="2025-05-01", NP="121", Eq="1100", ShEq="1100"),
            _fy(CurPerEn="2026-03-31", DiscDate="2026-05-01", NP="122", Eq="1200", ShEq="1200"),
        ]
    }
    fundamentals = parse_jquants_summary(payload, expected_code="72030")
    assert fundamentals.roe_history is not None
    assert len(fundamentals.roe_history) == 2
    assert 999 / 9999 not in fundamentals.roe_history


def test_jquants_prefers_consolidated_and_sheq():
    payload = {
        "data": [
            _fy(
                DocType="FYFinancialStatements_NonConsolidated_JGAAP",
                ShEq="1",
                Eq="1",
                NP="1",
            ),
            _fy(
                DocType="FYFinancialStatements_Consolidated_IFRS",
                DiscDate="2026-05-09",
                ShEq="2000000",
                Eq="9000000",
                NP="200000",
            ),
        ]
    }
    fundamentals = parse_jquants_summary(payload, expected_code="72030")
    assert fundamentals.book_value == pytest.approx(2.0)


def test_jquants_missing_treasury_leaves_shares_missing():
    payload = {"data": [_fy(TrShFY="")]}
    fundamentals = parse_jquants_summary(payload, expected_code="72030")
    assert fundamentals.shares_outstanding is None
    assert fundamentals.book_value == pytest.approx(0.001)


def test_jquants_negative_profit_not_zero():
    payload = json.loads((JQUANTS_DIR / "67580.json").read_text(encoding="utf-8"))
    fundamentals = parse_jquants_summary(payload, expected_code="67580")
    assert fundamentals.latest_roe is not None
    assert fundamentals.latest_roe < 0


def test_jquants_html_is_bot_wall():
    with pytest.raises(BotWallError):
        parse_jquants_summary("<html>verify</html>")


def test_jquants_missing_data_key_is_fetch_error():
    with pytest.raises(FetchError):
        parse_jquants_summary({"message": "Unauthorized"})


def test_fetch_jquants_requires_key_without_fetcher():
    with pytest.raises(FetchError, match="JQUANTS_API_KEY"):
        fetch_jquants_summary_json("72030", api_key="")


def test_fetch_jquants_does_not_hit_network_when_injected():
    def fake_fetch(url: str) -> tuple[int, str, str]:
        assert "72030" in url
        assert "fins/summary" in url
        return 200, "application/json", (JQUANTS_DIR / "72030.json").read_text(encoding="utf-8")

    payload = fetch_jquants_summary_json("72030", fetcher=fake_fetch)
    fundamentals = parse_jquants_summary(payload, expected_code="72030")
    assert fundamentals.book_value == pytest.approx(39_918_854.0)


def test_fetch_jquants_401_is_not_empty_fundamentals():
    def fake_fetch(url: str) -> tuple[int, str, str]:
        return 401, "application/json", json.dumps({"message": "Unauthorized"})

    with pytest.raises(FetchError, match="401"):
        fetch_jquants_summary_json("72030", fetcher=fake_fetch)


def test_fetch_jquants_follows_pagination_key():
    pages = {
        None: {
            "data": [_fy(CurPerEn="2025-03-31", NP="110", Eq="1000", ShEq="1000")],
            "pagination_key": "page-2",
        },
        "page-2": {
            "data": [_fy(CurPerEn="2026-03-31", NP="120", Eq="1100", ShEq="1100")],
        },
    }

    def fake_fetch(url: str) -> tuple[int, str, str]:
        key = None
        if "pagination_key=page-2" in url:
            key = "page-2"
        return 200, "application/json", json.dumps(pages[key])

    payload = fetch_jquants_summary_json("72030", fetcher=fake_fetch)
    assert len(payload["data"]) == 2


def test_redact_subscription_key():
    url = jquants_summary_url("72030")
    assert "72030" in url
    leaked = "https://api.edinet-fsa.go.jp/api/v2/documents.json?date=2026-01-01&Subscription-Key=secret"
    assert "secret" not in redact_url(leaked)
    assert "REDACTED" in redact_url(leaked)


def test_jquants_snapshot_ranks_with_recorded_files(tmp_path: Path):
    snapshot = load_jquants_snapshot(
        raw_dir=YAHOO_DIR,
        jquants_dir=JQUANTS_DIR,
        fetch=False,
        fundamentals_path=tmp_path / "empty.json",
    )
    assert snapshot.source == "jquants"
    assert snapshot.fundamentals_source == "jquants_summary"
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
    assert by_ticker["9984"]["eligible"] is True
    ranked = [row["ticker"] for row in computed if row["rank"] is not None]
    assert set(ranked) == {"7203", "6758", "9984"}


def test_jquants_without_summaries_stays_ineligible(tmp_path: Path):
    snapshot = load_jquants_snapshot(
        raw_dir=YAHOO_DIR,
        jquants_dir=tmp_path,
        fetch=False,
        fundamentals_path=tmp_path / "empty.json",
    )
    computed = evaluate_universe(snapshot.stocks, snapshot.assumptions)
    toyota = next(row for row in computed if row["ticker"] == "7203")
    assert toyota["price"] == pytest.approx(3013.0)
    assert toyota["eligible"] is False
    assert "missing_book_value" in toyota["exclusionReasons"]
    assert toyota["bookValue"] is None
    assert snapshot.fundamentals_source == "missing"


def test_jquants_invalid_payload_shape():
    with pytest.raises(InvalidPriceDataError):
        parse_jquants_summary(["not", "an", "object"])

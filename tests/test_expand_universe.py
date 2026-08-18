from __future__ import annotations

import json
from pathlib import Path

import pytest

from expand_universe import expand_universe, stocks_from_source_file, stocks_from_tickers
from providers.errors import FetchError
from providers.tse import listing_row, merge_listings, parse_tse_ticker

ROOT = Path(__file__).resolve().parents[1]
TOPIX_CORE30 = ROOT / "scripts" / "providers" / "topix_core30.json"
UNIVERSE = ROOT / "scripts" / "providers" / "universe.json"


def test_parse_tse_ticker_rejects_invalid():
    with pytest.raises(FetchError, match="invalid"):
        parse_tse_ticker("7974.T")
    with pytest.raises(FetchError, match="invalid"):
        parse_tse_ticker("123")


def test_listing_row_derives_provider_codes():
    row = listing_row("7974", "Nintendo")
    assert row == {
        "ticker": "7974",
        "yahooSymbol": "7974.T",
        "stooqSymbol": "7974.jp",
        "jquantsCode": "79740",
        "edinetSecCode": "79740",
        "companyName": "Nintendo",
    }


def test_merge_listings_keeps_existing_names():
    existing = [listing_row("7203", "Toyota Motor")]
    incoming = [listing_row("7203", "POISON"), listing_row("7974", "Nintendo")]
    merged, added = merge_listings(existing, incoming, keep_existing=True)
    assert [row["ticker"] for row in merged] == ["7203", "7974"]
    assert merged[0]["companyName"] == "Toyota Motor"
    assert added == ["7974"]


def test_topix_core30_source_is_recorded_not_empty():
    rows = stocks_from_source_file(TOPIX_CORE30)
    tickers = [row["ticker"] for row in rows]
    assert len(tickers) >= 30
    assert len(set(tickers)) == len(tickers)
    universe = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    have = {str(item["ticker"]) for item in universe["stocks"]}
    assert have <= set(tickers)
    assert "7974" in tickers
    assert "9983" in tickers


def test_expand_universe_dry_merge_does_not_write_public(tmp_path: Path):
    universe = {"stocks": [listing_row("7203", "Toyota Motor")]}
    incoming = stocks_from_tickers(["7974"], ["7974=Nintendo"])
    updated, added = expand_universe(universe, incoming)
    assert added == ["7974"]
    assert [row["ticker"] for row in universe["stocks"]] == ["7203"]
    assert [row["ticker"] for row in updated["stocks"]] == ["7203", "7974"]
    assert not (tmp_path / "public").exists()


def test_expand_universe_keep_existing_adds_none_when_already_listed():
    universe = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    incoming = stocks_from_source_file(TOPIX_CORE30)
    updated, added = expand_universe(universe, incoming)
    assert added == []
    assert [row["ticker"] for row in updated["stocks"]] == [
        row["ticker"] for row in universe["stocks"]
    ]


def test_stocks_from_tickers_requires_names():
    with pytest.raises(FetchError, match="company name missing"):
        stocks_from_tickers(["7974"], [])

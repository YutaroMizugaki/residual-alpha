"""TSE 4-digit listing codes. Yahoo / J-Quants / EDINET symbols are derived, not typed."""

from __future__ import annotations

from typing import Any

from providers.errors import FetchError


def parse_tse_ticker(raw: str) -> str:
    ticker = raw.strip()
    if len(ticker) != 4 or not ticker.isdigit():
        raise FetchError(f"TSE ticker is invalid: {raw}")
    return ticker


def listing_row(ticker: str, company_name: str) -> dict[str, str]:
    code = parse_tse_ticker(ticker)
    name = company_name.strip()
    if not name:
        raise FetchError(f"company name is missing for {code}")
    return {
        "ticker": code,
        "yahooSymbol": f"{code}.T",
        "stooqSymbol": f"{code}.jp",
        "jquantsCode": f"{code}0",
        "edinetSecCode": f"{code}0",
        "companyName": name,
    }


def merge_listings(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    *,
    keep_existing: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Append new listings. Duplicate tickers keep the current row when keep_existing."""
    by_ticker: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in existing:
        ticker = parse_tse_ticker(str(item["ticker"]))
        if ticker not in by_ticker:
            order.append(ticker)
        by_ticker[ticker] = dict(item)
        by_ticker[ticker]["ticker"] = ticker
    added: list[str] = []
    for item in incoming:
        ticker = parse_tse_ticker(str(item["ticker"]))
        if ticker in by_ticker:
            if keep_existing:
                continue
            by_ticker[ticker] = dict(item)
            by_ticker[ticker]["ticker"] = ticker
            continue
        by_ticker[ticker] = dict(item)
        by_ticker[ticker]["ticker"] = ticker
        order.append(ticker)
        added.append(ticker)
    return [by_ticker[ticker] for ticker in order], added

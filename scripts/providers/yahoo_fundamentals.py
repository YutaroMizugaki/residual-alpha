"""Yahoo fundamentals timeseries. Annual equity, income, and shares. No yfinance."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from providers.errors import BotWallError, FetchError, InvalidPriceDataError
from providers.fundamentals_common import (
    JPY_MILLION,
    Fundamentals,
    as_date,
    beginning_book_roes,
    pack_roes,
)

EQUITY_KEY = "annualStockholdersEquity"
INCOME_KEY = "annualNetIncomeCommonStockholders"
SHARES_KEY = "annualOrdinarySharesNumber"


def _raw_map(payload: dict[str, Any], key: str, *, require_jpy: bool) -> dict[date, float]:
    results = (payload.get("timeseries") or {}).get("result")
    if results is None:
        raise FetchError("Yahoo timeseries result is missing")
    if not isinstance(results, list):
        raise InvalidPriceDataError("Yahoo timeseries result is invalid")

    out: dict[date, float] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        rows = item.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            as_of = row.get("asOfDate")
            raw = (row.get("reportedValue") or {}).get("raw")
            if as_of is None or raw is None:
                continue
            if require_jpy and row.get("currencyCode") not in (None, "JPY"):
                raise InvalidPriceDataError(f"{key} currency is {row.get('currencyCode')}, not JPY")
            try:
                number = float(raw)
            except (TypeError, ValueError):
                continue
            if number != number:  # NaN
                continue
            out[as_date(str(as_of))] = number
    return out


def parse_yahoo_fundamentals(payload: Any) -> Fundamentals:
    if isinstance(payload, str):
        text = payload.lstrip()
        if text.startswith("<!") or text.startswith("<html"):
            raise BotWallError("Yahoo fundamentals returned HTML instead of JSON")
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise FetchError("Yahoo fundamentals payload is not JSON") from exc
    if not isinstance(payload, dict):
        raise InvalidPriceDataError("Yahoo fundamentals payload is not an object")
    if (payload.get("timeseries") or {}).get("error"):
        raise FetchError(f"Yahoo timeseries error: {payload['timeseries']['error']}")

    equity = _raw_map(payload, EQUITY_KEY, require_jpy=True)
    income = _raw_map(payload, INCOME_KEY, require_jpy=True)
    shares = _raw_map(payload, SHARES_KEY, require_jpy=False)

    book_value = None
    fiscal_year_end = None
    if equity:
        latest_eq_date = max(equity)
        latest_equity = equity[latest_eq_date]
        if latest_equity > 0:
            book_value = latest_equity / JPY_MILLION
            fiscal_year_end = latest_eq_date.isoformat()

    shares_outstanding = None
    if shares:
        latest_sh_date = max(shares)
        latest_shares = shares[latest_sh_date]
        if latest_shares > 0:
            shares_outstanding = latest_shares / JPY_MILLION

    roes = beginning_book_roes(equity, income)
    latest_roe, roe_history = pack_roes(roes)

    return Fundamentals(
        book_value=book_value,
        shares_outstanding=shares_outstanding,
        latest_roe=latest_roe,
        roe_history=roe_history,
        fiscal_year_end=fiscal_year_end,
    )

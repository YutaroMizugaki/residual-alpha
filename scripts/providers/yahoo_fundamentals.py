"""Yahoo fundamentals timeseries. Annual equity, income, and shares. No yfinance."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from providers.errors import BotWallError, FetchError, InvalidPriceDataError

JPY_MILLION = 1_000_000.0
EQUITY_KEY = "annualStockholdersEquity"
INCOME_KEY = "annualNetIncomeCommonStockholders"
SHARES_KEY = "annualOrdinarySharesNumber"
MIN_YEAR_DAYS = 300
MAX_YEAR_DAYS = 450


@dataclass(frozen=True)
class Fundamentals:
    book_value: float | None  # million JPY
    shares_outstanding: float | None  # million shares
    latest_roe: float | None
    roe_history: list[float] | None  # oldest → newest
    fiscal_year_end: str | None


def _as_date(value: str) -> date:
    return date.fromisoformat(value[:10])


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
            out[_as_date(str(as_of))] = number
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

    year_dates = sorted(set(equity) | set(income))
    roes: list[float] = []
    for prev, curr in zip(year_dates, year_dates[1:]):
        span = (curr - prev).days
        if span < MIN_YEAR_DAYS or span > MAX_YEAR_DAYS:
            continue
        beginning = equity.get(prev)
        net_income = income.get(curr)
        if beginning is None or net_income is None:
            continue
        if beginning <= 0:
            continue
        roes.append(net_income / beginning)

    latest_roe = roes[-1] if roes else None
    roe_history = roes[-3:] if roes else None

    return Fundamentals(
        book_value=book_value,
        shares_outstanding=shares_outstanding,
        latest_roe=latest_roe,
        roe_history=roe_history,
        fiscal_year_end=fiscal_year_end,
    )

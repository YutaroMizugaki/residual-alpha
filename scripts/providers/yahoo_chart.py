"""Parse Yahoo Finance chart JSON. This is not the yfinance package."""

from __future__ import annotations

import json
from typing import Any

from providers.errors import BotWallError, FetchError, InvalidPriceDataError
from providers.series import PriceSeries, exchange_date, series_from_pairs

REQUIRED_CURRENCY = "JPY"


def parse_yahoo_chart(payload: Any, *, expected_symbol: str | None = None) -> PriceSeries:
    if isinstance(payload, str):
        text = payload.lstrip()
        if text.startswith("<!") or text.startswith("<html"):
            raise BotWallError("Yahoo chart returned HTML instead of JSON")
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise FetchError("Yahoo chart payload is not JSON") from exc

    if not isinstance(payload, dict):
        raise InvalidPriceDataError("Yahoo chart payload is not an object")

    chart = payload.get("chart")
    if not isinstance(chart, dict):
        raise InvalidPriceDataError("Yahoo chart.chart is missing")
    if chart.get("error"):
        raise FetchError(f"Yahoo chart error: {chart.get('error')}")

    result = chart.get("result")
    if result is None:
        raise FetchError("Yahoo chart result is missing")
    if not isinstance(result, list) or not result:
        raise FetchError("Yahoo chart result is empty")

    first = result[0]
    if not isinstance(first, dict):
        raise InvalidPriceDataError("Yahoo chart result[0] is invalid")

    meta = first.get("meta") or {}
    symbol = str(meta.get("symbol") or expected_symbol or "")
    currency = meta.get("currency")
    if currency is not None and currency != REQUIRED_CURRENCY:
        raise InvalidPriceDataError(f"{symbol} currency is {currency}, not JPY")

    timestamps = first.get("timestamp")
    indicators = first.get("indicators") or {}
    quote = (indicators.get("quote") or [None])[0] or {}
    closes = quote.get("close")
    if not isinstance(timestamps, list) or not isinstance(closes, list):
        raise InvalidPriceDataError(f"{symbol} timestamp/close missing")
    if len(timestamps) != len(closes):
        raise InvalidPriceDataError(f"{symbol} timestamp/close length mismatch")

    gmtoffset = meta.get("gmtoffset")
    pairs: list[tuple] = []
    for ts, close in zip(timestamps, closes):
        if ts is None:
            continue
        pairs.append((exchange_date(int(ts), gmtoffset), close))

    series = series_from_pairs(symbol, currency, pairs)
    if not series.points:
        raise FetchError(f"{symbol} has no valid closes")
    return series

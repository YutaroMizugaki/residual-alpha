"""Parse Yahoo Finance chart JSON. This is not the yfinance package."""

from __future__ import annotations

import json
from typing import Any, Iterable

from providers.errors import BotWallError, FetchError, InvalidPriceDataError
from providers.series import PriceSeries, exchange_date, series_from_pairs

REQUIRED_CURRENCY = "JPY"
COMPACT_META_KEYS = (
    "currency",
    "symbol",
    "gmtoffset",
    "timezone",
    "exchangeName",
    "instrumentType",
    "regularMarketPrice",
)


def _chart_object(payload: Any) -> dict:
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
    return first


def valid_chart_closes(
    payload: Any, *, expected_symbol: str | None = None
) -> tuple[dict[str, Any], list[tuple[int, float]]]:
    """Timestamp/close pairs with null and non-positive closes dropped, not filled with 0."""
    first = _chart_object(payload)
    meta = first.get("meta") or {}
    if not isinstance(meta, dict):
        meta = {}
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

    pairs: list[tuple[int, float]] = []
    for ts, close in zip(timestamps, closes):
        if ts is None or close is None:
            continue
        try:
            value = float(close)
        except (TypeError, ValueError) as exc:
            raise InvalidPriceDataError(f"{symbol} close is not a number") from exc
        if value != value or value <= 0.0:
            continue
        pairs.append((int(ts), value))
    if not pairs:
        raise FetchError(f"{symbol} has no valid closes")
    return meta, pairs


def parse_yahoo_chart(payload: Any, *, expected_symbol: str | None = None) -> PriceSeries:
    meta, pairs = valid_chart_closes(payload, expected_symbol=expected_symbol)
    symbol = str(meta.get("symbol") or expected_symbol or "")
    currency = meta.get("currency")
    gmtoffset = meta.get("gmtoffset")
    date_pairs = [(exchange_date(ts, gmtoffset), close) for ts, close in pairs]
    series = series_from_pairs(symbol, currency, date_pairs)
    if not series.points:
        raise FetchError(f"{symbol} has no valid closes")
    return series


def compact_yahoo_chart(
    payload: Any,
    *,
    expected_symbol: str | None = None,
    keep_timestamps: Iterable[int] | None = None,
) -> dict[str, Any]:
    """Keep parseable timestamp + close. Drop unused fields, nulls, and non-positive closes."""
    meta, pairs = valid_chart_closes(payload, expected_symbol=expected_symbol)
    symbol = str(meta.get("symbol") or expected_symbol or "")
    if keep_timestamps is not None:
        by_ts = dict(pairs)
        pairs = [(int(ts), by_ts[int(ts)]) for ts in keep_timestamps if int(ts) in by_ts]
    if not pairs:
        raise FetchError(f"{symbol} has no valid closes")
    compact_meta = {
        key: meta[key] for key in COMPACT_META_KEYS if key in meta and meta[key] is not None
    }
    if "symbol" not in compact_meta and symbol:
        compact_meta["symbol"] = symbol
    return {
        "chart": {
            "result": [
                {
                    "meta": compact_meta,
                    "timestamp": [ts for ts, _ in pairs],
                    "indicators": {"quote": [{"close": [close for _, close in pairs]}]},
                }
            ],
            "error": None,
        }
    }


def common_chart_timestamps(
    payloads: Iterable[Any],
    *,
    expected_symbols: Iterable[str | None] | None = None,
) -> list[int]:
    """Inner-join valid timestamps. Missing days are dropped, not filled with 0."""
    items = list(payloads)
    symbols = list(expected_symbols) if expected_symbols is not None else [None] * len(items)
    if len(symbols) != len(items):
        raise InvalidPriceDataError("expected_symbols length does not match payloads")
    if not items:
        return []
    order: list[int] | None = None
    common: set[int] | None = None
    for payload, symbol in zip(items, symbols):
        _meta, pairs = valid_chart_closes(payload, expected_symbol=symbol)
        stamps = [ts for ts, _ in pairs]
        if order is None:
            order = stamps
        stamp_set = set(stamps)
        common = stamp_set if common is None else common & stamp_set
    if not order or not common:
        return []
    return [ts for ts in order if ts in common]


def compact_yahoo_charts(
    payloads: dict[str, Any],
    *,
    align: bool = False,
) -> dict[str, dict[str, Any]]:
    """Compact many chart payloads. Optional inner-join; missing days are not filled with 0."""
    keep = common_chart_timestamps(payloads.values()) if align else None
    if align and not keep:
        raise FetchError("aligned Yahoo charts have no common valid timestamps")
    return {
        name: compact_yahoo_chart(payload, keep_timestamps=keep)
        for name, payload in payloads.items()
    }

"""J-Quants v2 /equities/bars/daily. Adjusted close only. Missing stays missing."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from providers.errors import BotWallError, FetchError, InvalidPriceDataError
from providers.fundamentals_common import as_date, optional_float
from providers.jquants_summary import codes_match
from providers.series import PriceSeries, series_from_pairs


def parse_jquants_bars(payload: Any, *, expected_code: str | None = None) -> PriceSeries:
    if isinstance(payload, str):
        text = payload.lstrip()
        if text.startswith("<!") or text.startswith("<html"):
            raise BotWallError("J-Quants bars returned HTML instead of JSON")
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise FetchError("J-Quants bars payload is not JSON") from exc
    if not isinstance(payload, dict):
        raise InvalidPriceDataError("J-Quants bars payload is not an object")
    if payload.get("data") is None:
        raise FetchError("J-Quants bars data is missing")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise InvalidPriceDataError("J-Quants bars data is invalid")

    pairs: list[tuple[date, float | None]] = []
    symbol = expected_code or ""
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("Code") or "")
        if expected_code and not codes_match(code, expected_code):
            continue
        if not symbol:
            symbol = code
        raw_date = row.get("Date")
        if not raw_date:
            continue
        try:
            day = as_date(str(raw_date))
        except ValueError:
            continue
        # Split-adjusted close only. Unadjusted C is not mixed in.
        close = optional_float(row.get("AdjC"))
        pairs.append((day, close))

    series = series_from_pairs(symbol or expected_code or "", "JPY", pairs)
    if not series.points:
        raise FetchError(f"{symbol or expected_code or 'bars'} has no valid adjusted closes")
    return series


def compact_jquants_bars(payload: Any, *, expected_code: str | None = None) -> dict[str, Any]:
    """Keep Date + Code + AdjC. Drop unused fields, empty AdjC, and non-positive AdjC."""
    series = parse_jquants_bars(payload, expected_code=expected_code)
    if isinstance(payload, str):
        payload = json.loads(payload)
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise InvalidPriceDataError("J-Quants bars data is invalid")
    compact_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("Code") or "")
        if expected_code and not codes_match(code, expected_code):
            continue
        raw_date = row.get("Date")
        if not raw_date:
            continue
        close = optional_float(row.get("AdjC"))
        if close is None or close <= 0.0:
            continue
        compact_rows.append(
            {
                "Date": str(raw_date),
                "Code": code or expected_code or "",
                "AdjC": close,
            }
        )
    if not compact_rows:
        raise FetchError(f"{series.symbol} has no valid adjusted closes")
    return {"data": compact_rows}

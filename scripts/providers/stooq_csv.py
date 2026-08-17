"""Stooq daily CSV parser. Live HTML bot-walls are errors, not price 0."""

from __future__ import annotations

import csv
import io
from datetime import date

from providers.errors import BotWallError, InvalidPriceDataError
from providers.series import PriceSeries, series_from_pairs


def parse_stooq_csv(text: str, *, symbol: str) -> PriceSeries:
    stripped = text.lstrip()
    if stripped.startswith("<!") or stripped.startswith("<html") or "verify your browser" in stripped.lower():
        raise BotWallError("Stooq returned an HTML bot-wall instead of CSV")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise InvalidPriceDataError(f"{symbol} CSV has no header")
    fields = {name.strip(): name for name in reader.fieldnames}
    if "Date" not in fields or "Close" not in fields:
        raise InvalidPriceDataError(f"{symbol} CSV missing Date/Close columns")

    pairs: list[tuple[date, float | None]] = []
    for row in reader:
        raw_date = (row.get(fields["Date"]) or "").strip()
        raw_close = (row.get(fields["Close"]) or "").strip()
        if not raw_date:
            continue
        day = date.fromisoformat(raw_date)
        if raw_close == "" or raw_close == "-":
            pairs.append((day, None))
            continue
        pairs.append((day, float(raw_close)))

    series = series_from_pairs(symbol, "JPY", pairs)
    if not series.points:
        raise InvalidPriceDataError(f"{symbol} CSV has no valid closes")
    return series

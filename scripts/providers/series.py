"""Daily price series helpers. Missing closes stay missing; they are never 0."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from providers.errors import InvalidPriceDataError


@dataclass(frozen=True)
class PriceSeries:
    symbol: str
    currency: str | None
    points: tuple[tuple[date, float], ...]  # oldest → newest, no nulls

    def last(self) -> tuple[date, float] | None:
        if not self.points:
            return None
        return self.points[-1]


def exchange_date(timestamp: int, gmtoffset: int | None) -> date:
    offset = 0 if gmtoffset is None else int(gmtoffset)
    tz = timezone(timedelta(seconds=offset))
    return datetime.fromtimestamp(int(timestamp), tz=tz).date()


def series_from_pairs(
    symbol: str,
    currency: str | None,
    pairs: list[tuple[date, float | None]],
) -> PriceSeries:
    points: list[tuple[date, float]] = []
    for day, close in pairs:
        if close is None:
            continue
        try:
            value = float(close)
        except (TypeError, ValueError) as exc:
            raise InvalidPriceDataError(f"{symbol} close is not a number") from exc
        if value != value:  # NaN
            continue
        if value <= 0.0:
            # Listed JP equity closes of 0 are invalid, not "free".
            continue
        points.append((day, value))
    points.sort(key=lambda item: item[0])
    return PriceSeries(symbol=symbol, currency=currency, points=tuple(points))


def aligned_simple_returns(
    stock: PriceSeries,
    market: PriceSeries,
) -> tuple[list[float], list[float]]:
    """
    Inner-join on dates, then simple returns on consecutive common closes.

    Missing days are dropped, not filled with 0 or the previous close.
    """
    stock_map = dict(stock.points)
    market_map = dict(market.points)
    common = sorted(set(stock_map) & set(market_map))
    if len(common) < 2:
        return [], []

    stock_returns: list[float] = []
    market_returns: list[float] = []
    for prev_day, day in zip(common, common[1:]):
        prev_stock = stock_map[prev_day]
        prev_market = market_map[prev_day]
        stock_close = stock_map[day]
        market_close = market_map[day]
        if prev_stock <= 0.0 or prev_market <= 0.0:
            continue
        stock_returns.append(stock_close / prev_stock - 1.0)
        market_returns.append(market_close / prev_market - 1.0)
    return stock_returns, market_returns

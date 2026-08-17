"""Shared fundamentals types and beginning-book ROE. Missing stays missing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

JPY_MILLION = 1_000_000.0
MIN_YEAR_DAYS = 300
MAX_YEAR_DAYS = 450


@dataclass(frozen=True)
class Fundamentals:
    book_value: float | None  # million JPY
    shares_outstanding: float | None  # million shares
    latest_roe: float | None
    roe_history: list[float] | None  # oldest → newest
    fiscal_year_end: str | None


def as_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def optional_float(value: object) -> float | None:
    """Empty string / None / NaN → None. Numeric 0 is kept."""
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def beginning_book_roes(
    equity: dict[date, float],
    income: dict[date, float],
) -> list[float]:
    """ROE_t = NI_t / Equity_{t-1}. Do not jump a missing year or fill with 0."""
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
    return roes


def pack_roes(roes: list[float]) -> tuple[float | None, list[float] | None]:
    if not roes:
        return None, None
    return roes[-1], roes[-3:]

"""Normalized ROE and 10-year ROE fade toward cost of equity."""

from __future__ import annotations

import math

import numpy as np

from models.exceptions import (
    InsufficientHistoryError,
    InvalidInputError,
    MissingDataError,
)

NORMALIZED_ROE_LATEST_WEIGHT = 0.6
NORMALIZED_ROE_MEDIAN_WEIGHT = 0.4
NORMALIZED_ROE_MIN = -0.20
NORMALIZED_ROE_MAX = 0.40
FADE_YEARS = 10
STABLE_YEARS = 3


def _require_number(value: float | None, field: str) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        raise MissingDataError(field)
    return float(value)


def normalize_roe(
    latest_roe: float | None,
    roe_history: list[float] | None,
) -> float:
    """
    If at least 3 history observations exist (oldest → newest):

        roe_3y_median = median(last 3 years)
        normalized_roe = 0.6 * latest_roe + 0.4 * roe_3y_median

    Result is clipped to [-0.20, 0.40].
    History shorter than 3 years is insufficient — not filled with zeros.
    """
    latest = _require_number(latest_roe, "latest_roe")
    if roe_history is None:
        raise InsufficientHistoryError("roe_history is missing")

    history = [float(x) for x in roe_history]
    if any(math.isnan(x) for x in history):
        raise InvalidInputError("roe_history contains NaN")
    if len(history) < STABLE_YEARS:
        raise InsufficientHistoryError("need at least 3 years of ROE history")

    last_three = history[-STABLE_YEARS:]
    roe_3y_median = float(np.median(last_three))
    normalized = (
        NORMALIZED_ROE_LATEST_WEIGHT * latest
        + NORMALIZED_ROE_MEDIAN_WEIGHT * roe_3y_median
    )
    return float(np.clip(normalized, NORMALIZED_ROE_MIN, NORMALIZED_ROE_MAX))


def fade_roe(
    normalized_roe: float,
    cost_of_equity: float,
    years: int = FADE_YEARS,
) -> list[float]:
    """
    10-year ROE path.

    Year 1–3 = normalized_roe
    Year 10 = cost_of_equity
    Year 4–10 linear interpolation from Year 3 to Year 10.
    """
    nroe = _require_number(normalized_roe, "normalized_roe")
    ke = _require_number(cost_of_equity, "cost_of_equity")
    if years != FADE_YEARS:
        raise InvalidInputError("MVP fade path is fixed at 10 years")

    path = [0.0] * years
    path[0] = nroe
    path[1] = nroe
    path[2] = nroe

    # Year t=4..10: linear from year 3 (nroe) to year 10 (ke).
    fade_steps = years - STABLE_YEARS  # 7
    for year in range(STABLE_YEARS + 1, years + 1):
        weight = (year - STABLE_YEARS) / fade_steps
        path[year - 1] = nroe + (ke - nroe) * weight

    path[years - 1] = ke
    return path

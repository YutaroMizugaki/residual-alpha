"""Raw beta and Bloomberg-style adjusted beta."""

from __future__ import annotations

import numpy as np

from models.exceptions import (
    InsufficientHistoryError,
    InvalidInputError,
    MissingDataError,
)

ADJUSTED_BETA_RAW_WEIGHT = 0.67
ADJUSTED_BETA_PRIOR_WEIGHT = 0.33
ADJUSTED_BETA_PRIOR = 1.0
ADJUSTED_BETA_MIN = 0.3
ADJUSTED_BETA_MAX = 2.0


def calculate_raw_beta(
    stock_returns: list[float] | np.ndarray | None,
    market_returns: list[float] | np.ndarray | None,
) -> float:
    """
    beta_raw = cov(stock, market) / var(market)

    Covariance and variance use the same sample definition (ddof=1).
    Zero market variance is invalid — it is not returned as 0.
    """
    if stock_returns is None or market_returns is None:
        raise MissingDataError("returns")

    stock = np.asarray(stock_returns, dtype=float)
    market = np.asarray(market_returns, dtype=float)

    if stock.ndim != 1 or market.ndim != 1:
        raise InvalidInputError("returns must be 1-dimensional")
    if stock.size != market.size:
        raise InvalidInputError("stock and market return lengths differ")
    if stock.size < 2:
        raise InsufficientHistoryError("need at least 2 return observations")
    if np.any(np.isnan(stock)) or np.any(np.isnan(market)):
        raise InvalidInputError("returns contain NaN")

    market_variance = float(np.var(market, ddof=1))
    if market_variance <= 0.0 or np.isclose(market_variance, 0.0, rtol=0.0, atol=1e-18):
        raise InvalidInputError("market variance is zero")

    covariance = float(np.cov(stock, market, ddof=1)[0, 1])
    return covariance / market_variance


def calculate_adjusted_beta(beta_raw: float) -> float:
    """
    beta_adjusted = 0.67 * beta_raw + 0.33 * 1.0
    then clipped to [0.3, 2.0].
    """
    if beta_raw is None or (isinstance(beta_raw, float) and np.isnan(beta_raw)):
        raise MissingDataError("beta_raw")

    adjusted = ADJUSTED_BETA_RAW_WEIGHT * float(beta_raw) + (
        ADJUSTED_BETA_PRIOR_WEIGHT * ADJUSTED_BETA_PRIOR
    )
    return float(np.clip(adjusted, ADJUSTED_BETA_MIN, ADJUSTED_BETA_MAX))

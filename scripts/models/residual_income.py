"""Residual income model, book-value roll-forward, and intrinsic value."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from models.exceptions import InvalidInputError, MissingDataError

DEFAULT_RETENTION_RATIO = 0.50
FORECAST_YEARS = 10


def _require_number(value: float | None, field: str) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        raise MissingDataError(field)
    return float(value)


def residual_income(
    beginning_book_value: float,
    roe: float,
    cost_of_equity: float,
) -> tuple[float, float, float]:
    """
    Returns (net_income, equity_charge, residual_income).

    Net Income      = ROE × Beginning Book Value
    Equity Charge   = Cost of Equity × Beginning Book Value
    Residual Income = Net Income - Equity Charge
                    = (ROE - Cost of Equity) × Beginning Book Value
    """
    bv = _require_number(beginning_book_value, "beginning_book_value")
    roe_v = _require_number(roe, "roe")
    ke = _require_number(cost_of_equity, "cost_of_equity")

    net_income = roe_v * bv
    equity_charge = ke * bv
    ri = net_income - equity_charge
    return net_income, equity_charge, ri


def ending_book_value(
    beginning_book_value: float,
    net_income: float,
    retention_ratio: float = DEFAULT_RETENTION_RATIO,
) -> tuple[float, float]:
    """
    Retention ratio is the share of earnings kept in the firm, not the payout.

    Dividend            = Net Income × (1 - Retention Ratio)
    Ending Book Value   = Beginning Book Value + Net Income - Dividend
                        = Beginning Book Value + Net Income × Retention Ratio
    """
    bv = _require_number(beginning_book_value, "beginning_book_value")
    ni = _require_number(net_income, "net_income")
    rr = _require_number(retention_ratio, "retention_ratio")
    if not 0.0 <= rr <= 1.0:
        raise InvalidInputError("retention_ratio must be in [0, 1]")

    dividend = ni * (1.0 - rr)
    ending = bv + ni - dividend
    return dividend, ending


def discount_factor(cost_of_equity: float, year: int) -> float:
    """Year t residual income is discounted by (1+ke)^t. Year 1 uses t=1, not t=0."""
    ke = _require_number(cost_of_equity, "cost_of_equity")
    if year < 1:
        raise InvalidInputError("forecast year must be >= 1")
    return 1.0 / ((1.0 + ke) ** year)


def intrinsic_price(intrinsic_equity_value: float, shares_outstanding: float) -> float:
    iev = _require_number(intrinsic_equity_value, "intrinsic_equity_value")
    shares = _require_number(shares_outstanding, "shares_outstanding")
    if shares == 0.0:
        raise InvalidInputError("shares_outstanding is zero")
    return iev / shares


def intrinsic_upside(intrinsic_price_value: float, current_price: float) -> float:
    ip = _require_number(intrinsic_price_value, "intrinsic_price")
    price = _require_number(current_price, "price")
    if price == 0.0:
        raise InvalidInputError("price is zero")
    return ip / price - 1.0


@dataclass
class ForecastYear:
    year: int
    beginning_book_value: float
    roe: float
    net_income: float
    equity_charge: float
    residual_income: float
    discount_factor: float
    pv_residual_income: float
    dividend: float
    ending_book_value: float

    def to_json(self) -> dict:
        return {
            "year": self.year,
            "beginningBookValue": self.beginning_book_value,
            "roe": self.roe,
            "netIncome": self.net_income,
            "equityCharge": self.equity_charge,
            "residualIncome": self.residual_income,
            "discountFactor": self.discount_factor,
            "pvResidualIncome": self.pv_residual_income,
            "dividend": self.dividend,
            "endingBookValue": self.ending_book_value,
        }


@dataclass
class ResidualIncomeResult:
    current_book_value: float
    pv_residual_income_sum: float
    intrinsic_equity_value: float
    forecast: list[ForecastYear] = field(default_factory=list)


def residual_income_model(
    current_book_value: float,
    roe_path: list[float],
    cost_of_equity: float,
    retention_ratio: float = DEFAULT_RETENTION_RATIO,
) -> ResidualIncomeResult:
    """
    Intrinsic Equity Value = Current Book Value + Σ PV(Residual Income)
    Terminal value is 0. Current book value is added once.
    """
    bv0 = _require_number(current_book_value, "book_value")
    ke = _require_number(cost_of_equity, "cost_of_equity")
    if not roe_path:
        raise InvalidInputError("roe_path is empty")
    if len(roe_path) != FORECAST_YEARS:
        raise InvalidInputError("MVP residual income path is 10 years")

    beginning = bv0
    pv_sum = 0.0
    forecast: list[ForecastYear] = []

    for year, roe in enumerate(roe_path, start=1):
        net_income, equity_charge, ri = residual_income(beginning, roe, ke)
        dividend, ending = ending_book_value(beginning, net_income, retention_ratio)
        df = discount_factor(ke, year)
        pv = ri * df
        pv_sum += pv
        forecast.append(
            ForecastYear(
                year=year,
                beginning_book_value=beginning,
                roe=roe,
                net_income=net_income,
                equity_charge=equity_charge,
                residual_income=ri,
                discount_factor=df,
                pv_residual_income=pv,
                dividend=dividend,
                ending_book_value=ending,
            )
        )
        beginning = ending

    # Terminal value = 0. Do not add current book value twice.
    iev = bv0 + pv_sum
    return ResidualIncomeResult(
        current_book_value=bv0,
        pv_residual_income_sum=pv_sum,
        intrinsic_equity_value=iev,
        forecast=forecast,
    )

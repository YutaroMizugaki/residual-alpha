"""CAPM cost of equity. Rates are decimals (0.065 = 6.5%)."""

from __future__ import annotations

import math

from models.exceptions import InvalidInputError, MissingDataError


def calculate_cost_of_equity(
    risk_free_rate: float,
    beta: float,
    equity_risk_premium: float,
) -> float:
    """ke = rf + beta * ERP"""
    for name, value in (
        ("risk_free_rate", risk_free_rate),
        ("beta", beta),
        ("equity_risk_premium", equity_risk_premium),
    ):
        if value is None or (isinstance(value, float) and math.isnan(value)):
            raise MissingDataError(name)

    ke = float(risk_free_rate) + float(beta) * float(equity_risk_premium)
    if math.isnan(ke):
        raise InvalidInputError("cost of equity is not a number")
    return ke

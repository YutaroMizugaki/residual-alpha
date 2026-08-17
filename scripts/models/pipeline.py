"""Evaluate one fixture stock. Missing inputs stay missing; they are never 0."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from models.beta import calculate_adjusted_beta, calculate_raw_beta
from models.capm import calculate_cost_of_equity
from models.exceptions import (
    STATUS_INSUFFICIENT_HISTORY,
    STATUS_INVALID,
    STATUS_MISSING,
    STATUS_VALID,
    InsufficientHistoryError,
    InvalidInputError,
    MissingDataError,
    QuantError,
)
from models.residual_income import (
    DEFAULT_RETENTION_RATIO,
    intrinsic_price,
    intrinsic_upside,
    residual_income_model,
)
from models.roe import fade_roe, normalize_roe
from models.scoring import apply_scores


def optional_number(value: Any, field: str) -> tuple[float | None, str | None]:
    """Return (number, exclusion_reason). Explicit 0 is kept; None/NaN is missing."""
    if value is None:
        return None, f"missing_{field}"
    if isinstance(value, str) and value.strip() == "":
        return None, f"missing_{field}"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, f"invalid_{field}"
    if math.isnan(number):
        return None, f"missing_{field}"
    return number, None


def _optional_float_list(value: Any) -> list[float] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        return None
    out: list[float] = []
    for item in value:
        if item is None:
            return None
        out.append(float(item))
    if any(math.isnan(x) for x in out):
        return None
    return out


def evaluate_stock(stock: dict, assumptions: dict) -> dict:
    reasons: list[str] = []
    rf = float(assumptions["riskFreeRate"])
    erp = float(assumptions["equityRiskPremium"])
    retention = float(assumptions.get("retentionRatio", DEFAULT_RETENTION_RATIO))
    market_returns = assumptions.get("marketReturns")

    price, reason = optional_number(stock.get("price"), "price")
    if reason:
        reasons.append(reason)

    book_value, reason = optional_number(stock.get("bookValue"), "book_value")
    if reason:
        reasons.append(reason)

    shares, reason = optional_number(stock.get("sharesOutstanding"), "shares_outstanding")
    if reason:
        reasons.append(reason)
    elif shares == 0.0:
        reasons.append("invalid_shares_outstanding")

    latest_roe, roe_reason = optional_number(stock.get("latestRoe"), "roe")
    roe_history = _optional_float_list(stock.get("roeHistory"))
    stock_returns = _optional_float_list(stock.get("stockReturns"))
    market_returns = _optional_float_list(stock.get("marketReturns"))
    if market_returns is None:
        market_returns = _optional_float_list(assumptions.get("marketReturns"))
    price_as_of = stock.get("priceAsOf")

    beta_raw = None
    beta_adjusted = None
    beta_status = STATUS_MISSING
    try:
        beta_raw = calculate_raw_beta(stock_returns, market_returns)
        beta_adjusted = calculate_adjusted_beta(beta_raw)
        beta_status = STATUS_VALID
    except MissingDataError:
        beta_status = STATUS_MISSING
        reasons.append("missing_returns")
    except InsufficientHistoryError:
        beta_status = STATUS_INSUFFICIENT_HISTORY
        reasons.append("insufficient_return_history")
    except InvalidInputError:
        beta_status = STATUS_INVALID
        reasons.append("invalid_returns")

    cost_of_equity = None
    if beta_adjusted is not None:
        cost_of_equity = calculate_cost_of_equity(rf, beta_adjusted, erp)

    normalized_roe = None
    normalized_roe_status = STATUS_MISSING
    try:
        if roe_reason:
            raise MissingDataError("latest_roe")
        normalized_roe = normalize_roe(latest_roe, roe_history)
        normalized_roe_status = STATUS_VALID
    except MissingDataError:
        normalized_roe_status = STATUS_MISSING
        reasons.append("missing_roe")
    except InsufficientHistoryError:
        normalized_roe_status = STATUS_INSUFFICIENT_HISTORY
        reasons.append("insufficient_roe_history")
    except InvalidInputError:
        normalized_roe_status = STATUS_INVALID
        reasons.append("invalid_roe")

    excess_roe = None
    if normalized_roe is not None and cost_of_equity is not None:
        excess_roe = normalized_roe - cost_of_equity

    earnings_yield = None
    pb_discount = None
    if (
        latest_roe is not None
        and book_value is not None
        and price is not None
        and shares is not None
        and price != 0.0
        and shares != 0.0
    ):
        market_cap = price * shares
        earnings_yield = (latest_roe * book_value) / market_cap
        book_value_per_share = book_value / shares
        price_to_book = price / book_value_per_share
        pb_discount = 1.0 - price_to_book

    roe_volatility = None
    if roe_history is not None and len(roe_history) >= 2:
        roe_volatility = float(np.std(roe_history, ddof=1))

    price_volatility = None
    if stock_returns is not None and len(stock_returns) >= 2:
        price_volatility = float(np.std(stock_returns, ddof=1))

    forecast: list[dict] = []
    iev = None
    ip = None
    upside = None
    valuation_ready = (
        book_value is not None
        and shares is not None
        and shares != 0.0
        and price is not None
        and price != 0.0
        and cost_of_equity is not None
        and normalized_roe is not None
    )
    if valuation_ready:
        try:
            roe_path = fade_roe(normalized_roe, cost_of_equity)
            model = residual_income_model(
                current_book_value=book_value,
                roe_path=roe_path,
                cost_of_equity=cost_of_equity,
                retention_ratio=retention,
            )
            iev = model.intrinsic_equity_value
            ip = intrinsic_price(iev, shares)
            upside = intrinsic_upside(ip, price)
            forecast = [year.to_json() for year in model.forecast]
        except QuantError as exc:
            reasons.append(f"valuation_error:{exc}")
            valuation_ready = False

    # Unique, stable reason order.
    unique_reasons = list(dict.fromkeys(reasons))
    eligible = valuation_ready and len(unique_reasons) == 0

    return {
        "ticker": str(stock["ticker"]),
        "companyName": str(stock["companyName"]),
        "eligible": eligible,
        "exclusionReasons": unique_reasons,
        "price": price,
        "priceAsOf": price_as_of if isinstance(price_as_of, str) else None,
        "bookValue": book_value,
        "sharesOutstanding": shares,
        "betaRaw": beta_raw,
        "betaAdjusted": beta_adjusted,
        "betaStatus": beta_status,
        "riskFreeRate": rf,
        "equityRiskPremium": erp,
        "costOfEquity": cost_of_equity,
        "latestRoe": latest_roe,
        "normalizedRoe": normalized_roe,
        "normalizedRoeStatus": normalized_roe_status,
        "excessRoe": excess_roe,
        "earningsYield": earnings_yield,
        "pbDiscount": pb_discount,
        "roeVolatility": roe_volatility,
        "priceVolatility": price_volatility,
        "intrinsicEquityValue": iev,
        "intrinsicPrice": ip,
        "intrinsicUpside": upside,
        "forecast": forecast,
        # scoring inputs (internal names used by apply_scores)
        "intrinsic_upside": upside,
        "earnings_yield": earnings_yield,
        "pb_discount": pb_discount,
        "excess_roe": excess_roe,
        "roe_volatility": roe_volatility,
        "price_volatility": price_volatility,
        "beta_adjusted": beta_adjusted,
        "valuationScore": None,
        "qualityScore": None,
        "riskScore": None,
        "totalScore": None,
        "rank": None,
    }


def _round(value: float | None, digits: int) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def ranking_row(stock: dict) -> dict:
    return {
        "rank": stock["rank"],
        "ticker": stock["ticker"],
        "companyName": stock["companyName"],
        "price": _round(stock["price"], 4),
        "intrinsicPrice": _round(stock["intrinsicPrice"], 4),
        "intrinsicUpside": _round(stock["intrinsicUpside"], 8),
        "betaAdjusted": _round(stock["betaAdjusted"], 8),
        "costOfEquity": _round(stock["costOfEquity"], 8),
        "normalizedRoe": _round(stock["normalizedRoe"], 8),
        "excessRoe": _round(stock["excessRoe"], 8),
        "valuationScore": _round(stock["valuationScore"], 2),
        "qualityScore": _round(stock["qualityScore"], 2),
        "riskScore": _round(stock["riskScore"], 2),
        "totalScore": _round(stock["totalScore"], 2),
        "eligible": stock["eligible"],
        "exclusionReasons": stock["exclusionReasons"],
    }


def _round_forecast(forecast: list[dict]) -> list[dict]:
    rounded = []
    for item in forecast:
        rounded.append(
            {
                "year": item["year"],
                "beginningBookValue": _round(item["beginningBookValue"], 6),
                "roe": _round(item["roe"], 8),
                "netIncome": _round(item["netIncome"], 6),
                "equityCharge": _round(item["equityCharge"], 6),
                "residualIncome": _round(item["residualIncome"], 6),
                "discountFactor": _round(item["discountFactor"], 10),
                "pvResidualIncome": _round(item["pvResidualIncome"], 6),
                "dividend": _round(item["dividend"], 6),
                "endingBookValue": _round(item["endingBookValue"], 6),
            }
        )
    return rounded


def detail_row(stock: dict) -> dict:
    return {
        "ticker": stock["ticker"],
        "companyName": stock["companyName"],
        "price": _round(stock["price"], 4),
        "priceAsOf": stock.get("priceAsOf"),
        "betaRaw": _round(stock["betaRaw"], 8),
        "betaAdjusted": _round(stock["betaAdjusted"], 8),
        "betaStatus": stock["betaStatus"],
        "riskFreeRate": _round(stock["riskFreeRate"], 8),
        "equityRiskPremium": _round(stock["equityRiskPremium"], 8),
        "costOfEquity": _round(stock["costOfEquity"], 8),
        "latestRoe": _round(stock["latestRoe"], 8),
        "normalizedRoe": _round(stock["normalizedRoe"], 8),
        "normalizedRoeStatus": stock["normalizedRoeStatus"],
        "excessRoe": _round(stock["excessRoe"], 8),
        "bookValue": _round(stock["bookValue"], 6),
        "sharesOutstanding": _round(stock["sharesOutstanding"], 6),
        "intrinsicEquityValue": _round(stock["intrinsicEquityValue"], 6),
        "intrinsicPrice": _round(stock["intrinsicPrice"], 4),
        "intrinsicUpside": _round(stock["intrinsicUpside"], 8),
        "valuationScore": _round(stock["valuationScore"], 2),
        "qualityScore": _round(stock["qualityScore"], 2),
        "riskScore": _round(stock["riskScore"], 2),
        "totalScore": _round(stock["totalScore"], 2),
        "eligible": stock["eligible"],
        "exclusionReasons": stock["exclusionReasons"],
        "forecast": _round_forecast(stock["forecast"]),
    }


def evaluate_universe(stocks: list[dict], assumptions: dict) -> list[dict]:
    computed = [evaluate_stock(stock, assumptions) for stock in stocks]
    eligible = [row for row in computed if row["eligible"]]
    scored_eligible = apply_scores(eligible)
    scored_by_ticker = {row["ticker"]: row for row in scored_eligible}

    merged: list[dict] = []
    for row in computed:
        if row["ticker"] in scored_by_ticker:
            scored = scored_by_ticker[row["ticker"]]
            row = {
                **row,
                "valuationScore": scored["valuation_score"],
                "qualityScore": scored["quality_score"],
                "riskScore": scored["risk_score"],
                "totalScore": scored["total_score"],
            }
        merged.append(row)

    ranked = [row for row in merged if row["eligible"] and row["totalScore"] is not None]
    ranked.sort(key=lambda row: (-float(row["totalScore"]), row["ticker"]))
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    return merged

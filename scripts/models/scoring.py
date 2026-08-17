"""Composite scoring. Missing metrics are never scored as zero.

Within each category, weights of available metrics are redistributed
proportionally. High beta is penalized; it is never treated as a
higher-is-better percentile.
"""

from __future__ import annotations

from typing import Iterable

VALUATION_WEIGHTS = {
    "intrinsic_upside": 30.0,
    "earnings_yield": 10.0,
    "pb_discount": 10.0,
}
QUALITY_WEIGHTS = {
    "excess_roe": 20.0,
    "roe_stability": 10.0,
}
RISK_WEIGHTS = {
    "beta": 10.0,
    "volatility": 10.0,
}

VALUATION_TOTAL = sum(VALUATION_WEIGHTS.values())  # 50
QUALITY_TOTAL = sum(QUALITY_WEIGHTS.values())  # 30
RISK_TOTAL = sum(RISK_WEIGHTS.values())  # 20


def percentile_rank(value: float, universe: list[float]) -> float:
    """0–100 rank. Minimum maps to 0, maximum to 100. Single observation → 50."""
    n = len(universe)
    if n == 0:
        raise ValueError("percentile universe is empty")
    if n == 1:
        return 50.0
    n_less_or_equal = sum(1 for item in universe if item <= value)
    return 100.0 * (n_less_or_equal - 1) / (n - 1)


def oriented_percentile(
    value: float,
    universe: list[float],
    *,
    higher_is_better: bool,
) -> float:
    rank = percentile_rank(value, universe)
    if higher_is_better:
        return rank
    return 100.0 - rank


def beta_quality_score(beta: float) -> float:
    """
    0–100 quality of beta. Peak at beta = 1.0.
    Beta above 1.0 is penalized. High beta is never rewarded.
    """
    if beta <= 1.0:
        return 100.0 - 15.0 * (1.0 - beta)
    return max(0.0, 100.0 - 100.0 * (beta - 1.0))


def redistribute_weights(
    weights: dict[str, float],
    available_keys: Iterable[str],
) -> dict[str, float]:
    present = {key: weights[key] for key in weights if key in set(available_keys)}
    if not present:
        return {}
    present_sum = sum(present.values())
    category_total = sum(weights.values())
    return {key: category_total * (weight / present_sum) for key, weight in present.items()}


def category_points(
    percentiles: dict[str, float | None],
    weights: dict[str, float],
) -> float | None:
    available = {key: pct for key, pct in percentiles.items() if pct is not None and key in weights}
    redistributed = redistribute_weights(weights, available.keys())
    if not redistributed:
        return None
    points = 0.0
    for key, weight in redistributed.items():
        points += (available[key] / 100.0) * weight
    return points


def collect_universe(rows: list[dict], key: str) -> list[float]:
    return [row[key] for row in rows if row.get(key) is not None]


def apply_scores(rows: list[dict]) -> list[dict]:
    """
    Attach valuationScore, qualityScore, riskScore, totalScore.
    Input rows must already contain metric fields (None if unavailable).
    """
    upside_u = collect_universe(rows, "intrinsic_upside")
    ey_u = collect_universe(rows, "earnings_yield")
    pb_u = collect_universe(rows, "pb_discount")
    excess_u = collect_universe(rows, "excess_roe")
    roe_vol_u = collect_universe(rows, "roe_volatility")
    price_vol_u = collect_universe(rows, "price_volatility")

    scored: list[dict] = []
    for row in rows:
        valuation_pcts = {
            "intrinsic_upside": (
                oriented_percentile(row["intrinsic_upside"], upside_u, higher_is_better=True)
                if row.get("intrinsic_upside") is not None and upside_u
                else None
            ),
            "earnings_yield": (
                oriented_percentile(row["earnings_yield"], ey_u, higher_is_better=True)
                if row.get("earnings_yield") is not None and ey_u
                else None
            ),
            "pb_discount": (
                oriented_percentile(row["pb_discount"], pb_u, higher_is_better=True)
                if row.get("pb_discount") is not None and pb_u
                else None
            ),
        }
        quality_pcts = {
            "excess_roe": (
                oriented_percentile(row["excess_roe"], excess_u, higher_is_better=True)
                if row.get("excess_roe") is not None and excess_u
                else None
            ),
            "roe_stability": (
                oriented_percentile(row["roe_volatility"], roe_vol_u, higher_is_better=False)
                if row.get("roe_volatility") is not None and roe_vol_u
                else None
            ),
        }

        beta_pct = (
            beta_quality_score(row["beta_adjusted"])
            if row.get("beta_adjusted") is not None
            else None
        )
        vol_pct = (
            oriented_percentile(row["price_volatility"], price_vol_u, higher_is_better=False)
            if row.get("price_volatility") is not None and price_vol_u
            else None
        )
        risk_pcts = {
            "beta": beta_pct,
            "volatility": vol_pct,
        }

        valuation = category_points(valuation_pcts, VALUATION_WEIGHTS)
        quality = category_points(quality_pcts, QUALITY_WEIGHTS)
        risk = category_points(risk_pcts, RISK_WEIGHTS)

        if valuation is None or quality is None or risk is None:
            row = {
                **row,
                "valuation_score": None,
                "quality_score": None,
                "risk_score": None,
                "total_score": None,
                "score_eligible": False,
            }
        else:
            row = {
                **row,
                "valuation_score": valuation,
                "quality_score": quality,
                "risk_score": risk,
                "total_score": valuation + quality + risk,
                "score_eligible": True,
            }
        scored.append(row)
    return scored

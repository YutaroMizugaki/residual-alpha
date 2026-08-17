import pytest

from models.exceptions import MissingDataError
from models.pipeline import evaluate_stock, evaluate_universe
from models.residual_income import residual_income_model
from models.scoring import apply_scores, beta_quality_score, oriented_percentile


def test_high_upside_scores_higher():
    high = oriented_percentile(0.40, [0.10, 0.40], higher_is_better=True)
    low = oriented_percentile(0.10, [0.10, 0.40], higher_is_better=True)
    assert high > low


def test_lower_volatility_scores_higher():
    low_vol = oriented_percentile(0.10, [0.10, 0.40], higher_is_better=False)
    high_vol = oriented_percentile(0.40, [0.10, 0.40], higher_is_better=False)
    assert low_vol > high_vol


def test_high_beta_not_rewarded():
    near_one = beta_quality_score(1.0)
    high = beta_quality_score(1.8)
    very_high = beta_quality_score(2.0)
    assert near_one > high
    assert high > very_high
    assert high < near_one

    rows = apply_scores(
        [
            {
                "intrinsic_upside": 0.10,
                "earnings_yield": 0.08,
                "pb_discount": 0.0,
                "excess_roe": 0.02,
                "roe_volatility": 0.01,
                "price_volatility": 0.02,
                "beta_adjusted": 0.9,
            },
            {
                "intrinsic_upside": 0.10,
                "earnings_yield": 0.08,
                "pb_discount": 0.0,
                "excess_roe": 0.02,
                "roe_volatility": 0.01,
                "price_volatility": 0.02,
                "beta_adjusted": 1.8,
            },
        ]
    )
    assert rows[0]["risk_score"] > rows[1]["risk_score"]
    assert rows[0]["total_score"] > rows[1]["total_score"]


def test_missing_metric_not_scored_as_zero():
    rows = apply_scores(
        [
            {
                "intrinsic_upside": 0.20,
                "earnings_yield": 0.10,
                "pb_discount": None,
                "excess_roe": 0.05,
                "roe_volatility": 0.01,
                "price_volatility": 0.02,
                "beta_adjusted": 1.0,
            }
        ]
    )
    # P/B weight is redistributed inside Valuation (50). Score is not 40/50.
    assert rows[0]["valuation_score"] is not None
    assert rows[0]["valuation_score"] == pytest.approx(25.0)
    assert rows[0]["valuation_score"] != pytest.approx(20.0)


def test_missing_data_not_zero():
    stock = {
        "ticker": "1006",
        "companyName": "Missing Data",
        "price": None,
        "bookValue": None,
        "sharesOutstanding": None,
        "latestRoe": None,
        "roeHistory": None,
        "stockReturns": None,
    }
    assumptions = {
        "riskFreeRate": 0.015,
        "equityRiskPremium": 0.05,
        "retentionRatio": 0.50,
        "marketReturns": [0.01, 0.02, -0.01],
    }
    result = evaluate_stock(stock, assumptions)
    assert result["eligible"] is False
    assert "missing_book_value" in result["exclusionReasons"]
    assert result["bookValue"] is None
    assert result["intrinsicEquityValue"] is None
    assert result["intrinsicPrice"] is None
    assert 0 not in (
        result["bookValue"],
        result["intrinsicEquityValue"],
        result["betaRaw"],
        result["normalizedRoe"],
    )
    with pytest.raises(MissingDataError):
        residual_income_model(None, [0.1] * 10, 0.1)  # type: ignore[arg-type]


def test_stable_industries_intrinsic_near_book():
    stock = {
        "ticker": "1002",
        "companyName": "Stable Industries",
        "price": 1000,
        "bookValue": 100000,
        "sharesOutstanding": 100,
        "latestRoe": 0.065,
        "roeHistory": [0.065, 0.065, 0.065],
        "stockReturns": [0.01, 0.02, -0.01, 0.015],
    }
    market = [0.01, 0.02, -0.01, 0.015]
    assumptions = {
        "riskFreeRate": 0.015,
        "equityRiskPremium": 0.05,
        "retentionRatio": 0.50,
        "marketReturns": market,
    }
    result = evaluate_stock(stock, assumptions)
    assert result["eligible"] is True
    assert result["costOfEquity"] == pytest.approx(0.065)
    assert result["normalizedRoe"] == pytest.approx(0.065)
    assert result["intrinsicEquityValue"] == pytest.approx(100000.0)
    assert result["intrinsicPrice"] == pytest.approx(1000.0)
    assert result["intrinsicUpside"] == pytest.approx(0.0)


def test_universe_excludes_missing_from_rank():
    assumptions = {
        "riskFreeRate": 0.015,
        "equityRiskPremium": 0.05,
        "retentionRatio": 0.50,
        "marketReturns": [0.01, 0.02, -0.01, 0.00],
    }
    complete = {
        "ticker": "1001",
        "companyName": "A",
        "price": 1000,
        "bookValue": 100000,
        "sharesOutstanding": 100,
        "latestRoe": 0.12,
        "roeHistory": [0.10, 0.11, 0.12],
        "stockReturns": [0.01, 0.02, -0.01, 0.00],
    }
    missing = {
        "ticker": "1006",
        "companyName": "Missing",
        "price": None,
        "bookValue": None,
        "sharesOutstanding": None,
        "latestRoe": None,
        "roeHistory": None,
        "stockReturns": None,
    }
    rows = evaluate_universe([complete, missing], assumptions)
    by_ticker = {row["ticker"]: row for row in rows}
    assert by_ticker["1001"]["rank"] == 1
    assert by_ticker["1006"]["rank"] is None
    assert by_ticker["1006"]["eligible"] is False

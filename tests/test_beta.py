from models.beta import calculate_adjusted_beta, calculate_raw_beta
from models.exceptions import InvalidInputError, MissingDataError
import pytest


def test_raw_beta():
    market = [1.0, 2.0, 3.0, 4.0]
    stock = [2.0, 4.0, 6.0, 8.0]
    assert calculate_raw_beta(stock, market) == pytest.approx(2.0)

    identical = [0.01, -0.02, 0.03, 0.00]
    assert calculate_raw_beta(identical, identical) == pytest.approx(1.0)


def test_beta_zero_market_variance():
    stock = [0.01, 0.02, -0.01]
    for market in ([0.05, 0.05, 0.05], [0.0, 0.0, 0.0], [1, 1, 1]):
        with pytest.raises(InvalidInputError, match="market variance is zero"):
            calculate_raw_beta(stock, market)


def test_raw_beta_missing_not_zero():
    with pytest.raises(MissingDataError):
        calculate_raw_beta(None, [0.01, 0.02])


def test_adjusted_beta():
    assert calculate_adjusted_beta(1.0) == pytest.approx(1.0)
    assert calculate_adjusted_beta(0.7) == pytest.approx(0.67 * 0.7 + 0.33)


def test_adjusted_beta_lower_clip():
    assert calculate_adjusted_beta(-1.0) == pytest.approx(0.3)


def test_adjusted_beta_upper_clip():
    assert calculate_adjusted_beta(3.0) == pytest.approx(2.0)

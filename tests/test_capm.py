import pytest

from models.capm import calculate_cost_of_equity
from models.exceptions import MissingDataError


def test_capm():
    ke = calculate_cost_of_equity(
        risk_free_rate=0.015,
        beta=1.0,
        equity_risk_premium=0.05,
    )
    assert ke == pytest.approx(0.065)


def test_capm_missing_beta_not_zero():
    with pytest.raises(MissingDataError):
        calculate_cost_of_equity(0.015, None, 0.05)  # type: ignore[arg-type]

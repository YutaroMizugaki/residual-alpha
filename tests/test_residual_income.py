import pytest

from models.exceptions import MissingDataError
from models.residual_income import (
    discount_factor,
    ending_book_value,
    intrinsic_price,
    intrinsic_upside,
    residual_income,
    residual_income_model,
)
from models.roe import fade_roe


def test_residual_income():
    net_income, equity_charge, ri = residual_income(
        beginning_book_value=100.0,
        roe=0.15,
        cost_of_equity=0.10,
    )
    assert net_income == pytest.approx(15.0)
    assert equity_charge == pytest.approx(10.0)
    assert ri == pytest.approx(5.0)


def test_residual_income_roe_equivalence():
    bv, roe, ke = 250.0, 0.12, 0.08
    net_income, equity_charge, ri = residual_income(bv, roe, ke)
    assert ri == pytest.approx(net_income - equity_charge)
    assert ri == pytest.approx((roe - ke) * bv)


def test_book_value_roll_forward():
    dividend, ending = ending_book_value(
        beginning_book_value=100.0,
        net_income=20.0,
        retention_ratio=0.50,
    )
    assert dividend == pytest.approx(10.0)
    assert ending == pytest.approx(110.0)
    assert ending == pytest.approx(100.0 + 20.0 * 0.50)


def test_retention_ratio_semantics():
    # Retention 0.40 means 40% kept, 60% paid out — not the reverse.
    dividend, ending = ending_book_value(100.0, 20.0, retention_ratio=0.40)
    assert dividend == pytest.approx(20.0 * 0.60)
    assert dividend != pytest.approx(20.0 * 0.40)
    assert ending == pytest.approx(100.0 + 20.0 * 0.40)


def test_discount_year_one():
    ke = 0.10
    year_one = discount_factor(ke, 1)
    assert year_one == pytest.approx(1.0 / (1.10 ** 1))
    assert year_one != pytest.approx(1.0 / (1.10 ** 0))
    assert discount_factor(ke, 10) == pytest.approx(1.0 / (1.10 ** 10))


def test_intrinsic_equity_value():
    result = residual_income_model(
        current_book_value=100.0,
        roe_path=[0.10] * 10,
        cost_of_equity=0.10,
        retention_ratio=0.50,
    )
    assert result.intrinsic_equity_value == pytest.approx(100.0)
    assert result.pv_residual_income_sum == pytest.approx(0.0)
    for year in result.forecast:
        assert year.residual_income == pytest.approx(0.0)


def test_intrinsic_price():
    assert intrinsic_price(100.0, 10.0) == pytest.approx(10.0)


def test_intrinsic_upside():
    assert intrinsic_upside(1200.0, 1000.0) == pytest.approx(0.20)


def test_golden_residual_income_model():
    """
    Hand-checkable fixture:

    Book Value = 100, Shares = 10, ROE = 10%, ke = 10%, Retention = 50%
    Residual Income = 0 every year
    Intrinsic Equity Value = 100
    Intrinsic Price = 10
    """
    book_value = 100.0
    shares = 10.0
    roe = 0.10
    ke = 0.10
    path = fade_roe(roe, ke)
    assert path[0] == roe
    assert path[9] == ke

    result = residual_income_model(
        current_book_value=book_value,
        roe_path=path,
        cost_of_equity=ke,
        retention_ratio=0.50,
    )
    assert result.intrinsic_equity_value == pytest.approx(100.0)
    price = intrinsic_price(result.intrinsic_equity_value, shares)
    assert price == pytest.approx(10.0)

    # Units: 100 million JPY / 10 million shares = 10 JPY/share
    million_jpy = 100.0
    million_shares = 10.0
    assert million_jpy / million_shares == pytest.approx(10.0)


def test_missing_book_value_not_zero():
    with pytest.raises(MissingDataError, match="book_value"):
        residual_income_model(
            current_book_value=None,  # type: ignore[arg-type]
            roe_path=[0.10] * 10,
            cost_of_equity=0.10,
        )

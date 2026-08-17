import pytest

from models.exceptions import InsufficientHistoryError, MissingDataError
from models.roe import fade_roe, normalize_roe


def test_normalized_roe():
    latest = 0.18
    history = [0.01, 0.02, 0.16, 0.17, 0.18]  # last 3 → median 0.17
    expected = 0.6 * 0.18 + 0.4 * 0.17
    assert normalize_roe(latest, history) == pytest.approx(expected)


def test_normalized_roe_uses_last_three_years():
    latest = 0.14
    history = [0.01, 0.02, 0.03, 0.10, 0.12, 0.14]
    last3_median = 0.12
    expected = 0.6 * 0.14 + 0.4 * last3_median
    first3_median = 0.02
    wrong = 0.6 * 0.14 + 0.4 * first3_median
    result = normalize_roe(latest, history)
    assert result == pytest.approx(expected)
    assert result != pytest.approx(wrong)


def test_normalized_roe_clip():
    assert normalize_roe(0.80, [0.80, 0.80, 0.80]) == pytest.approx(0.40)
    assert normalize_roe(-0.50, [-0.50, -0.50, -0.50]) == pytest.approx(-0.20)


def test_normalized_roe_insufficient_history():
    with pytest.raises(InsufficientHistoryError):
        normalize_roe(0.10, [0.10, 0.10])
    with pytest.raises(MissingDataError):
        normalize_roe(None, [0.10, 0.10, 0.10])


def test_roe_fade_length():
    path = fade_roe(0.15, 0.08)
    assert len(path) == 10


def test_roe_fade_first_three_years():
    path = fade_roe(0.15, 0.08)
    assert path[0] == 0.15
    assert path[1] == 0.15
    assert path[2] == 0.15


def test_roe_fade_year_10_equals_ke():
    path = fade_roe(0.15, 0.08)
    assert path[9] == 0.08


def test_roe_fade_linear_between_year_3_and_10():
    nroe, ke = 0.15, 0.08
    path = fade_roe(nroe, ke)
    # Year 4 is the first fade step: 1/7 of the way from nroe to ke.
    assert path[3] == pytest.approx(nroe + (ke - nroe) * (1 / 7))
    assert path[8] == pytest.approx(nroe + (ke - nroe) * (6 / 7))

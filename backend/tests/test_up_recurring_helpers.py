from backend.services.up_recurring_service import (
    classify_cadence, compute_cv, monthly_equivalent, CADENCE_DAYS,
)


# classify_cadence ---------------------------------------------------------

def test_classify_monthly():
    assert classify_cadence([29, 30, 31, 30, 30]) == "monthly"


def test_classify_weekly():
    assert classify_cadence([7, 7, 8, 7, 7]) == "weekly"


def test_classify_fortnightly():
    assert classify_cadence([14, 13, 15, 14]) == "fortnightly"


def test_classify_yearly_single_interval():
    assert classify_cadence([365]) == "yearly"


def test_classify_returns_none_when_intervals_dont_cluster():
    assert classify_cadence([7, 30, 60, 5, 90]) is None


def test_classify_tolerates_one_outlier_in_five():
    assert classify_cadence([30, 30, 30, 30, 7]) == "monthly"


def test_classify_fails_at_60_percent_consistency():
    assert classify_cadence([30, 30, 30, 7, 7]) is None


def test_classify_returns_none_for_empty():
    assert classify_cadence([]) is None


# compute_cv --------------------------------------------------------------

def test_cv_zero_for_identical_amounts():
    assert compute_cv([10.0, 10.0, 10.0]) == 0.0


def test_cv_positive_for_varying_amounts():
    cv = compute_cv([10.0, 12.0, 14.0])
    assert 0.1 < cv < 0.3


def test_cv_zero_for_single_value():
    assert compute_cv([5.0]) == 0.0


def test_cv_zero_when_median_is_zero():
    assert compute_cv([0.0, 0.0]) == 0.0


# monthly_equivalent ------------------------------------------------------

def test_monthly_eq_monthly_passthrough():
    assert monthly_equivalent(11.99, "monthly") == 11.99


def test_monthly_eq_yearly_divides_by_twelve():
    assert round(monthly_equivalent(99.0, "yearly"), 2) == 8.25


def test_monthly_eq_weekly():
    assert round(monthly_equivalent(10.0, "weekly"), 2) == 43.45


def test_monthly_eq_fortnightly():
    assert round(monthly_equivalent(20.0, "fortnightly"), 2) == 43.45


# CADENCE_DAYS ------------------------------------------------------------

def test_cadence_days_complete():
    assert set(CADENCE_DAYS.keys()) == {"weekly", "fortnightly", "monthly", "yearly"}

from datetime import datetime, timezone
from backend.models.up import RecurringCharge


def test_recurring_charge_construction():
    rc = RecurringCharge(
        name="Spotify",
        sample_description="SPOTIFY P0123ABC",
        cadence="monthly",
        median_amount=11.99,
        last_charged_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        next_expected_at=datetime(2026, 5, 31, tzinfo=timezone.utc),
        occurrence_count=5,
        monthly_equivalent=11.99,
    )
    assert rc.cadence == "monthly"
    assert rc.median_amount == 11.99


def test_recurring_charge_rejects_unknown_cadence():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        RecurringCharge(
            name="Bad", sample_description="x", cadence="quarterly",
            median_amount=1.0,
            last_charged_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            next_expected_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            occurrence_count=2, monthly_equivalent=1.0,
        )

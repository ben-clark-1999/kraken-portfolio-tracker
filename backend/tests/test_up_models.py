from datetime import datetime, timezone
from backend.models.up import UpAccount, UpCategory, UpTransaction


def test_up_account_construction():
    a = UpAccount(
        id="abc", display_name="Spending", account_type="TRANSACTIONAL",
        ownership_type="INDIVIDUAL", balance_value=42.50, balance_currency="AUD",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    assert a.balance_value == 42.50


def test_up_category_optional_parent():
    c = UpCategory(id="good-life", name="Good Life")
    assert c.parent_id is None


def test_up_transaction_signed_amount():
    t = UpTransaction(
        id="t1", account_id="a1", status="SETTLED", description="Coffee",
        amount_value=-5.50, created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    assert t.amount_value < 0
    assert t.message is None
    assert t.settled_at is None

from unittest.mock import patch, MagicMock


def _make_trade(trade_id: str, asset: str = "ETH") -> dict:
    return {
        "trade_id": trade_id,
        "asset": asset,
        "time": 1700000000.0,
        "price": "3000.00",
        "vol": "0.5",
        "cost": "1500.00",
    }


@patch("backend.services.sync_service.get_supabase")
def test_upsert_lots_skips_existing_trades(mock_get_db):
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    # Simulate t1 already existing in the database
    mock_select = MagicMock()
    mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
        data=[{"kraken_trade_id": "t1"}]
    )

    # Mock insert chain
    mock_insert = MagicMock()
    mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])

    from backend.services.sync_service import upsert_lots

    trades = [_make_trade("t1"), _make_trade("t2")]
    result = upsert_lots(trades)

    # Should return the first trade_id (most recent)
    assert result == "t1"

    # Should only insert t2 (t1 already exists)
    insert_call = mock_db.table.return_value.insert
    insert_call.assert_called_once()
    inserted_rows = insert_call.call_args[0][0]
    assert len(inserted_rows) == 1
    assert inserted_rows[0]["kraken_trade_id"] == "t2"


@patch("backend.services.sync_service.get_supabase")
def test_upsert_lots_all_existing_skips_insert(mock_get_db):
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    # Both trades already exist
    mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
        data=[{"kraken_trade_id": "t1"}, {"kraken_trade_id": "t2"}]
    )

    from backend.services.sync_service import upsert_lots

    trades = [_make_trade("t1"), _make_trade("t2")]
    result = upsert_lots(trades)

    assert result == "t1"
    # insert should NOT be called — all trades already exist
    mock_db.table.return_value.insert.assert_not_called()


@patch("backend.services.sync_service.get_supabase")
def test_upsert_lots_empty_trades(mock_get_db):
    from backend.services.sync_service import upsert_lots

    result = upsert_lots([])
    assert result is None
    mock_get_db.assert_not_called()

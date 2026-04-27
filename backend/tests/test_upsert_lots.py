def _make_trade(trade_id: str, asset: str = "ETH") -> dict:
    return {
        "trade_id": trade_id,
        "asset": asset,
        "time": 1700000000.0,
        "price": "3000.00",
        "vol": "0.5",
        "cost": "1500.00",
    }


def test_upsert_lots_skips_existing_trades(monkeypatch):
    monkeypatch.setattr(
        "backend.repositories.lots_repo.get_existing_trade_ids",
        lambda trade_ids, schema="public": {"t1"},
    )
    inserted: list[dict] = []

    def _fake_insert(rows, schema="public"):
        inserted.extend(rows)

    monkeypatch.setattr("backend.repositories.lots_repo.insert", _fake_insert)

    from backend.services.sync_service import upsert_lots

    trades = [_make_trade("t1"), _make_trade("t2")]
    result = upsert_lots(trades)

    # Should return the first trade_id (most recent)
    assert result == "t1"

    # Should only insert t2 (t1 already exists)
    assert len(inserted) == 1
    assert inserted[0]["kraken_trade_id"] == "t2"


def test_upsert_lots_all_existing_skips_insert(monkeypatch):
    monkeypatch.setattr(
        "backend.repositories.lots_repo.get_existing_trade_ids",
        lambda trade_ids, schema="public": {"t1", "t2"},
    )
    inserted: list[dict] = []

    def _fake_insert(rows, schema="public"):
        inserted.extend(rows)

    monkeypatch.setattr("backend.repositories.lots_repo.insert", _fake_insert)

    from backend.services.sync_service import upsert_lots

    trades = [_make_trade("t1"), _make_trade("t2")]
    result = upsert_lots(trades)

    assert result == "t1"
    # insert should NOT be called — all trades already exist
    assert inserted == []


def test_upsert_lots_empty_trades(monkeypatch):
    called = []

    def _fake_get_existing(trade_ids, schema="public"):
        called.append("get_existing_trade_ids")
        return set()

    monkeypatch.setattr(
        "backend.repositories.lots_repo.get_existing_trade_ids",
        _fake_get_existing,
    )

    from backend.services.sync_service import upsert_lots

    result = upsert_lots([])
    assert result is None
    # repo should not be called for empty input
    assert called == []

"""Composes a portfolio_snapshots row tagged source='up' from current UP balances."""

from datetime import datetime, timezone

from backend.repositories import snapshots_repo, up_accounts_repo


def save_snapshot(schema: str = "public") -> None:
    total = up_accounts_repo.total_balance(schema=schema)
    snapshots_repo.insert_source_snapshot(
        captured_at=datetime.now(timezone.utc).isoformat(),
        total_value_aud=total,
        source="up",
        assets={},
        schema=schema,
    )

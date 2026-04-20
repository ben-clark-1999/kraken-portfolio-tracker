import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.db.supabase_client import get_supabase
from backend.models.portfolio import PortfolioSummary
from backend.models.snapshot import PortfolioSnapshot, SnapshotAsset

logger = logging.getLogger(__name__)


def _parse_snapshot_row(row: dict) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        id=row["id"],
        captured_at=row["captured_at"],
        total_value_aud=float(row["total_value_aud"]),
        assets={
            asset: SnapshotAsset(**data)
            for asset, data in row["assets"].items()
        },
    )


def save_snapshot(summary: PortfolioSummary, schema: str = "public") -> None:
    """Save a live snapshot, replacing any existing snapshot from today.

    This prevents duplicate rows when the server is restarted multiple times
    in the same day.
    """
    db = get_supabase()

    # Delete any existing snapshots from today before inserting
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    tomorrow = (datetime.now(tz=timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    db.schema(schema).table("portfolio_snapshots") \
        .delete() \
        .gte("captured_at", f"{today}T00:00:00+00:00") \
        .lt("captured_at", f"{tomorrow}T00:00:00+00:00") \
        .execute()

    assets_json = {
        pos.asset: {
            "quantity": pos.quantity,
            "value_aud": pos.value_aud,
            "price_aud": pos.price_aud,
        }
        for pos in summary.positions
    }
    db.schema(schema).table("portfolio_snapshots").insert({
        "captured_at": summary.captured_at,
        "total_value_aud": summary.total_value_aud,
        "assets": assets_json,
    }).execute()


def get_snapshots(
    from_dt: str | None = None,
    to_dt: str | None = None,
    schema: str = "public",
) -> list[PortfolioSnapshot]:
    db = get_supabase()
    query = db.schema(schema).table("portfolio_snapshots").select("*").order("captured_at", desc=False)
    if from_dt:
        query = query.gte("captured_at", from_dt)
    if to_dt:
        query = query.lte("captured_at", to_dt)
    result = query.execute()
    return [_parse_snapshot_row(row) for row in result.data]


def get_nearest_snapshot(target_dt: str, schema: str = "public") -> PortfolioSnapshot | None:
    """Find the snapshot with captured_at closest to target_dt."""
    db = get_supabase()

    after = (
        db.schema(schema).table("portfolio_snapshots")
        .select("*")
        .gte("captured_at", target_dt)
        .order("captured_at", desc=False)
        .limit(1)
        .execute()
    )

    before = (
        db.schema(schema).table("portfolio_snapshots")
        .select("*")
        .lt("captured_at", target_dt)
        .order("captured_at", desc=True)
        .limit(1)
        .execute()
    )

    candidates = []
    if after.data:
        candidates.append(after.data[0])
    if before.data:
        candidates.append(before.data[0])

    if not candidates:
        return None

    target = datetime.fromisoformat(target_dt)
    closest = min(
        candidates,
        key=lambda r: abs((datetime.fromisoformat(r["captured_at"]) - target).total_seconds()),
    )
    return _parse_snapshot_row(closest)


def get_oldest_snapshot(schema: str = "public") -> PortfolioSnapshot | None:
    """Get the oldest snapshot available."""
    db = get_supabase()
    result = (
        db.schema(schema).table("portfolio_snapshots")
        .select("*")
        .order("captured_at", desc=False)
        .limit(1)
        .execute()
    )
    if result.data:
        return _parse_snapshot_row(result.data[0])
    return None


def _get_existing_snapshot_dates(schema: str = "public") -> set[str]:
    """Return set of YYYY-MM-DD strings that already have snapshots."""
    db = get_supabase()
    result = db.schema(schema).table("portfolio_snapshots").select("captured_at").execute()
    return {row["captured_at"][:10] for row in result.data}


def clear_snapshots(schema: str = "public") -> int:
    """Delete all snapshots. Returns count deleted."""
    db = get_supabase()
    # Supabase delete requires a filter — match all rows via captured_at
    result = db.schema(schema).table("portfolio_snapshots") \
        .delete() \
        .gte("captured_at", "1970-01-01T00:00:00+00:00") \
        .execute()
    count = len(result.data)
    logger.info("Cleared %d snapshots", count)
    return count


def backfill_from_ledger(schema: str = "public") -> int:
    """Reconstruct daily portfolio snapshots from Kraken ledger + OHLC prices.

    Algorithm:
    1. Fetch every ledger entry → walk chronologically, maintaining a running
       balance for each tracked asset.
    2. For each calendar day, record the end-of-day holdings.
    3. Fetch daily OHLC close prices for each asset's AUD pair.
    4. Multiply holdings × price at each day to get portfolio value.
    5. Save as snapshots, skipping dates that already have data.
    6. Stop at yesterday — today is handled by the live snapshot.

    Returns the number of new snapshots created.
    """
    from backend.services import kraken_service

    # 1. Fetch all ledger entries (oldest first)
    entries = kraken_service.get_all_ledger_entries()
    if not entries:
        logger.info("Backfill: no ledger entries found — nothing to do")
        return 0

    logger.info("Backfill: fetched %d ledger entries", len(entries))

    # 2. Build running balance, snapshot at each day with activity
    running: dict[str, Decimal] = defaultdict(Decimal)
    daily_balances: dict[str, dict[str, Decimal]] = {}

    for entry in entries:
        asset_code = entry.get("asset", "")
        display = kraken_service.BALANCE_KEY_TO_DISPLAY.get(asset_code)
        if not display:
            continue

        running[display] += Decimal(str(entry["amount"]))

        ts = float(entry["time"])
        date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        daily_balances[date_str] = {k: v for k, v in running.items() if v > 0}

    if not daily_balances:
        logger.info("Backfill: no tracked-asset ledger entries — nothing to do")
        return 0

    # Log ledger date range
    sorted_ledger_dates = sorted(daily_balances.keys())
    logger.info(
        "Backfill: ledger activity spans %s to %s (%d days with activity)",
        sorted_ledger_dates[0], sorted_ledger_dates[-1], len(sorted_ledger_dates),
    )

    # 3. Fill gaps — carry forward balances on days with no activity
    #    Stop at YESTERDAY — today is handled by the live snapshot.
    start = datetime.strptime(sorted_ledger_dates[0], "%Y-%m-%d").date()
    yesterday = datetime.now(tz=timezone.utc).date() - timedelta(days=1)

    if start > yesterday:
        logger.info("Backfill: all ledger activity is from today — nothing to backfill")
        return 0

    filled: dict[str, dict[str, Decimal]] = {}
    prev: dict[str, Decimal] = {}
    current = start
    while current <= yesterday:
        ds = current.strftime("%Y-%m-%d")
        if ds in daily_balances:
            prev = daily_balances[ds]
        filled[ds] = dict(prev)
        current += timedelta(days=1)

    logger.info("Backfill: filled timeline from %s to %s (%d days)", start, yesterday, len(filled))

    # 4. Fetch daily OHLC prices for each tracked asset
    all_assets: set[str] = set()
    for balances in filled.values():
        all_assets.update(balances.keys())

    ohlc: dict[str, dict[str, float]] = {}
    for asset in sorted(all_assets):
        pair = kraken_service.ASSET_MAP.get(asset, {}).get("pair")
        if not pair:
            logger.warning("Backfill: no trading pair configured for %s — skipping", asset)
            continue
        try:
            prices = kraken_service.get_ohlc_daily(pair)
            ohlc[asset] = prices
            if prices:
                price_dates = sorted(prices.keys())
                logger.info(
                    "Backfill: OHLC %s (%s): %d candles, %s to %s",
                    asset, pair, len(prices), price_dates[0], price_dates[-1],
                )
            else:
                logger.warning("Backfill: OHLC %s (%s): empty response", asset, pair)
        except kraken_service.KrakenServiceError as e:
            logger.warning("Backfill: OHLC %s (%s) failed: %s", asset, pair, e)
            ohlc[asset] = {}

    # 5. Skip dates that already have snapshots
    existing = _get_existing_snapshot_dates(schema=schema)
    if existing:
        logger.info("Backfill: %d dates already have snapshots — will skip those", len(existing))

    # 6. Compute and save
    db = get_supabase()
    count = 0
    skipped_no_price = 0
    skipped_existing = 0

    for date_str in sorted(filled.keys()):
        if date_str in existing:
            skipped_existing += 1
            continue

        balances = filled[date_str]
        total = 0.0
        assets_json: dict[str, dict] = {}
        has_price = False

        for asset, balance in balances.items():
            bal = float(balance)
            if bal <= 0:
                continue
            price = ohlc.get(asset, {}).get(date_str, 0.0)
            if price > 0:
                has_price = True
            value = bal * price
            total += value
            assets_json[asset] = {
                "quantity": round(bal, 8),
                "value_aud": round(value, 2),
                "price_aud": round(price, 2),
            }

        if not has_price or total <= 0:
            skipped_no_price += 1
            continue

        db.schema(schema).table("portfolio_snapshots").insert({
            "captured_at": f"{date_str}T00:00:00+00:00",
            "total_value_aud": round(total, 2),
            "assets": assets_json,
        }).execute()
        count += 1

    logger.info(
        "Backfill complete: %d snapshots created, %d skipped (existing), %d skipped (no price data)",
        count, skipped_existing, skipped_no_price,
    )
    return count

from decimal import Decimal
from datetime import datetime, timedelta, date

from backend.models.portfolio import AssetPosition, PortfolioSummary
from backend.models.trade import Lot, DCAEntry
from backend.utils.fifo import calculate_cost_basis, LotInput
from backend.utils.timezone import to_iso, now_aest
from dateutil.relativedelta import relativedelta

from backend.models.analytics import (
    AssetPerformance,
    BalanceChange,
    BuyAndHoldComparison,
    BuyBreakdown,
    CGTLot,
    CGTSummary,
    DCAAnalysis,
    DCAAnalysisAsset,
    PairRatio,
    RelativePerformance,
    SkippedBuy,
    UnrealisedCGT,
)
from backend.repositories import ohlc_cache_repo
from backend.services import kraken_service
from backend.services import snapshot_service
from backend.services import sync_service


TIMEFRAME_DAYS = {
    "1W": 7,
    "1M": 30,
    "3M": 90,
    "6M": 180,
    "1Y": 365,
}


def _parse_timeframe_days(timeframe: str) -> int:
    if timeframe not in TIMEFRAME_DAYS:
        raise ValueError(
            f"Invalid timeframe: {timeframe}. Valid: {', '.join(TIMEFRAME_DAYS)} or ALL"
        )
    return TIMEFRAME_DAYS[timeframe]


def calculate_summary(
    balances: dict[str, Decimal],
    prices: dict[str, Decimal],
    lots: list[Lot],
) -> PortfolioSummary:
    total_value = sum(
        (balances.get(asset, Decimal("0")) * prices.get(asset, Decimal("0"))
         for asset in balances),
        Decimal("0"),
    )

    positions: list[AssetPosition] = []
    for asset, quantity in balances.items():
        price = prices.get(asset, Decimal("0"))
        value = quantity * price

        asset_lots = [
            LotInput(
                quantity=Decimal(str(lot.quantity)),
                cost_per_unit_aud=Decimal(str(lot.cost_per_unit_aud)),
                remaining_quantity=Decimal(str(lot.remaining_quantity)),
            )
            for lot in lots
            if lot.asset == asset
        ]
        cost_basis = calculate_cost_basis(asset_lots)
        unrealised_pnl = value - cost_basis
        allocation_pct = (value / total_value * 100) if total_value else Decimal("0")

        positions.append(AssetPosition(
            asset=asset,
            quantity=float(quantity),
            price_aud=float(price),
            value_aud=float(value),
            cost_basis_aud=float(cost_basis),
            unrealised_pnl_aud=float(unrealised_pnl),
            allocation_pct=float(allocation_pct),
        ))

    next_dca = calculate_next_dca_date(lots)
    return PortfolioSummary(
        total_value_aud=float(total_value),
        positions=sorted(positions, key=lambda p: p.value_aud, reverse=True),
        captured_at=to_iso(now_aest()),
        next_dca_date=next_dca.isoformat() if next_dca else None,
    )


def build_summary() -> PortfolioSummary:
    """Orchestrate balances, prices, lots into a full portfolio summary.

    Single entry point used by the FastAPI router, scheduler, and MCP server.
    """
    balances = kraken_service.get_balances()
    prices = kraken_service.get_ticker_prices(list(balances.keys()))
    lots = sync_service.get_all_lots()
    return calculate_summary(balances, prices, lots)


def get_dca_history(lots: list[Lot], prices: dict[str, Decimal]) -> list[DCAEntry]:
    entries: list[DCAEntry] = []
    for lot in sorted(lots, key=lambda l: l.acquired_at):
        price = prices.get(lot.asset, Decimal("0"))
        current_value = Decimal(str(lot.remaining_quantity)) * price
        cost = Decimal(str(lot.remaining_quantity)) * Decimal(str(lot.cost_per_unit_aud))
        entries.append(DCAEntry(
            lot_id=lot.id,
            asset=lot.asset,
            acquired_at=lot.acquired_at,
            quantity=lot.quantity,
            cost_aud=lot.cost_aud,
            cost_per_unit_aud=lot.cost_per_unit_aud,
            current_price_aud=float(price),
            current_value_aud=float(current_value),
            unrealised_pnl_aud=float(current_value - cost),
        ))
    return entries


def calculate_next_dca_date(lots: list[Lot]) -> date | None:
    if not lots:
        return None
    latest = max(lots, key=lambda l: l.acquired_at)
    acquired = datetime.fromisoformat(latest.acquired_at)
    return (acquired + timedelta(days=7)).date()


def get_balance_change(timeframe: str) -> BalanceChange:
    """Compare current portfolio value against a historical snapshot.

    Accepts "1W", "1M", "3M", "6M", "1Y", or "ALL".
    """
    summary = build_summary()
    end_value = summary.total_value_aud
    end_date = summary.captured_at

    note = None

    if timeframe == "ALL":
        start_snap = snapshot_service.get_oldest_snapshot()
    else:
        days = _parse_timeframe_days(timeframe)
        target_dt = to_iso(now_aest() - timedelta(days=days))
        start_snap = snapshot_service.get_nearest_snapshot(target_dt)
        if start_snap is None:
            start_snap = snapshot_service.get_oldest_snapshot()
            if start_snap is not None:
                note = (
                    f"No snapshot found for {timeframe} lookback. "
                    f"Using oldest available from {start_snap.captured_at[:10]}."
                )

    if start_snap is None:
        return BalanceChange(
            timeframe=timeframe,
            start_value_aud=0,
            end_value_aud=end_value,
            change_aud=end_value,
            change_pct=0,
            start_date="",
            end_date=end_date,
            note="No historical snapshots available.",
        )

    start_value = start_snap.total_value_aud
    change_aud = end_value - start_value
    change_pct = (change_aud / start_value * 100) if start_value else 0

    return BalanceChange(
        timeframe=timeframe,
        start_value_aud=start_value,
        end_value_aud=round(end_value, 2),
        change_aud=round(change_aud, 2),
        change_pct=round(change_pct, 2),
        start_date=start_snap.captured_at,
        end_date=end_date,
        note=note,
    )


def get_dca_analysis() -> DCAAnalysis:
    """Analyse DCA cadence and cost basis across all lots."""
    lots = sync_service.get_all_lots()

    from collections import defaultdict
    grouped: dict[str, list[Lot]] = defaultdict(list)
    for lot in lots:
        grouped[lot.asset].append(lot)

    asset_results: list[DCAAnalysisAsset] = []
    all_gaps: list[float] = []
    total_invested = 0.0

    for asset, asset_lots in sorted(grouped.items()):
        asset_lots.sort(key=lambda l: l.acquired_at)
        invested = sum(l.cost_aud for l in asset_lots)
        total_qty = sum(l.quantity for l in asset_lots)
        avg_cost = invested / total_qty if total_qty else 0

        dates = [datetime.fromisoformat(l.acquired_at).date() for l in asset_lots]
        last_buy = dates[-1]
        next_expected = last_buy + timedelta(days=7)

        if len(dates) >= 2:
            gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
            avg_gap = sum(gaps) / len(gaps)
            cadence_dev = avg_gap - 7.0
            all_gaps.extend(gaps)
        else:
            avg_gap = None
            cadence_dev = None

        total_invested += invested
        asset_results.append(DCAAnalysisAsset(
            asset=asset,
            total_invested_aud=round(invested, 2),
            average_cost_basis_aud=round(avg_cost, 2),
            lot_count=len(asset_lots),
            average_days_between_buys=round(avg_gap, 1) if avg_gap is not None else None,
            last_buy_date=last_buy.isoformat(),
            next_expected_buy_date=next_expected.isoformat(),
            cadence_deviation_days=round(cadence_dev, 1) if cadence_dev is not None else None,
        ))

    overall_avg = sum(all_gaps) / len(all_gaps) if all_gaps else None

    return DCAAnalysis(
        assets=asset_results,
        overall={
            "total_invested_aud": round(total_invested, 2),
            "average_cadence_days": round(overall_avg, 1) if overall_avg is not None else None,
        },
    )


def get_unrealised_cgt() -> UnrealisedCGT:
    """Compute unrealised CGT position for each lot.

    Uses the ATO rule: CGT discount applies when asset is held for *more than*
    12 months. Earliest eligible disposal date = acquired_date + 1 year + 1 day
    (via dateutil.relativedelta to handle leap years correctly).
    """
    lots = sync_service.get_all_lots()
    balances = kraken_service.get_balances()
    prices = kraken_service.get_ticker_prices(list(balances.keys()))
    today = now_aest().date()

    cgt_lots: list[CGTLot] = []

    for lot in lots:
        if lot.remaining_quantity <= 0:
            continue

        acquired_date = datetime.fromisoformat(lot.acquired_at).date()
        days_held = (today - acquired_date).days

        # ATO: "more than 12 months" → acquired + 1 year + 1 day
        earliest_eligible = acquired_date + relativedelta(years=1, days=1)
        eligible = today >= earliest_eligible
        days_until = max(0, (earliest_eligible - today).days)

        price = prices.get(lot.asset, Decimal("0"))
        cost_basis = lot.remaining_quantity * lot.cost_per_unit_aud
        current_value = float(Decimal(str(lot.remaining_quantity)) * price)
        gain = current_value - cost_basis

        cgt_lots.append(CGTLot(
            lot_id=lot.id,
            asset=lot.asset,
            acquired_at=lot.acquired_at,
            days_held=days_held,
            quantity=lot.remaining_quantity,
            cost_basis_aud=round(cost_basis, 2),
            current_value_aud=round(current_value, 2),
            unrealised_gain_aud=round(gain, 2),
            cgt_discount_eligible=eligible,
            days_until_discount_eligible=days_until,
        ))

    cgt_lots.sort(key=lambda l: l.days_until_discount_eligible)

    total_eligible = sum(l.unrealised_gain_aud for l in cgt_lots if l.cgt_discount_eligible)
    total_ineligible = sum(l.unrealised_gain_aud for l in cgt_lots if not l.cgt_discount_eligible)
    within_30 = sum(1 for l in cgt_lots if 0 < l.days_until_discount_eligible <= 30)

    return UnrealisedCGT(
        lots=cgt_lots,
        summary=CGTSummary(
            total_eligible_gain_aud=round(total_eligible, 2),
            total_ineligible_gain_aud=round(total_ineligible, 2),
            lots_within_30_days_of_eligibility=within_30,
        ),
    )


def get_ohlc_cached(pair: str) -> dict[str, float]:
    """Get daily OHLC close prices, caching to avoid redundant Kraken calls."""
    cached = ohlc_cache_repo.get_by_pair(pair)
    if cached:
        return cached

    prices = kraken_service.get_ohlc_daily(pair)
    if prices:
        rows = [{"pair": pair, "date": d, "close_price": p} for d, p in prices.items()]
        ohlc_cache_repo.upsert(rows)
    return prices


def get_buy_and_hold_comparison(asset: str) -> BuyAndHoldComparison:
    """Compare actual DCA portfolio outcome against all-in on a single asset.

    actual_portfolio_value = sum(lot.remaining_quantity * current_price) across
    all lots, excluding staking rewards. The buy-and-hold counterfactual uses
    the same AUD amounts on the same dates.
    """
    lots = sync_service.get_all_lots()
    balances = kraken_service.get_balances()
    prices = kraken_service.get_ticker_prices(list(balances.keys()))

    target_pair = kraken_service.ASSET_MAP.get(asset, {}).get("pair")
    if not target_pair:
        raise ValueError(f"Unknown asset: {asset}")

    target_ohlc = get_ohlc_cached(target_pair)
    target_current_price = prices.get(asset, Decimal("0"))

    actual_value = 0.0
    for lot in lots:
        price = prices.get(lot.asset, Decimal("0"))
        actual_value += float(Decimal(str(lot.remaining_quantity)) * price)

    total_invested = 0.0
    hypothetical_qty = 0.0
    breakdowns: list[BuyBreakdown] = []
    skipped: list[SkippedBuy] = []

    for lot in sorted(lots, key=lambda l: l.acquired_at):
        buy_date = datetime.fromisoformat(lot.acquired_at).strftime("%Y-%m-%d")
        aud_spent = lot.cost_aud
        total_invested += aud_spent

        target_price_on_date = target_ohlc.get(buy_date)
        if target_price_on_date is None or target_price_on_date <= 0:
            skipped.append(SkippedBuy(
                date=buy_date,
                aud_spent=round(aud_spent, 2),
                actual_asset_bought=lot.asset,
                reason=f"No OHLC data for {asset} on {buy_date}",
            ))
            continue

        hyp_qty = aud_spent / target_price_on_date
        hypothetical_qty += hyp_qty

        breakdowns.append(BuyBreakdown(
            date=buy_date,
            aud_spent=round(aud_spent, 2),
            actual_asset_bought=lot.asset,
            actual_qty=lot.quantity,
            hypothetical_qty_of_target=round(hyp_qty, 8),
        ))

    hypothetical_value = float(Decimal(str(hypothetical_qty)) * target_current_price)
    diff = hypothetical_value - actual_value
    diff_pct = (diff / actual_value * 100) if actual_value else 0

    return BuyAndHoldComparison(
        asset=asset,
        total_aud_invested=round(total_invested, 2),
        actual_portfolio_value=round(actual_value, 2),
        hypothetical_value_if_all_in_asset=round(hypothetical_value, 2),
        difference_aud=round(diff, 2),
        difference_pct=round(diff_pct, 2),
        per_buy_breakdown=breakdowns,
        skipped_buys=skipped,
    )


def get_relative_performance(timeframe: str) -> RelativePerformance:
    """Compare % change of all tracked assets over a timeframe.

    Uses OHLC close prices for both start and end dates so the comparison is
    consistent. end_date reflects the actual OHLC date used (may be yesterday
    if today's candle hasn't closed).
    """
    assets = list(kraken_service.ASSET_MAP.keys())

    # Fetch OHLC for all assets
    ohlc_by_asset: dict[str, dict[str, float]] = {}
    for asset in assets:
        pair = kraken_service.ASSET_MAP[asset]["pair"]
        ohlc_by_asset[asset] = get_ohlc_cached(pair)

    # Determine end_date = latest OHLC date available across all assets
    all_dates: set[str] = set()
    for prices in ohlc_by_asset.values():
        all_dates.update(prices.keys())

    if not all_dates:
        raise ValueError("No OHLC data available for any asset")

    end_date = max(all_dates)

    # Determine start_date
    if timeframe == "ALL":
        start_date = min(all_dates)
    else:
        days = _parse_timeframe_days(timeframe)
        from datetime import date as date_type
        target = date_type.fromisoformat(end_date) - timedelta(days=days)
        target_str = target.isoformat()
        # Find closest available date >= target
        candidates = sorted(d for d in all_dates if d >= target_str)
        if candidates:
            start_date = candidates[0]
        else:
            start_date = min(all_dates)

    # Compute per-asset performance
    perf: dict[str, dict] = {}
    for asset in assets:
        ohlc = ohlc_by_asset[asset]
        start_price = ohlc.get(start_date, 0.0)
        end_price = ohlc.get(end_date, 0.0)
        change_pct = ((end_price - start_price) / start_price * 100) if start_price else 0
        perf[asset] = {
            "start_price": start_price,
            "end_price": end_price,
            "change_pct": round(change_pct, 2),
        }

    # Rank by change_pct descending (1 = best)
    ranked = sorted(perf.keys(), key=lambda a: perf[a]["change_pct"], reverse=True)
    for rank, asset in enumerate(ranked, 1):
        perf[asset]["rank"] = rank

    asset_results = {
        asset: AssetPerformance(
            start_price_aud=perf[asset]["start_price"],
            end_price_aud=perf[asset]["end_price"],
            change_pct=perf[asset]["change_pct"],
            rank=perf[asset]["rank"],
        )
        for asset in assets
    }

    # Pairwise ratios
    ratios: dict[str, PairRatio] = {}
    for i, a in enumerate(assets):
        for b in assets[i + 1:]:
            start_a = perf[a]["start_price"]
            start_b = perf[b]["start_price"]
            end_a = perf[a]["end_price"]
            end_b = perf[b]["end_price"]

            start_ratio = (start_a / start_b) if start_b else 0
            end_ratio = (end_a / end_b) if end_b else 0
            ratio_change = ((end_ratio - start_ratio) / start_ratio * 100) if start_ratio else 0

            ratios[f"{a}/{b}"] = PairRatio(
                start_ratio=round(start_ratio, 6),
                end_ratio=round(end_ratio, 6),
                change_pct=round(ratio_change, 2),
            )

    best = ranked[0]
    worst = ranked[-1]
    spread = perf[best]["change_pct"] - perf[worst]["change_pct"]

    return RelativePerformance(
        timeframe=timeframe,
        start_date=start_date,
        end_date=end_date,
        assets=asset_results,
        ratios=ratios,
        best_performer=best,
        worst_performer=worst,
        spread_pct=round(spread, 2),
    )

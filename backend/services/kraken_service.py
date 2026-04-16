from collections import defaultdict
from decimal import Decimal
from kraken.spot import User, Market
from backend.config import settings


class KrakenServiceError(Exception):
    """Raised when a Kraken API call fails."""


# Mapping from display asset name → list of Kraken balance keys (spot + staked/bonded variants) + AUD pair
ASSET_MAP: dict[str, dict] = {
    "ETH": {
        "keys": ["XETH", "ETH", "ETH.B", "ETH.S", "ETH2", "ETH2.S", "ETH.F"],
        "pair": "ETHAUD",
    },
    "SOL": {
        "keys": ["SOL", "SOL.S", "SOL.F", "SOL03.S"],
        "pair": "SOLAUD",
    },
    "ADA": {
        "keys": ["ADA", "ADA.S", "ADA.F"],
        "pair": "ADAAUD",
    },
}

# Mapping from ledger asset code → display asset name (used for trade history).
# The ledger uses Kraken's native asset codes (XETH, SOL, ADA) rather than trading
# pair names. These are the only assets we currently track as tradeable.
LEDGER_ASSET_TO_DISPLAY: dict[str, str] = {
    "XETH": "ETH",
    "SOL":  "SOL",
    "ADA":  "ADA",
}

_user: User | None = None
_market: Market | None = None


def _get_user() -> User:
    global _user
    if _user is None:
        _user = User(key=settings.kraken_api_key, secret=settings.kraken_api_secret)
    return _user


def _get_market() -> Market:
    global _market
    if _market is None:
        _market = Market()
    return _market


def get_balances() -> dict[str, Decimal]:
    """
    Returns current balances for tracked assets, summing across spot + staked/bonded variants.
    Result: {"ETH": Decimal("0.9445"), "SOL": Decimal("9.03"), "ADA": Decimal("692.77")}
    """
    try:
        raw = _get_user().get_account_balance()
    except Exception as e:
        raise KrakenServiceError(f"get_balances failed: {e}") from e

    result: dict[str, Decimal] = {}
    for asset_name, info in ASSET_MAP.items():
        total = Decimal("0")
        for kraken_key in info["keys"]:
            raw_balance = raw.get(kraken_key, "0")
            total += Decimal(str(raw_balance))
        if total > 0:
            result[asset_name] = total
    return result


def get_ticker_prices(assets: list[str]) -> dict[str, Decimal]:
    """
    Returns live AUD prices for given asset names (e.g. ["ETH", "SOL", "ADA"]).
    Result: {"ETH": Decimal("3000.00"), "SOL": Decimal("220.50"), ...}
    """
    name_to_pair = {name: info["pair"] for name, info in ASSET_MAP.items()}
    pairs = [name_to_pair[a] for a in assets if a in name_to_pair]
    if not pairs:
        return {}

    pair_str = ",".join(pairs)
    try:
        raw = _get_market().get_ticker(pair=pair_str)
    except Exception as e:
        raise KrakenServiceError(f"get_ticker_prices failed: {e}") from e

    result: dict[str, Decimal] = {}
    pair_to_name = {info["pair"]: name for name, info in ASSET_MAP.items()}
    for pair, data in raw.items():
        asset_name = pair_to_name.get(pair)
        if asset_name:
            # 'c' is last trade price: [price, lot_volume]
            result[asset_name] = Decimal(str(data["c"][0]))
    return result


def get_trade_history(since_trade_id: str | None = None) -> list[dict]:
    """
    Returns all buy trades for tracked assets, reconstructed from ledger entries.

    Kraken represents a buy as two ledger entries sharing a refid: one `spend`
    entry in ZAUD (the fiat leaving) and one `receive` entry in the crypto
    asset. We pair them by refid to rebuild the trade. The refid serves as the
    trade_id.

    Results are sorted newest-first. Pass `since_trade_id` on subsequent runs
    to return only trades newer than the last one you stored.

    Each returned dict contains:
      trade_id (the refid), asset, time (float unix), price (str), vol (str), cost (str)
    """
    user = _get_user()
    all_entries: dict[str, dict] = {}
    offset = 0

    while True:
        try:
            result = user.get_ledgers_info(ofs=offset)
        except Exception as e:
            raise KrakenServiceError(f"get_trade_history failed: {e}") from e
        ledger: dict = result.get("ledger", {})
        count: int = result.get("count", 0)

        page_len = len(ledger)
        if page_len == 0:
            break
        all_entries.update(ledger)
        offset += page_len
        if offset >= count:
            break

    # Group ledger entries by refid. A buy trade appears as one `spend` + one
    # `receive` sharing a single refid.
    groups: dict[str, list[dict]] = defaultdict(list)
    for entry in all_entries.values():
        groups[entry["refid"]].append(entry)

    trades: list[dict] = []
    for refid, entries in groups.items():
        spend = next((e for e in entries if e.get("type") == "spend"), None)
        receive = next((e for e in entries if e.get("type") == "receive"), None)
        if not spend or not receive:
            continue  # not a buy trade (transfers, staking, deposits, etc.)

        asset = LEDGER_ASSET_TO_DISPLAY.get(receive.get("asset", ""))
        if not asset:
            continue  # untracked asset (e.g. EIGEN)

        vol = Decimal(str(receive["amount"]))
        cost_aud = abs(Decimal(str(spend["amount"])))
        if vol <= 0:
            continue
        price = cost_aud / vol

        trades.append({
            "trade_id": refid,
            "asset": asset,
            "time": float(receive["time"]),
            "price": str(price),
            "vol": str(vol),
            "cost": str(cost_aud),
        })

    # Newest first — matches how Kraken's own trades_history endpoint ordered results.
    trades.sort(key=lambda t: t["time"], reverse=True)

    if since_trade_id:
        filtered: list[dict] = []
        for t in trades:
            if t["trade_id"] == since_trade_id:
                break
            filtered.append(t)
        return filtered

    return trades
